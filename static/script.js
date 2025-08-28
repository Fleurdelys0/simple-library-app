document.addEventListener('DOMContentLoaded', () => {
    // --- SABİTLER ve DEĞİŞKENLER ---
    const API_BASE = `${window.location.protocol}//${window.location.host}`;
    const API_KEY = 'super-secret-key';
    const BOOKS_PER_PAGE = 3;
    const DEBOUNCE_DELAY = 300; // Arama gecikme süresi

    let allBooks = [];
    let filteredBooks = [];
    let currentIndex = 0;
    let searchTimeout = null;
    let isLoading = false;
    let pendingFetchCount = 0;
    let favoriteBooks = JSON.parse(localStorage.getItem('favorites') || '[]');
    let readingList = JSON.parse(localStorage.getItem('readingList') || '[]');
    let viewMode = localStorage.getItem('viewMode') || 'grid'; // grid veya list
    let allTags = [];
    let selectedFilterTags = [];
    let advancedFilters = {};
    const REDUCED_MOTION = (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    const MOTION_PREF = (localStorage.getItem('motion') || 'on');
    document.documentElement.setAttribute('data-motion', MOTION_PREF);
    const EFFECTIVE_REDUCED = MOTION_PREF === 'off' ? true : (MOTION_PREF === 'on' ? false : REDUCED_MOTION);
    // Grafikler
    let chartAuthors = null;
    let chartCategories = null;
    
    // Hızlı Fitreleme
    let quickFilter = null; // { type: 'author'|'category', value: string }

    // UI Elementlerini Yükle
    const modalLoading = document.getElementById('modalLoading');
    // Configure NProgress if available
    if (window.NProgress) {
        NProgress.configure({ showSpinner: false, trickleSpeed: 200, minimum: 0.08 });
    }

    // --- FRONTEND ÖNBELLEĞİ (ISBN-keyed) ---
    const DETAIL_TTL_MS = 5 * 60 * 1000; // 5dk
    const AI_TTL_MS = 10 * 60 * 1000;    // 10dk

    const detailCache = new Map();   // isbn -> { value, expires }
    const aiSummaryCache = new Map(); // isbn -> { value, expires }
    // ETag store: endpoint -> { etag, data }
    const etagStore = new Map();

    function cacheGet(map, key) {
        const entry = map.get(key);
        if (!entry) return null;
        if (Date.now() > entry.expires) {
            map.delete(key);
            return null;
        }
        return entry.value;
    }

    function cacheSet(map, key, value, ttlMs) {
        map.set(key, { value, expires: Date.now() + ttlMs });
    }

    function invalidateBookCaches(isbn) {
        detailCache.delete(isbn);
        aiSummaryCache.delete(isbn);
    }

    // --- İSTEK TEKİLLEŞTİRME ve İPTAL ---
    const pendingDetailRequests = new Map();   // isbn -> Promise<Book>
    const pendingAISummaryRequests = new Map(); // isbn -> Promise<string>
    let currentModalController = null; // AbortController

    async function getBookWithFallback(isbn, options = {}) {
        // Önce enhanced, yoksa eklemeyi dene, sonra enriched/basic
        try {
            return await apiFetch(`/books/${isbn}/enhanced`, options);
        } catch (e1) {
            const notFound = /not found/i.test(e1.message || '') || e1.message?.includes('500');
            console.log(`Enhanced endpoint failed for ${isbn}: ${e1.message}`);
            
            if (notFound) {
                try {
                    console.log(`Attempting to add book ${isbn} to library...`);
                    await apiFetch(`/books`, {
                        method: 'POST',
                        body: JSON.stringify({ isbn }),
                        signal: options?.signal
                    });
                    return await apiFetch(`/books/${isbn}/enhanced`, options);
                } catch (e2) {
                    console.log(`Failed to add book ${isbn}: ${e2.message}`);
                    // Son çare basic endpoint
                    try {
                        return await apiFetch(`/books/${isbn}`, { signal: options?.signal });
                    } catch (e3) {
                        console.log(`All endpoints failed for ${isbn}`);
                        throw new Error(`Kitap bulunamadı: ${isbn}`);
                    }
                }
            } else {
                try {
                    return await apiFetch(`/books/${isbn}/enriched`, options);
                } catch (e3) {
                    return await apiFetch(`/books/${isbn}`, { signal: options?.signal });
                }
            }
        }
    }

    function fetchBookEnhancedDedupe(isbn, options = {}) {
        const cached = cacheGet(detailCache, isbn);
        if (cached) return Promise.resolve(cached);
        const existing = pendingDetailRequests.get(isbn);
        if (existing) return existing;
        const p = (async () => {
            try {
                const book = await getBookWithFallback(isbn, options);
                if (book) cacheSet(detailCache, isbn, book, DETAIL_TTL_MS);
                return book;
            } finally {
                pendingDetailRequests.delete(isbn);
            }
        })();
        pendingDetailRequests.set(isbn, p);
        return p;
    }

    function fetchAISummaryDedupe(isbn, options = {}) {
        const cached = cacheGet(aiSummaryCache, isbn);
        if (cached) return Promise.resolve(cached);
        const existing = pendingAISummaryRequests.get(isbn);
        if (existing) return existing;
        const p = (async () => {
            try {
                const res = await apiFetch(`/books/${isbn}/ai-summary`, options);
                const summary = res?.summary || null;
                if (summary) cacheSet(aiSummaryCache, isbn, summary, AI_TTL_MS);
                return summary;
            } finally {
                pendingAISummaryRequests.delete(isbn);
            }
        })();
        pendingAISummaryRequests.set(isbn, p);
        return p;
    }

    // Initialize AOS (Animate On Scroll)
    if (typeof AOS !== 'undefined') {
        AOS.init({
            duration: 600,
            easing: 'ease-out-cubic',
            once: true,
            offset: 50,
            delay: 100
        });
    }

    // --- ELEMENT REFERANSLARI ---
    const bookGrid = document.getElementById('bookGrid');
    const isbnInput = document.getElementById('isbn');
    const addBtn = document.getElementById('addByIsbnBtn');
    const searchInput = document.getElementById('catalogSearch');
    const modal = document.getElementById('bookModal');
    const modalContent = document.getElementById('modalContent');
    const modalClose = document.getElementById('modalClose');
    const scrollLeftBtn = document.getElementById('scrollLeftBtn');
    const scrollRightBtn = document.getElementById('scrollRightBtn');
    const filterSelect = document.getElementById('catalogFilter');
    // NYT Reviews card elements
    const nytRefreshBtn = document.getElementById('refreshNytReviews');
    const nytReviewsState = document.getElementById('nytReviewsState');
    const nytReviewsList = document.getElementById('nytReviewsList');

    // --- OLAY DİNLEYİCİLER ---
    addBtn.addEventListener('click', handleAddBook);
    isbnInput.addEventListener('keypress', (e) => e.key === 'Enter' && handleAddBook());
    searchInput.addEventListener('input', handleSearch);
    filterSelect?.addEventListener('change', handleSearch);
    modalClose.addEventListener('click', closeModal);
    window.addEventListener('click', (e) => e.target === modal && closeModal());
    scrollLeftBtn.addEventListener('click', () => changePage(-1));
    scrollRightBtn.addEventListener('click', () => changePage(1));
    
    // Export/Import event listeners
    document.getElementById('exportJsonBtn')?.addEventListener('click', exportJSON);
    document.getElementById('exportCsvBtn')?.addEventListener('click', exportCSV);
    document.getElementById('importBtn')?.addEventListener('click', () => {
        document.getElementById('importFile').click();
    });
    document.getElementById('importFile')?.addEventListener('change', handleImport);
    
    // Random book button
    document.getElementById('randomBookBtn')?.addEventListener('click', showRandomBook);
    
    // Advanced filter button
    document.getElementById('advancedFilterBtn')?.addEventListener('click', openFilterModal);
    
    // Tag management
    document.getElementById('addTagBtn')?.addEventListener('click', addNewTag);
    
    // Filter modal buttons
    document.getElementById('applyFilterBtn')?.addEventListener('click', applyAdvancedFilter);
    document.getElementById('clearFilterBtn')?.addEventListener('click', clearAdvancedFilter);
    document.getElementById('closeFilterBtn')?.addEventListener('click', closeFilterModal);
    // NYT Reviews refresh
    nytRefreshBtn?.addEventListener('click', () => loadNytReviews(true));

    // Global ripple effect for .btn
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.btn');
        if (!btn) return;
        if (btn.disabled || btn.getAttribute('aria-disabled') === 'true') return;
        if (EFFECTIVE_REDUCED) return;
        const rect = btn.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        btn.style.setProperty('--ripple-x', `${x}px`);
        btn.style.setProperty('--ripple-y', `${y}px`);
        btn.classList.remove('ripple');
        // force reflow to restart animation
        void btn.offsetWidth;
        btn.classList.add('ripple');
        setTimeout(() => btn.classList.remove('ripple'), 700);
    });
    
    // --- TOOLTIPLER (Tippy.js) ---
    function initTooltips() {
        // Tippy.js yüklenmemişse veya hatalıysa atla
        if (typeof tippy === 'undefined' || !tippy) {
            console.warn('Tippy.js henüz yüklenmemiş');
            return;
        }
        
        try {
            const commonOptions = {
                theme: 'material',
                animation: 'shift-away-subtle',
                arrow: true,
                delay: [150, 0],
                duration: [200, 150],
                interactive: false,
                appendTo: () => document.body,
                placement: 'top',
                offset: [0, 8],
            };

            // Statik öğeler (data-tippy-content attribute'u olanlar)
            document.querySelectorAll('[data-tippy-content]').forEach(el => {
                try {
                    if (!el._tippy) {
                        tippy(el, commonOptions);
                    }
                } catch (e) {
                    console.warn('Tooltip oluşturulamadı:', e);
                }
            });

            // Dinamik kitap kartı aksiyon butonları (title -> data-tippy-content dönüştür, sonra bağla)
            document.querySelectorAll('.book-actions .action-icon').forEach(btn => {
                try {
                    const title = btn.getAttribute('title');
                    if (title) {
                        btn.setAttribute('data-tippy-content', title);
                        btn.removeAttribute('title');
                    }
                    if (!btn._tippy) {
                        tippy(btn, commonOptions);
                    }
                } catch (e) {
                    console.warn('Button tooltip oluşturulamadı:', e);
                }
            });
            
            console.log('Tooltips başarıyla başlatıldı (createSingleton kullanımı kaldırıldı)');
        } catch (error) {
            console.warn('Tooltip başlatma hatası:', error);
        }
    }
    
    // Güvenli tooltip başlatma - Tippy.js yüklenene kadar bekle
    async function safeInitTooltips() {
        if (window.loadTippy) {
            try {
                await window.loadTippy();
                // Tippy yüklendikten sonra kısa bir bekleme
                setTimeout(initTooltips, 200);
            } catch (e) {
                console.warn('Tippy.js yüklenemedi, tooltipsiz devam ediliyor');
            }
        } else {
            // loadTippy yoksa klasik yöntemle dene
            setTimeout(initTooltips, 300);
        }
    }
    
    // İlk yüklemede güvenli tooltip başlatma
    safeInitTooltips();

    // 3D Tilt effect for book cards
    function initTiltEffect() {
        const bookCards = document.querySelectorAll('.book-card');
        bookCards.forEach(card => {
            // Remove existing listeners if any
            card.removeEventListener('mousemove', handleTiltMove);
            card.removeEventListener('mouseleave', handleTiltLeave);
            
            if (!EFFECTIVE_REDUCED) {
                card.addEventListener('mousemove', handleTiltMove);
                card.addEventListener('mouseleave', handleTiltLeave);
            }
        });
    }

    function handleTiltMove(e) {
        const card = e.currentTarget;
        const rect = card.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        const mouseX = e.clientX - centerX;
        const mouseY = e.clientY - centerY;
        
        // Calculate rotation values (max 15 degrees)
        const rotateX = (mouseY / (rect.height / 2)) * -8;
        const rotateY = (mouseX / (rect.width / 2)) * 8;
        
        // Calculate spotlight position
        const spotlightX = ((e.clientX - rect.left) / rect.width) * 100;
        const spotlightY = ((e.clientY - rect.top) / rect.height) * 100;

        // Calculate gentle translation toward the mouse (max ~12px)
        const maxTranslate = 12; // px
        const tx = (mouseX / (rect.width / 2)) * maxTranslate;
        const ty = (mouseY / (rect.height / 2)) * maxTranslate;
        
        card.style.setProperty('--rx', `${rotateX}deg`);
        card.style.setProperty('--ry', `${rotateY}deg`);
        card.style.setProperty('--mx', `${spotlightX}%`);
        card.style.setProperty('--my', `${spotlightY}%`);
        card.style.setProperty('--tx', `${tx.toFixed(2)}px`);
        card.style.setProperty('--ty', `${ty.toFixed(2)}px`);
    }

    function handleTiltLeave(e) {
        const card = e.currentTarget;
        card.style.setProperty('--rx', '0deg');
        card.style.setProperty('--ry', '0deg');
        card.style.setProperty('--mx', '50%');
        card.style.setProperty('--my', '50%');
        card.style.setProperty('--tx', '0px');
        card.style.setProperty('--ty', '0px');
    }

    // Elastic hover scale for book cards using GSAP
    function initCardElasticHover() {
        if (EFFECTIVE_REDUCED || !window.gsap) return;
        const cards = document.querySelectorAll('.book-card');
        cards.forEach(card => {
            // initial scale var
            card.style.setProperty('--scale', '1');
            const onEnter = () => {
                card.setAttribute('data-elastic', '1');
                gsap.to(card, {
                    duration: 0.8,
                    ease: 'elastic.out(1, 0.5)',
                    overwrite: 'auto',
                    transformOrigin: '50% 50%',
                    "--scale": 1.07,
                    onComplete: () => card.removeAttribute('data-elastic')
                });
            };
            const onLeave = () => {
                card.setAttribute('data-elastic', '1');
                gsap.to(card, {
                    duration: 0.6,
                    ease: 'power3.out',
                    overwrite: 'auto',
                    transformOrigin: '50% 50%',
                    "--scale": 1,
                    onComplete: () => card.removeAttribute('data-elastic')
                });
            };
            card.addEventListener('mouseenter', onEnter);
            card.addEventListener('mouseleave', onLeave);
        });
    }

    // --- API FONKSİYONLARI ---
    async function apiFetch(endpoint, options = {}) {
        const method = (options.method || 'GET').toUpperCase();
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': API_KEY
            }
        };
        const headers = { ...(defaultOptions.headers || {}), ...(options.headers || {}) };
        const useEtag = method === 'GET' && options.etag !== false; // etag=false ile devre dışı bırakılabilir
        const etagEntry = useEtag ? etagStore.get(endpoint) : null;
        if (useEtag && etagEntry?.etag) {
            headers['If-None-Match'] = etagEntry.etag;
        }

        // HTTP cache davranışı: İlk istekte network'ten getir (reload), etag varken tarayıcı cache kullanılmasın (no-store)
        const cacheMode = method === 'GET'
            ? (etagEntry ? 'no-store' : 'reload')
            : (options.cache || 'no-store');

        const reqOptions = {
            ...defaultOptions,
            ...options,
            method,
            headers,
            cache: cacheMode
        };

        // Start global progress
        if (window.NProgress) {
            if (pendingFetchCount === 0) NProgress.start();
            pendingFetchCount++;
        }
        try {
            const response = await fetch(`${API_BASE}${endpoint}`, reqOptions);

            // 304: İçerik değişmedi -> eldeki veriyi döndür
            if (response.status === 304 && useEtag) {
                if (etagEntry?.data !== undefined) return etagEntry.data;
                // 304 ama elimizde veri yoksa, güvenli bir hata üret
                throw new Error('İçerik değişmedi (304) ancak önbellek bulunamadı.');
            }

            if (!response.ok) {
                // non-JSON gövdelerde de güvenli yakalama yap
                const errorData = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
                throw new Error(errorData.detail || `HTTP ${response.status}`);
            }

            if (response.status === 204) return null;

            // JSON parse ve ETag depolama
            const data = await response.json();
            if (useEtag) {
                const etag = response.headers.get('ETag');
                if (etag) {
                    etagStore.set(endpoint, { etag, data });
                }
            }
            return data;
        } finally {
            if (window.NProgress) {
                pendingFetchCount = Math.max(0, pendingFetchCount - 1);
                if (pendingFetchCount === 0) NProgress.done();
            }
        }
    }
    // Expose for inline/global callers
    window.apiFetch = apiFetch;

    // Backend health kontrolü (bağlantı hatası için hızlı uyarı)
    async function checkBackend() {
        try {
            await fetch(`${API_BASE}/health`, { method: 'GET' });
        } catch (e) {
            showToast('Sunucuya bağlanılamıyor. Lütfen backend\'i çalıştırın (http://127.0.0.1:8000).', 'error');
        }
    }

    // --- DİYALOGLAR (SweetAlert2) ---
    async function confirmDialog(message, confirmText = 'Evet', cancelText = 'Vazgeç') {
        try {
            if (typeof Swal !== 'undefined' && Swal?.fire) {
                const res = await Swal.fire({
                    title: 'Emin misiniz?',
                    text: message,
                    icon: 'warning',
                    showCancelButton: true,
                    confirmButtonText: confirmText,
                    cancelButtonText: cancelText,
                    reverseButtons: true,
                });
                return !!res.isConfirmed;
            }
            return Promise.resolve(confirm(message));
        } catch (e) {
            console.warn('Confirm dialog failed, using native confirm:', e);
            return Promise.resolve(confirm(message));
        }
    }

    // --- ANA İŞLEVLER ---
    async function fetchAndDisplayStats() {
        try {
            const stats = await apiFetch('/stats');
            const statsGrid = document.getElementById('statsGrid');
            if (statsGrid) {
                statsGrid.innerHTML = `
                    <div class="stat-item fade-in">
                        <div class="stat-number" id="statTotal">0</div>
                        <div class="stat-label">Toplam Kitap</div>
                    </div>
                    <div class="stat-item fade-in">
                        <div class="stat-number" id="statAuthors">0</div>
                        <div class="stat-label">Benzersiz Yazar</div>
                    </div>
                    <div class="stat-item fade-in">
                        <div class="stat-number" id="statFavorites">${favoriteBooks.length}</div>
                        <div class="stat-label">Favori Kitap</div>
                    </div>
                    <div class="stat-item fade-in">
                        <div class="stat-number" id="statReading">${readingList.length}</div>
                        <div class="stat-label">Okunacak</div>
                    </div>
                    <div class="stat-item fade-in">
                        <div class="stat-number" id="statAvgPages">0</div>
                        <div class="stat-label">Ort. Sayfa</div>
                    </div>
                    <div class="stat-item fade-in">
                        <div class="stat-number" id="statAvgRating">0</div>
                        <div class="stat-label">Ort. Puan</div>
                    </div>
                `;
                animateNumber(document.getElementById('statTotal'), stats.total_books, 700);
                animateNumber(document.getElementById('statAuthors'), stats.unique_authors, 700);
            }
            // Sol kart: Koleksiyon Özeti
            const left = document.getElementById('leftQuickStats');
            if (left) {
                left.innerHTML = `
                    <div class="stat-item fade-in">
                        <div class="stat-number" id="leftStatTotal">0</div>
                        <div class="stat-label">Toplam Kitap</div>
                    </div>
                    <div class="stat-item fade-in">
                        <div class="stat-number" id="leftStatAuthors">0</div>
                        <div class="stat-label">Benzersiz Yazar</div>
                    </div>
                    <div class="stat-item fade-in">
                        <div class="stat-number" id="leftStatFavorites">${favoriteBooks.length}</div>
                        <div class="stat-label">Favori</div>
                    </div>
                    <div class="stat-item fade-in">
                        <div class="stat-number" id="leftStatReading">${readingList.length}</div>
                        <div class="stat-label">Okunacak</div>
                    </div>
                    <div class="stat-item fade-in">
                        <div class="stat-number" id="leftStatAvgPages">0</div>
                        <div class="stat-label">Ort. Sayfa</div>
                    </div>
                    <div class="stat-item fade-in">
                        <div class="stat-number" id="leftStatAvgRating">0</div>
                        <div class="stat-label">Ort. Puan</div>
                    </div>
                `;
                animateNumber(document.getElementById('leftStatTotal'), stats.total_books, 700);
                animateNumber(document.getElementById('leftStatAuthors'), stats.unique_authors, 700);
            }
        } catch (error) {
            console.error("İstatistikler yüklenemedi:", error);
        }
    }

    function animateNumber(el, to, duration = 600) {
        const from = 0;
        const start = performance.now();
        function tick(now) {
            const t = Math.min(1, (now - start) / duration);
            const eased = t < 0.5 ? 2*t*t : -1 + (4-2*t)*t; // easeInOutQuad-ish
            el.textContent = Math.floor(from + (to - from) * eased);
            if (t < 1) requestAnimationFrame(tick);
            else el.textContent = to;
        }
        requestAnimationFrame(tick);
    }

    // --- CHARTS (Chart.js) ---
    function getThemeColors() {
        const root = getComputedStyle(document.documentElement);
        const primary = root.getPropertyValue('--primary')?.trim() || '#3B82F6';
        const secondary = root.getPropertyValue('--secondary')?.trim() || '#10B981';
        const surface = root.getPropertyValue('--card-bg')?.trim() || '#111827';
        const text = root.getPropertyValue('--text-color')?.trim() || '#E5E7EB';
        const palette = [
            primary, '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#06B6D4', '#84CC16', '#EC4899', '#6366F1', '#14B8A6'
        ];
        return { primary, secondary, surface, text, palette };
    }

    function countBy(arr, keyGetter) {
        const map = new Map();
        for (const item of arr) {
            const key = keyGetter(item);
            if (!key) continue;
            const prev = map.get(key) || 0;
            map.set(key, prev + 1);
        }
        return map;
    }

    function getTopN(map, n) {
        return Array.from(map.entries())
            .sort((a, b) => b[1] - a[1])
            .slice(0, n);
    }

    function buildCharts() {
        if (typeof Chart === 'undefined') return; // Chart.js yüklenmemişse çık
        const authorsCanvas = document.getElementById('chartAuthors');
        const categoriesCanvas = document.getElementById('chartCategories');
        if (!authorsCanvas || !categoriesCanvas) return;

        const { palette, text } = getThemeColors();

        // Top authors (ilk 5)
        const authorCounts = countBy(allBooks, b => (b.author || '').trim());
        authorCounts.delete('');
        const topAuthors = getTopN(authorCounts, 5);
        const aLabels = topAuthors.map(([k]) => k);
        const aData = topAuthors.map(([, v]) => v);

        // Category distribution (ilk 8)
        const catCounts = new Map();
        for (const b of allBooks) {
            let cats = [];
            const raw = b.categories;
            if (Array.isArray(raw)) {
                cats = raw;
            } else if (typeof raw === 'string') {
                // String ise virgül veya noktalı virgül ile böl
                cats = raw.split(/[;,]/g);
            }
            for (const c of cats) {
                const key = (c || '').trim();
                if (!key) continue;
                catCounts.set(key, (catCounts.get(key) || 0) + 1);
            }
        }
        const topCats = getTopN(catCounts, 8);
        const cLabels = topCats.map(([k]) => k);
        const cData = topCats.map(([, v]) => v);

        // AUTHORS BAR
        if (chartAuthors) {
            chartAuthors.data.labels = aLabels;
            chartAuthors.data.datasets[0].data = aData;
            chartAuthors.update();
        } else {
            chartAuthors = new Chart(authorsCanvas.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: aLabels,
                    datasets: [{
                        label: 'Kitap sayısı',
                        data: aData,
                        backgroundColor: palette.slice(0, aLabels.length).map(c => c + 'CC'),
                        borderColor: palette.slice(0, aLabels.length),
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: { beginAtZero: true, ticks: { color: text } },
                        x: { ticks: { color: text } }
                    },
                    plugins: {
                        legend: { labels: { color: text } },
                        tooltip: { enabled: true }
                    },
                    onClick: (evt, activeEls) => {
                        const idx = activeEls?.[0]?.index;
                        if (idx == null) return;
                        const label = chartAuthors.data.labels[idx];
                        applyQuickFilter({ type: 'author', value: label });
                    }
                }
            });
        }

        // CATEGORIES/TAGS DOUGHNUT (fallback: tags when no categories)
        const catWrapper = categoriesCanvas?.parentElement;
        // Prepare tag fallback from allTags (book_count)
        const sortedTags = Array.isArray(allTags) ? [...allTags].sort((a, b) => (b.book_count||0) - (a.book_count||0)) : [];
        const tTop = sortedTags.filter(t => (t.book_count||0) > 0).slice(0, 8);
        const tLabels = tTop.map(t => t.name);
        const tData = tTop.map(t => t.book_count);
        const useTags = cLabels.length === 0 && tLabels.length > 0;
        const labels = useTags ? tLabels : cLabels;
        const data = useTags ? tData : cData;
        const dsLabel = useTags ? 'Etiket' : 'Kategori';

        if (labels.length === 0) {
            if (chartCategories) { chartCategories.destroy(); chartCategories = null; }
            if (categoriesCanvas) categoriesCanvas.style.display = 'none';
            if (catWrapper && !catWrapper.querySelector('.chart-placeholder')) {
                const ph = document.createElement('div');
                ph.className = 'chart-placeholder';
                ph.setAttribute('style', 'height:160px;display:flex;align-items:center;justify-content:center;opacity:0.7;border:1px dashed var(--muted-border, #555);border-radius:8px;');
                ph.textContent = 'Kategori/Etiket verisi bulunamadı';
                catWrapper.appendChild(ph);
            }
        } else {
            if (catWrapper) {
                const ph = catWrapper.querySelector('.chart-placeholder');
                if (ph) ph.remove();
            }
            if (categoriesCanvas) categoriesCanvas.style.display = '';
            if (chartCategories) {
                chartCategories.data.labels = labels;
                chartCategories.data.datasets[0].data = data;
                chartCategories.data.datasets[0].label = dsLabel;
                chartCategories.update();
            } else if (categoriesCanvas) {
                chartCategories = new Chart(categoriesCanvas.getContext('2d'), {
                    type: 'doughnut',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: dsLabel,
                            data: data,
                            backgroundColor: palette.slice(0, labels.length).map(c => c + 'CC'),
                            borderColor: palette.slice(0, labels.length),
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { position: 'bottom', labels: { color: text } },
                            tooltip: { enabled: true }
                        },
                        onClick: (evt, activeEls) => {
                            const idx = activeEls?.[0]?.index;
                            if (idx == null) return;
                            const label = chartCategories.data.labels[idx];
                            applyQuickFilter({ type: useTags ? 'tag' : 'category', value: label });
                        }
                    }
                });
            }
        }
    
    }

    

    function applyQuickFilter(f) {
        quickFilter = f; // { type, value }
        showQuickFilterBadge();
        handleSearch();
    }

    function clearQuickFilter() {
        quickFilter = null;
        showQuickFilterBadge();
        handleSearch();
    }

    function showQuickFilterBadge() {
        const badge = document.getElementById('quickFilterBadge');
        if (!badge) return;
        if (!quickFilter) {
            badge.classList.add('hidden');
            badge.innerHTML = '';
            return;
        }
        const labels = { author: 'Yazar', category: 'Kategori', tag: 'Etiket' };
        const title = labels[quickFilter.type] || 'Filtre';
        const value = String(quickFilter.value);
        badge.classList.remove('hidden');
        badge.innerHTML = `
            <span><i class="fas fa-filter"></i> ${title}: <strong>${value}</strong></span>
            <button class="btn btn-ghost btn-sm" id="clearQuickFilterBtn" aria-label="Filtreyi temizle"><i class="fas fa-times"></i></button>
        `;
        document.getElementById('clearQuickFilterBtn')?.addEventListener('click', clearQuickFilter);
    }
    // Fuse.js index for fuzzy search
    let fuse = null;
    function buildFuseIndex() {
        if (!window.Fuse) return;
        const options = {
            includeScore: true,
            threshold: 0.35,
            ignoreLocation: true,
            keys: [
                { name: 'title', weight: 0.5 },
                { name: 'author', weight: 0.3 },
                'isbn',
                { name: 'categories', weight: 0.2 }
            ]
        };
        fuse = new Fuse(allBooks, options);
    }

    // --- NYTimes Books RSS: Yardımcılar ve Render ---
    function escapeHtml(str) {
        if (str == null) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function stripHtml(str) {
        if (!str) return '';
        try {
            const tmp = document.createElement('div');
            tmp.innerHTML = str;
            return (tmp.textContent || tmp.innerText || '').trim();
        } catch (_) {
            return String(str).replace(/<[^>]*>/g, '').trim();
        }
    }

    function truncate(str, max = 160) {
        const s = String(str || '');
        return s.length > max ? s.slice(0, max - 1) + '…' : s;
    }

    function formatRssDate(d) {
        if (!d) return '';
        const dt = new Date(d);
        if (isNaN(dt.getTime())) return '';
        try {
            return dt.toLocaleDateString('tr-TR', { year: 'numeric', month: 'short', day: 'numeric' });
        } catch (_) {
            return dt.toISOString().slice(0, 10);
        }
    }

    function renderNytReviews(items) {
        if (!nytReviewsList) return;
        nytReviewsList.innerHTML = '';
        if (!Array.isArray(items) || items.length === 0) {
            if (nytReviewsState) nytReviewsState.textContent = 'İçerik bulunamadı.';
            return;
        }
        const limited = items.slice(0, 3);
        const frag = document.createDocumentFragment();
        for (const it of limited) {
            const li = document.createElement('li');
            li.className = 'nyt-item';

            const imgUrl = it.image || '/static/default-cover.svg';
            const title = escapeHtml(it.title || 'İsimsiz');
            const link = it.link || '#';
            const summary = truncate(stripHtml(it.summary || ''), 180);
            const pub = formatRssDate(it.published_at);

            li.innerHTML = `
                <a href="${link}" target="_blank" rel="noopener" class="nyt-link">
                    <div class="nyt-media">
                        <img src="${imgUrl}" alt="Kapak" loading="lazy" onerror="this.src='/static/default-cover.svg'" />
                    </div>
                    <div class="nyt-body">
                        <div class="nyt-title">${title}</div>
                        <div class="nyt-meta">${pub ? `<i class='fas fa-clock'></i> ${pub}` : ''}</div>
                        <div class="nyt-desc">${escapeHtml(summary)}</div>
                    </div>
                </a>
            `;
            frag.appendChild(li);
        }

        nytReviewsList.appendChild(frag);
        if (nytReviewsState) nytReviewsState.textContent = '';
    }

    async function loadNytReviews(force = false) {
      if (!nytReviewsList || !nytReviewsState) return;
      try {
          if (nytReviewsState) nytReviewsState.textContent = 'Yükleniyor...';
          if (nytRefreshBtn) {
              nytRefreshBtn.disabled = true;
              nytRefreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Yükleniyor';
          }
          const endpoint = force 
              ? `/news/books/nyt?limit=3&force_refresh=true`
              : `/news/books/nyt?limit=3`;
          const data = await apiFetch(endpoint, { etag: !force });
          // Backend şu anda düz bir dizi döndürüyor; ileriye dönük uyumluluk için { items: [] } formatını da destekleyelim
          const items = Array.isArray(data) ? data : (Array.isArray(data?.items) ? data.items : []);
          renderNytReviews(items);
      } catch (error) {
          if (nytReviewsState) nytReviewsState.textContent = 'Yüklenemedi.';
          showToast('NYT incelemeleri yüklenemedi: ' + (error?.message || error), 'error');
      } finally {
          if (nytRefreshBtn) {
              nytRefreshBtn.disabled = false;
              nytRefreshBtn.innerHTML = '<i class="fas fa-rotate"></i> Yenile';
          }
      }
  }

    async function initialize() {
        try {
            checkBackend();
            await fetchAndDisplayStats();
            await loadTags();
            allBooks = await apiFetch('/books');
            buildFuseIndex();
            handleSearch(); // Başlangıçta tüm kitapları filtrele ve render et
            buildCharts();
            updateDerivedKPIs();
            fetchAndDisplayExtendedStats();
            // NYT Reviews ilk yükleme
            await loadNytReviews(false);
            
            // Initialize advanced interactions
            setTimeout(() => {
                initAdvancedInteractions();
                // Yenile AOS after dynamic content loads
                if (typeof AOS !== 'undefined') {
                    AOS.refresh();
                }
            }, 500);
        } catch (error) {
            showToast(`Kitaplar yüklenemedi: ${error.message}`, 'error');
        }
    }

    async function handleAddBook() {
        const isbn = isbnInput.value.trim();
        if (!isbn) return showToast('Lütfen bir ISBN girin.', 'warning');
        
        addBtn.disabled = true;
        addBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Ekleniyor...';
        
        try {
            const newBook = await apiFetch('/books', { method: 'POST', body: JSON.stringify({ isbn }) });
            allBooks.unshift(newBook);
            // Eklendikten sonra ilgili ISBN ve liste ETag önbelleklerini temizle
            invalidateBookCaches(isbn);
            buildFuseIndex();
            isbnInput.value = '';
            handleSearch();
            buildCharts();
            updateDerivedKPIs();
            showToast(`"${newBook.title}" eklendi!`, 'success');
            fetchAndDisplayStats(); // İstatistikleri güncelle
        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            addBtn.disabled = false;
            addBtn.innerHTML = '<i class="fas fa-plus"></i> Ekle';
        }
    }

    async function handleDeleteBook(isbn) {
        const ok = await confirmDialog('Bu kitabı silmek istediğinizden emin misiniz?', 'Sil', 'Vazgeç');
        if (!ok) return;
        try {
            await apiFetch(`/books/${isbn}`, { method: 'DELETE' });
            // Invalidate caches for this ISBN
            invalidateBookCaches(isbn);
            allBooks = allBooks.filter(b => b.isbn !== isbn);
            buildFuseIndex();
            handleSearch();
            buildCharts();
            updateDerivedKPIs();
            showToast('Kitap başarıyla silindi.', 'success');
            fetchAndDisplayStats(); // İstatistikleri güncelle
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function handleUpdateBook(isbn) {
        const title = document.getElementById('editTitle').value.trim();
        const author = document.getElementById('editAuthor').value.trim();
        if (!title || !author) return showToast('Başlık ve yazar boş olamaz.', 'warning');

        try {
            const updatedBook = await apiFetch(`/books/${isbn}`, {
                method: 'PUT',
                body: JSON.stringify({ title, author })
            });
            // Invalidate caches for updated details
            invalidateBookCaches(isbn);
            const index = allBooks.findIndex(b => b.isbn === isbn);
            if (index !== -1) allBooks[index] = updatedBook;
            buildFuseIndex();
            closeModal();
            handleSearch();
            showToast(`"${updatedBook.title}" güncellendi.`, 'success');
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    function handleSearch() {
        // Debounce ile arama performansını artır
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(async () => {
            const raw = searchInput.value || '';
            const searchTerm = raw.trim();
            const lcTerm = searchTerm.toLowerCase();
            const currentFilter = (filterSelect?.value || 'all');

            if (searchTerm && window.Fuse && fuse) {
                const results = fuse.search(searchTerm);
                filteredBooks = results.map(r => r.item);
            } else {
                // Basit filtre (aranmıyorsa tümü)
                filteredBooks = allBooks.slice();
            }
            // Ek filtre (favoriler/okuma listesi)
            if (currentFilter === 'favorites') {
                filteredBooks = filteredBooks.filter(b => favoriteBooks.includes(b.isbn));
            } else if (currentFilter === 'reading') {
                filteredBooks = filteredBooks.filter(b => readingList.includes(b.isbn));
            }
            // Hızlı grafik filtresi
            if (quickFilter) {
                const { type, value } = quickFilter;
                // 'tag' filtresi backend üzerinden yapılır
                if (type === 'tag') {
                    try {
                        const tag = (allTags || []).find(t => (t.name || '').trim() === String(value));
                        if (tag) {
                            const response = await apiFetch('/books/search/enhanced', {
                                method: 'POST',
                                body: JSON.stringify({ tag_ids: [tag.id] })
                            });
                            filteredBooks = response || [];
                        } else {
                            filteredBooks = [];
                        }
                    } catch (e) {
                        console.warn('Tag filtresi uygulanamadı:', e?.message || e);
                    }
                    currentIndex = 0;
                    renderBooks();
                    // Arama terimini vurgula
                    if (typeof Mark !== 'undefined') {
                        if (searchTerm) highlightSearch(searchTerm);
                        else clearSearchHighlight();
                    }
                    return; // 'tag' filtresi işlendi, çık
                }
                filteredBooks = filteredBooks.filter(b => {
                    if (type === 'author') return (b.author || '').trim() === value;
                    if (type === 'category') return Array.isArray(b.categories) && b.categories.some(c => (c || '').trim() === value);
                    return true;
                });
            }
            currentIndex = 0; // Aramadan sonra slider'ı başa sar
            renderBooks();
            // Arama terimini vurgula
            if (typeof Mark !== 'undefined') {
                if (searchTerm) highlightSearch(searchTerm);
                else clearSearchHighlight();
            }
        }, DEBOUNCE_DELAY);
    }

    function updateDerivedKPIs() {
        try {
            const elAvgPages = document.getElementById('statAvgPages');
            const elAvgRating = document.getElementById('statAvgRating');
            const leftAvgPages = document.getElementById('leftStatAvgPages');
            const leftAvgRating = document.getElementById('leftStatAvgRating');
            if (!elAvgPages && !elAvgRating) return;

            const pages = allBooks.map(b => b.page_count).filter(n => typeof n === 'number' && isFinite(n) && n > 0);
            const avgPages = pages.length ? Math.round(pages.reduce((a,b)=>a+b,0) / pages.length) : 0;
            const ratings = allBooks.map(b => b.google_rating).filter(n => typeof n === 'number' && isFinite(n) && n > 0);
            const avgRating = ratings.length ? (ratings.reduce((a,b)=>a+b,0) / ratings.length) : 0;

            if (elAvgPages) elAvgPages.textContent = String(avgPages);
            if (elAvgRating) elAvgRating.textContent = avgRating ? avgRating.toFixed(1) : '0.0';
            if (leftAvgPages) leftAvgPages.textContent = String(avgPages);
            if (leftAvgRating) leftAvgRating.textContent = avgRating ? avgRating.toFixed(1) : '0.0';
        } catch (e) {
            console.warn('KPI güncellenemedi:', e);
        }
    }

    async function fetchAndDisplayExtendedStats() {
        try {
            const data = await apiFetch('/stats/extended');
            const topAuthorEl = document.getElementById('topAuthor');
            const recentEl = document.getElementById('recentAdditions');
            if (topAuthorEl) {
                const name = data.most_common_author || '-';
                const topCount = data.books_by_author ? Math.max(...Object.values(data.books_by_author)) : 0;
                topAuthorEl.innerHTML = `<div class="extended-row"><strong>En Çok Kitaplı Yazar:</strong> ${name} ${topCount ? `(${topCount})` : ''}</div>`;
            }
            if (recentEl) {
                const items = (data.recent_additions || []).map(b => `<li>${b.title} <span class="muted">— ${b.author}</span></li>`).join('');
                recentEl.innerHTML = `<div class="extended-row"><strong>Son Eklenenler:</strong></div><ul class="recent-list">${items}</ul>`;
            }
        } catch (e) {
            console.log('Extended stats alınamadı:', e?.message || e);
        }
    }

    // --- FAVORİ VE OKUMA LİSTESİ İŞLEVLERİ ---
    function toggleFavorite(isbn) {
        const index = favoriteBooks.indexOf(isbn);
        if (index === -1) {
            favoriteBooks.push(isbn);
            showToast('Favorilere eklendi!', 'success');
        } else {
            favoriteBooks.splice(index, 1);
            showToast('Favorilerden çıkarıldı!', 'info');
        }
        localStorage.setItem('favorites', JSON.stringify(favoriteBooks));
        renderBooks();
    }

    function toggleReadingList(isbn) {
        const index = readingList.indexOf(isbn);
        if (index === -1) {
            readingList.push(isbn);
            showToast('Okuma listesine eklendi!', 'success');
        } else {
            readingList.splice(index, 1);
            showToast('Okuma listesinden çıkarıldı!', 'info');
        }
        localStorage.setItem('readingList', JSON.stringify(readingList));
        renderBooks();
    }

    // --- RENDER FONKSİYONLARI ---
    function renderBooks() {
        bookGrid.innerHTML = '';
        if (filteredBooks.length === 0) {
            bookGrid.innerHTML = '<p class="no-books">Katalogda hiç kitap yok veya arama sonucu boş.</p>';
            updateSlider();
            return;
        }

        filteredBooks.forEach(book => {
            const isFavorite = favoriteBooks.includes(book.isbn);
            const isInReadingList = readingList.includes(book.isbn);
            const isEnhanced = book.data_sources && book.data_sources.length > 1;
            const hasAI = book.ai_summary;
            
            const bookCard = document.createElement('div');
            // Scroll-reveal başlangıç durumu: sr-ready (reduced motion değilse)
            // ISBN ve hydration durumu
            bookCard.dataset.isbn = book.isbn;
            // Yalnızca gerçekten detay alanlar varsa hydrated say: ai_summary tek başına yeterli değil
            bookCard.dataset.hydrated = (book.page_count || (book.categories && book.categories.length) || book.google_rating) ? '1' : '0';
            bookCard.className = `book-card ${isEnhanced ? 'enhanced' : ''} ${EFFECTIVE_REDUCED ? '' : 'sr-ready'}`;
            if (!EFFECTIVE_REDUCED) {
                // Gecikme değişkenini başlangıçta sıfırla, IntersectionObserver görünür olunca güncellenecek
                bookCard.style.setProperty('--sr-delay', '0ms');
            }
            // Book card tooltip (Tippy)
            bookCard.setAttribute('data-tippy-content', `${book.title}`);
            bookCard.innerHTML = `
                <div class="book-cover">
                    <img src="${book.cover_url || API_BASE + '/covers/' + book.isbn}" alt="${book.title}" loading="lazy" onerror="this.src='/static/default-cover.svg'">
                    ${book.google_rating ? `
                        <div class="rating-overlay">
                            <i class="fas fa-star"></i> ${book.google_rating}
                        </div>
                    ` : ''}
                    <div class="book-actions">
                        <button class="action-icon favorite-icon ${isFavorite ? 'active' : ''}" data-isbn="${book.isbn}" title="Favori">
                            ${isFavorite ? '❤️' : '🤍'}
                        </button>
                        <button class="action-icon reading-icon ${isInReadingList ? 'active' : ''}" data-isbn="${book.isbn}" title="Okuma Listesi">
                            ${isInReadingList ? '📖' : '📚'}
                        </button>
                        <button class="action-icon edit-icon" data-isbn="${book.isbn}" title="Düzenle">✏️</button>
                        <button class="action-icon delete-icon" data-isbn="${book.isbn}" title="Sil">🗑️</button>
                    </div>
                </div>
                <div class="book-info">
                    <h3 class="book-title">${book.title}</h3>
                    <p class="book-author">${book.author}</p>
                    ${book.page_count ? `<p class="book-pages"><i class="fas fa-file-alt"></i> ${book.page_count} sayfa</p>` : ''}
                    ${book.categories && book.categories.length ? `<p class="book-category"><i class="fas fa-tag"></i> ${book.categories[0]}</p>` : ''}
                    <div class="book-badges">
                        ${isFavorite ? '<span class="badge badge-favorite">❤️ Favori</span>' : ''}
                        ${isInReadingList ? '<span class="badge badge-reading">📖 Okuma Listesi</span>' : ''}
                        ${hasAI ? '<span class="badge enhanced-badge">🤖 AI</span>' : ''}
                        ${isEnhanced ? '<span class="badge enhanced-badge">✨ Enhanced</span>' : ''}
                    </div>
                    ${book.data_sources && book.data_sources.length ? `
                        <div class="source-count">
                            <i class="fas fa-database"></i> ${book.data_sources.length} kaynak
                        </div>
                    ` : ''}
                    <div class="wave-cta" role="button" tabindex="0" aria-label="Detayları gör" data-isbn="${book.isbn}">
                        <span class="wave-text" data-text="Detayları Gör">Detayları Gör</span>
                    </div>
                </div>
            `;
            // Ripple Katmanı
            const rippleLayer = document.createElement('div');
            rippleLayer.className = 'ripple-layer';
            bookCard.appendChild(rippleLayer);
            bookGrid.appendChild(bookCard);
            bookCard.addEventListener('click', (e) => {
                if (!e.target.closest('.action-icon')) {
                    window.openDetailModal(book.isbn);
                }
            });
        });

        document.querySelectorAll('.delete-icon').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                handleDeleteBook(btn.dataset.isbn);
            });
        });

        document.querySelectorAll('.edit-icon').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                openEditModal(btn.dataset.isbn);
            });
        });

        document.querySelectorAll('.favorite-icon').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleFavorite(btn.dataset.isbn);
            });
        });

        document.querySelectorAll('.reading-icon').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleReadingList(btn.dataset.isbn);
            });
        });

        // Initialize tilt effect for new cards
        initTiltEffect();
        // Initialize elastic hover after tilt
        initCardElasticHover();

        updateSlider();
        
        // Re-initialize advanced interactions for new cards
        setTimeout(() => {
            initAdvancedInteractions();
            // Yeni eklenen öğeler için tooltipleri yenile
            initTooltips();
            // Refresh AOS for new elements
            if (typeof AOS !== 'undefined') {
                AOS.refresh();
            }
            // Initialize wavy CTA after cards are in DOM
            initWaveCTAs();
        }, 100);
    }

    // Global ripple for book cards (similar to .btn ripple)
    document.addEventListener('click', (e) => {
        const card = e.target.closest('.book-card');
        if (!card) return;
        if (EFFECTIVE_REDUCED) return;
        // Do not trigger ripple when clicking action icons or actions bar
        if (e.target.closest('.action-icon') || e.target.closest('.book-actions')) return;
        const layer = card.querySelector('.ripple-layer');
        if (!layer) return;
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const dot = document.createElement('span');
        dot.className = 'card-ripple';
        dot.style.left = x + 'px';
        dot.style.top = y + 'px';
        layer.appendChild(dot);
        // Remove after animation
        setTimeout(() => {
            dot.remove();
        }, 700);
    });

    // Mark.js ile arama vurgulama
    function highlightSearch(term) {
        try {
            const instance = new Mark(bookGrid);
            instance.unmark({
                done: () => {
                    instance.mark(term, {
                        separateWordSearch: true,
                        caseSensitive: false,
                        accuracy: 'partially',
                        className: 'search-mark'
                    });
                }
            });
        } catch (e) {
            // mark.js yoksa hata yutulur
        }
    }

    function clearSearchHighlight() {
        try {
            const instance = new Mark(bookGrid);
            instance.unmark();
        } catch (e) {}
    }

    function bindCardInteractions() {
        const cards = document.querySelectorAll('.book-card');
        cards.forEach(card => {
            let raf = null;
            const onMove = (e) => {
                if (EFFECTIVE_REDUCED) return;
                const rect = card.getBoundingClientRect();
                const px = (e.clientX - rect.left) / rect.width;
                const py = (e.clientY - rect.top) / rect.height;
                const rx = (0.5 - py) * 12; // -6deg..6deg
                const ry = (px - 0.5) * 12; // -6deg..6deg
                if (raf) cancelAnimationFrame(raf);
                raf = requestAnimationFrame(() => {
                    card.style.setProperty('--mx', `${(px * 100).toFixed(2)}%`);
                    card.style.setProperty('--my', `${(py * 100).toFixed(2)}%`);
                    card.style.setProperty('--rx', `${rx.toFixed(2)}deg`);
                    card.style.setProperty('--ry', `${ry.toFixed(2)}deg`);
                });
            };
            const onLeave = () => {
                if (raf) cancelAnimationFrame(raf);
                card.style.setProperty('--rx', `0deg`);
                card.style.setProperty('--ry', `0deg`);
                card.style.setProperty('--mx', `50%`);
                card.style.setProperty('--my', `50%`);
            };
            card.addEventListener('mousemove', onMove);
            card.addEventListener('mouseleave', onLeave);
        });
    }

    // --- WAVY CTA INIT (GSAP hover + accessibility) ---
    function initWaveCTAs(context = document) {
        try {
            const nodes = context.querySelectorAll('.wave-cta .wave-text');
            nodes.forEach(el => {
                if (el.dataset.processed === '1') return;
                el.dataset.processed = '1';
                const raw = (el.getAttribute('data-text') || el.textContent || '').trim();
                // Split into spans
                el.textContent = '';
                const frag = document.createDocumentFragment();
                Array.from(raw).forEach((ch, i) => {
                    const span = document.createElement('span');
                    span.className = 'char';
                    span.textContent = ch === ' ' ? '\u00A0' : ch;
                    if (!EFFECTIVE_REDUCED) {
                        span.style.animationDelay = `${i * 60}ms`;
                    }
                    frag.appendChild(span);
                });
                el.appendChild(frag);
            });

            // Click + keyboard
            context.querySelectorAll('.wave-cta').forEach(cta => {
                const onActivate = (e) => {
                    e.stopPropagation();
                    const isbn = cta.dataset.isbn || cta.closest('.book-card')?.dataset.isbn;
                    if (isbn && typeof window.openDetailModal === 'function') {
                        window.openDetailModal(isbn);
                    }
                };
                cta.addEventListener('click', onActivate);
                cta.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onActivate(e);
                    }
                });

                // GSAP hover neon if available
                if (!EFFECTIVE_REDUCED && window.gsap) {
                    const chars = cta.querySelectorAll('.char');
                    cta.addEventListener('mouseenter', () => {
                        gsap.to(chars, {
                            y: -2,
                            stagger: 0.02,
                            duration: 0.25,
                            overwrite: true,
                            textShadow: '0 0 10px var(--neon-a), 0 0 18px var(--neon-b)'
                        });
                        gsap.to(cta, { boxShadow: '0 6px 18px color-mix(in srgb, var(--neon-b), transparent 40%), 0 0 18px color-mix(in srgb, var(--neon-a), transparent 54%)', duration: 0.25, overwrite: true });
                    });
                    cta.addEventListener('mouseleave', () => {
                        gsap.to(chars, {
                            y: 0,
                            stagger: 0.02,
                            duration: 0.25,
                            overwrite: true,
                            textShadow: '0 0 6px color-mix(in srgb, var(--neon-a), transparent 40%), 0 0 12px color-mix(in srgb, var(--neon-b), transparent 55%)'
                        });
                        gsap.to(cta, { boxShadow: '0 2px 10px rgba(0,0,0,.12)', duration: 0.25, overwrite: true });
                    });
                }
            });
        } catch (_) {}
    }

    // --- SLIDER İŞLEVLERİ ---
    function visibleCount() {
        const wrapper = document.querySelector('.book-grid-wrapper');
        const card = document.querySelector('.book-card');
        if (!card) return BOOKS_PER_PAGE;
        const wrapperWidth = wrapper.clientWidth - 160; // leave padding for buttons
        return Math.max(1, Math.floor(wrapperWidth / card.clientWidth));
    }

    function updateSlider() {
        const perPage = visibleCount();
        const offset = -currentIndex * (100 / perPage);
        bookGrid.style.transform = `translateX(${offset}%)`;
        
        scrollLeftBtn.classList.toggle('hidden', currentIndex === 0);
        scrollRightBtn.classList.toggle('hidden', currentIndex >= Math.max(0, filteredBooks.length - perPage));
    }

    function changePage(direction) {
        const perPage = visibleCount();
        const newIndex = currentIndex + direction;
        if (newIndex >= 0 && newIndex <= Math.max(0, filteredBooks.length - perPage)) {
            currentIndex = newIndex;
            updateSlider();
        }
    }

    // --- MODAL İŞLEVLERİ ---

    async function openEditModal(isbn) {
        try {
            const book = await apiFetch(`/books/${isbn}`);
            modalContent.innerHTML = `
                <div class="detail-cover">
                     <img src="${API_BASE}/covers/${book.isbn}" alt="${book.title}" onerror="this.src='/static/default-cover.svg'">
                </div>
                <div class="detail-info">
                    <h2>Kitabı Düzenle</h2>
                    <div class="form-group">
                        <label for="editTitle">Başlık</label>
                        <input type="text" id="editTitle" value="${book.title}">
                    </div>
                    <div class="form-group">
                        <label for="editAuthor">Yazar</label>
                        <input type="text" id="editAuthor" value="${book.author}">
                    </div>
                    <button id="saveUpdateBtn" class="btn">Kaydet</button>
                </div>
            `;
            modal.style.display = 'flex';
            requestAnimationFrame(() => modal.classList.add('open'));
            document.getElementById('saveUpdateBtn').addEventListener('click', () => handleUpdateBook(isbn));
        } catch (error) {
            showToast(`Düzenleme için kitap yüklenemedi: ${error.message}`, 'error');
        }
    }

    function closeModal() {
        // graceful close with transition
        if (currentModalController) {
            try { currentModalController.abort(); } catch (e) {}
            currentModalController = null;
        }
        // Ensure loading overlay is hidden when closing the modal
        hideModalLoading();
        modal.classList.remove('open');
        const hide = () => {
            modal.style.display = 'none';
            modalContent.innerHTML = '';
            modal.removeEventListener('transitionend', hide);
        };
        // If transitionend doesn't fire, fallback
        modal.addEventListener('transitionend', hide);
        setTimeout(hide, 320);
    }

    // Expose close for global callers
    window.closeModal = closeModal;

    // --- GELİŞMİŞ ETKİLEŞİM FONKSİYONLARI ---
    function initAdvancedInteractions() {
        // Tilt effect for book cards
        const bookCards = document.querySelectorAll('.book-card');
        bookCards.forEach(card => {
            card.addEventListener('mousemove', handleTilt);
            card.addEventListener('mouseleave', resetTilt);
        });

        // Magnetic effect for buttons
        const buttons = document.querySelectorAll('.btn');
        buttons.forEach(btn => {
            btn.classList.add('btn-magnetic');
            btn.addEventListener('mousemove', handleMagnetic);
            btn.addEventListener('mouseleave', resetMagnetic);
        });

        // Ripple effect for buttons
        buttons.forEach(btn => {
            btn.addEventListener('click', createRipple);
        });

        // Scroll-triggered animations
        // 1) Header görünürlüğü (mevcut davranışı koru)
        const headerObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('visible');
                }
            });
        }, { threshold: 0.1 });
        document.querySelectorAll('.catalog-header').forEach(el => headerObserver.observe(el));

        // 2) Kitap kartları için scroll-reveal (stagger ile)
        const perPage = visibleCount();
        const cards = Array.from(document.querySelectorAll('.book-card'));

        if (EFFECTIVE_REDUCED) {
            // Hareket azaltma açık ise animasyon kullanma
            cards.forEach(c => {
                c.classList.remove('sr-ready');
                c.classList.add('sr-in');
                c.style.removeProperty('--sr-delay');
                // Reduced motion açıkken de zengin verileri hemen hydrate et
                hydrateCardIfNeeded(c);
            });
        } else {
            const cardObserver = new IntersectionObserver((entries, obs) => {
                entries.forEach(entry => {
                    if (!entry.isIntersecting) return;
                    const el = entry.target;
                    const idx = cards.indexOf(el);
                    const col = perPage > 0 ? (idx % perPage) : idx;
                    const delay = Math.min(col * 120, 720); // 0,120,240,... max 720ms
                    el.style.setProperty('--sr-delay', `${delay}ms`);
                    el.classList.add('sr-in');
                    el.classList.remove('sr-ready');
                    // Görünür olan kart için zengin detayları getir ve DOM'u güncelle
                    hydrateCardIfNeeded(el);
                    obs.unobserve(el);
                });
            }, { threshold: 0.15, rootMargin: '0px 0px -10% 0px' });

            cards.forEach(c => {
                if (!c.classList.contains('sr-in')) {
                    c.classList.add('sr-ready');
                    c.style.setProperty('--sr-delay', '0ms');
                    cardObserver.observe(c);
                }
            });
        }
    }

    // Kart görünür olduğunda, henüz zenginleştirilmemişse detayları getir ve DOM'u güncelle
    function hydrateCardIfNeeded(card) {
        try {
            if (!card || card.dataset.hydrated === '1') return;
            const isbn = card.dataset.isbn;
            if (!isbn) return;
            fetchBookEnhancedDedupe(isbn)
                .then(enhanced => {
                    if (!enhanced) return;
                    hydrateCardWithEnhancedData(card, enhanced);
                    card.dataset.hydrated = '1';
                    // Bellekteki kitabı da zengin alanlarla güncelle
                    const idx = allBooks.findIndex(b => b.isbn === isbn);
                    if (idx !== -1) {
                        Object.assign(allBooks[idx], enhanced);
                    }
                })
                .catch(() => {});
        } catch (_) {}
    }

    // Kartın içeriğini gelen zengin verilerle güncelle
    function hydrateCardWithEnhancedData(card, book) {
        try {
            const info = card.querySelector('.book-info');
            const cover = card.querySelector('.book-cover');
            if (!info) return;

            // Sayfa sayısı
            if (book.page_count) {
                let pagesEl = info.querySelector('.book-pages');
                const html = `<i class="fas fa-file-alt"></i> ${book.page_count} sayfa`;
                if (!pagesEl) {
                    pagesEl = document.createElement('p');
                    pagesEl.className = 'book-pages';
                    pagesEl.innerHTML = html;
                    const authorEl = info.querySelector('.book-author');
                    if (authorEl && authorEl.nextSibling) authorEl.parentNode.insertBefore(pagesEl, authorEl.nextSibling);
                    else info.appendChild(pagesEl);
                } else {
                    pagesEl.innerHTML = html;
                }
            }

            // Kategori (ilk kategori)
            if (Array.isArray(book.categories) && book.categories.length) {
                let catEl = info.querySelector('.book-category');
                const html = `<i class="fas fa-tag"></i> ${book.categories[0]}`;
                if (!catEl) {
                    catEl = document.createElement('p');
                    catEl.className = 'book-category';
                    catEl.innerHTML = html;
                    const pagesEl = info.querySelector('.book-pages');
                    if (pagesEl && pagesEl.nextSibling) pagesEl.parentNode.insertBefore(catEl, pagesEl.nextSibling);
                    else info.appendChild(catEl);
                } else {
                    catEl.innerHTML = html;
                }
            }

            // Google rating overlay
            if (book.google_rating && cover) {
                let overlay = cover.querySelector('.rating-overlay');
                const html = `<i class="fas fa-star"></i> ${book.google_rating}`;
                if (!overlay) {
                    overlay = document.createElement('div');
                    overlay.className = 'rating-overlay';
                    overlay.innerHTML = html;
                    cover.appendChild(overlay);
                } else {
                    overlay.innerHTML = html;
                }
            }

            // Rozetler: Enhanced / AI
            const badges = info.querySelector('.book-badges');
            if (badges) {
                const hasEnhancedBadge = badges.textContent.includes('Enhanced');
                const hasAIBadge = badges.textContent.includes('AI');
                if (Array.isArray(book.data_sources) && book.data_sources.length > 1 && !hasEnhancedBadge) {
                    const span = document.createElement('span');
                    span.className = 'badge enhanced-badge';
                    span.textContent = '✨ Enhanced';
                    badges.appendChild(span);
                }
                if (book.ai_summary && !hasAIBadge) {
                    const span = document.createElement('span');
                    span.className = 'badge enhanced-badge';
                    span.textContent = '🤖 AI';
                    badges.appendChild(span);
                }
            }

            // Kaynak sayısı
            if (Array.isArray(book.data_sources) && book.data_sources.length) {
                let sc = info.querySelector('.source-count');
                const html = `<i class="fas fa-database"></i> ${book.data_sources.length} kaynak`;
                if (!sc) {
                    sc = document.createElement('div');
                    sc.className = 'source-count';
                    sc.innerHTML = html;
                    info.appendChild(sc);
                } else {
                    sc.innerHTML = html;
                }
            }
        } catch (_) {}
    }

    function handleTilt(e) {
        const card = e.currentTarget;
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;
        
        const rotateX = (y - centerY) / 10;
        const rotateY = (centerX - x) / 10;
        
        card.style.transform = `translateY(-12px) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
        card.style.setProperty('--mx', `${(x / rect.width) * 100}%`);
        card.style.setProperty('--my', `${(y / rect.height) * 100}%`);
    }

    function resetTilt(e) {
        const card = e.currentTarget;
        card.style.transform = '';
        card.style.removeProperty('--mx');
        card.style.removeProperty('--my');
    }

    function handleMagnetic(e) {
        const btn = e.currentTarget;
        const rect = btn.getBoundingClientRect();
        const x = e.clientX - rect.left - rect.width / 2;
        const y = e.clientY - rect.top - rect.height / 2;
        
        btn.style.transform = `translate(${x * 0.1}px, ${y * 0.1}px) translateY(-3px) scale(1.02)`;
    }

    function resetMagnetic(e) {
        const btn = e.currentTarget;
        btn.style.transform = '';
    }

    function createRipple(e) {
        const btn = e.currentTarget;
        const rect = btn.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height);
        const x = e.clientX - rect.left - size / 2;
        const y = e.clientY - rect.top - size / 2;
        
        const ripple = document.createElement('span');
        ripple.style.cssText = `
            position: absolute;
            width: ${size}px;
            height: ${size}px;
            left: ${x}px;
            top: ${y}px;
            background: rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            transform: scale(0);
            animation: ripple-animation 0.6s linear;
            pointer-events: none;
            z-index: 0;
        `;
        
        btn.appendChild(ripple);
        
        setTimeout(() => {
            ripple.remove();
        }, 600);
    }

    // CSS animation for ripple
    const style = document.createElement('style');
    style.textContent = `
        @keyframes ripple-animation {
            to {
                transform: scale(4);
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);

    // --- LOADING UI FONKSİYONLARI ---
    function showModalLoading(text = 'İçerik yükleniyor...') {
        // Ensure overlay exists (it may be removed when modalContent.innerHTML is set)
        let overlay = document.getElementById('modalLoading');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'modalLoading';
            overlay.className = 'modal-loading';
            overlay.innerHTML = `
                <div class="modal-spinner uiverse-loader">
                    <div class="dots-wave" aria-hidden="true">
                        <span></span><span></span><span></span><span></span><span></span>
                    </div>
                    <div class="loading-text">${text}</div>
                </div>
            `;
            const mc = document.getElementById('modalContent');
            if (mc) mc.appendChild(overlay);
        } else {
            // Replace old spinner markup with the new dots-wave loader even if overlay exists
            overlay.className = 'modal-loading';
            overlay.innerHTML = `
                <div class="modal-spinner uiverse-loader">
                    <div class="dots-wave" aria-hidden="true">
                        <span></span><span></span><span></span><span></span><span></span>
                    </div>
                    <div class="loading-text">${text}</div>
                </div>
            `;
        }
        overlay.classList.add('show');
    }

    function hideModalLoading() {
        const overlay = document.getElementById('modalLoading');
        if (overlay) {
            overlay.classList.remove('show');
        }
    }

    async function showRandomBook() {
        try {
            const response = await fetch(`${API_BASE}/books/random`);
            if (!response.ok) {
                if (response.status === 404) {
                    showToast('Kütüphanede henüz kitap yok!', 'warning');
                    return;
                }
                throw new Error('Rastgele kitap getirilemedi');
            }
            
            const book = await response.json();
            // Kitap detaylarını göster
            openDetailModal(book.isbn);
            showToast('Rastgele kitap seçildi!', 'success');
        } catch (error) {
            showToast('Hata: ' + error.message, 'error');
        }
    }

    // --- EXPORT/IMPORT FONKSİYONLARI ---
    async function exportJSON() {
        try {
            const response = await fetch(`${API_BASE}/export/json`, {
                headers: { 'Accept': 'application/json' }
            });
            // Hata sayfalarının indirilmesini engelle
            if (!response.ok) {
                const errText = await response.text();
                throw new Error(errText || 'JSON export başarısız.');
            }
            const contentType = response.headers.get('content-type') || '';
            if (!contentType.includes('application/json')) {
                const errText = await response.text();
                throw new Error(errText || 'Beklenmeyen yanıt alındı.');
            }
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `library_export_${new Date().toISOString().slice(0,10)}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            showToast('Kütüphane başarıyla JSON olarak indirildi!', 'success');
        } catch (error) {
            showToast('Export hatası: ' + error.message, 'error');
        }
    }

    async function exportCSV() {
        try {
            const response = await fetch(`${API_BASE}/export/csv`, {
                headers: { 'Accept': 'text/csv' }
            });
            // Hata sayfalarının indirilmesini engelle
            if (!response.ok) {
                const errText = await response.text();
                throw new Error(errText || 'CSV export başarısız.');
            }
            const contentType = response.headers.get('content-type') || '';
            // Sunucu bazen charset ekleyebilir: text/csv; charset=utf-8
            if (!contentType.includes('text/csv')) {
                const errText = await response.text();
                throw new Error(errText || 'Beklenmeyen yanıt alındı.');
            }
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `library_export_${new Date().toISOString().slice(0,10)}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            showToast('Kütüphane başarıyla CSV olarak indirildi!', 'success');
        } catch (error) {
            showToast('Export hatası: ' + error.message, 'error');
        }
    }

    async function handleImport(event) {
        const file = event.target.files[0];
        if (!file) return;
        
        if (!file.name.endsWith('.json')) {
            showToast('Lütfen bir JSON dosyası seçin!', 'warning');
            return;
        }
        
        try {
            const text = await file.text();
            const data = JSON.parse(text);
            
            const response = await fetch(`${API_BASE}/import/json`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': API_KEY
                },
                body: JSON.stringify(data)
            });
            
            if (!response.ok) {
                if (response.status === 403) {
                    throw new Error('Yetkilendirme hatası: API anahtarı geçersiz. .env içindeki API_KEY ile frontend\'deki API_KEY eşleşmeli.');
                }
                let errMsg = 'Import başarısız!';
                try {
                    const errJson = await response.json();
                    errMsg = errJson.detail || errJson.message || errMsg;
                } catch (_) {
                    const errText = await response.text();
                    if (errText) errMsg = errText;
                }
                throw new Error(errMsg);
            }
            
            const result = await response.json();
            showToast(`${result.imported} kitap başarıyla yüklendi!`, 'success');
            
            // Listeyi yenile
            allBooks = await apiFetch('/books');
            handleSearch();
            buildCharts();
            fetchAndDisplayStats();
            
            // Input'ı temizle
            event.target.value = '';
        } catch (error) {
            showToast('Import hatası: ' + error.message, 'error');
            event.target.value = '';
        }
    }

    // --- YENİ ÖZELLİKLER ---
    
    // Tag yönetimi
    async function loadTags() {
        try {
            allTags = await apiFetch('/tags');
            renderTags();
            renderFilterTags();
        } catch (error) {
            console.error('Etiketler yüklenemedi:', error);
        }
    }
    
    function renderTags() {
        const tagList = document.getElementById('tagList');
        if (!tagList) return;
        
        tagList.innerHTML = allTags.map(tag => `
            <span class="tag" style="background-color: ${tag.color}20; color: ${tag.color}; border: 1px solid ${tag.color};">
                ${tag.name} (${tag.book_count})
            </span>
        `).join('');
    }
    
    function renderFilterTags() {
        const filterTags = document.getElementById('filterTags');
        if (!filterTags) return;
        
        filterTags.innerHTML = allTags.map(tag => `
            <label class="tag-checkbox">
                <input type="checkbox" value="${tag.id}" data-tag-name="${tag.name}">
                <span style="background-color: ${tag.color}20; color: ${tag.color}; border: 1px solid ${tag.color};">
                    ${tag.name}
                </span>
            </label>
        `).join('');
    }
    
    async function addNewTag() {
        const nameInput = document.getElementById('newTagName');
        const colorInput = document.getElementById('newTagColor');
        
        const name = nameInput.value.trim();
        const color = colorInput.value;
        
        if (!name) {
            showToast('Lütfen etiket adı girin', 'warning');
            return;
        }
        
        try {
            const newTag = await apiFetch('/tags', {
                method: 'POST',
                body: JSON.stringify({ name, color })
            });
            
            allTags.push(newTag);
            renderTags();
            renderFilterTags();
            
            nameInput.value = '';
            colorInput.value = '#3B82F6';
            
            showToast(`"${name}" etiketi eklendi!`, 'success');
        } catch (error) {
            showToast(error.message, 'error');
        }
    }
    
    // Gelişmiş filtreleme
    function openFilterModal() {
        const modal = document.getElementById('filterModal');
        modal.style.display = 'flex';
        requestAnimationFrame(() => modal.classList.add('open'));
    }
    
    function closeFilterModal() {
        const modal = document.getElementById('filterModal');
        modal.classList.remove('open');
        setTimeout(() => {
            modal.style.display = 'none';
        }, 300);
    }
    
    async function applyAdvancedFilter() {
        const title = document.getElementById('filterTitle').value.trim();
        const author = document.getElementById('filterAuthor').value.trim();
        const yearFrom = document.getElementById('filterYearFrom').value;
        const yearTo = document.getElementById('filterYearTo').value;
        const minRating = document.getElementById('filterMinRating').value;
        
        // Seçili etiketleri al
        const selectedTags = [];
        document.querySelectorAll('#filterTags input[type="checkbox"]:checked').forEach(cb => {
            selectedTags.push(parseInt(cb.value));
        });
        
        const filters = {};
        if (title) filters.title = title;
        if (author) filters.author = author;
        if (yearFrom) filters.publish_year_from = parseInt(yearFrom);
        if (yearTo) filters.publish_year_to = parseInt(yearTo);
        if (minRating) filters.min_rating = parseFloat(minRating);
        if (selectedTags.length > 0) filters.tag_ids = selectedTags;
        
        try {
            const response = await apiFetch('/books/search/enhanced', {
                method: 'POST',
                body: JSON.stringify(filters)
            });
            
            allBooks = response;
            handleSearch();
            buildCharts();
            closeFilterModal();
            showToast('Filtre uygulandı', 'success');
        } catch (error) {
            showToast('Filtreleme hatası: ' + error.message, 'error');
        }
    }
    
    function clearAdvancedFilter() {
        document.getElementById('filterTitle').value = '';
        document.getElementById('filterAuthor').value = '';
        document.getElementById('filterYearFrom').value = '';
        document.getElementById('filterYearTo').value = '';
        document.getElementById('filterMinRating').value = '';
        
        document.querySelectorAll('#filterTags input[type="checkbox"]').forEach(cb => {
            cb.checked = false;
        });
        
        // Tüm kitapları yeniden yükle
        initialize();
        closeFilterModal();
        showToast('Filtreler temizlendi', 'info');
    }
    
    // Kitap detay modalını genişlet - yorumlar ve benzer kitaplar için
    async function showBookDetailsExtended(isbn, fetchOptions = {}) {
        try {
            // Ensure loading overlay is visible even when called directly (e.g., after adding a review)
            showModalLoading('Kitap detayları yükleniyor...');
            const signal = fetchOptions?.signal;
            // Kitap detayını tekilleştirerek al
            const book = await fetchBookEnhancedDedupe(isbn, { signal });
            // Bağımsız istekleri paralelleştir
            let reviews = [],
                rating = { average_rating: 0, review_count: 0 },
                tags = [],
                similar = [],
                aiSummary = cacheGet(aiSummaryCache, isbn) || null;

            const [revRes, ratRes, tagRes, simRes, aiRes] = await Promise.allSettled([
                apiFetch(`/books/${isbn}/reviews`, { signal }),
                apiFetch(`/books/${isbn}/rating`, { signal }),
                apiFetch(`/books/${isbn}/tags`, { signal }),
                apiFetch(`/books/${isbn}/similar?limit=3`, { signal }),
                aiSummary ? Promise.resolve(aiSummary) : fetchAISummaryDedupe(isbn, { signal })
            ]);

            if (revRes.status === 'fulfilled') reviews = revRes.value; else console.log('Reviews not available:', revRes.reason?.message || revRes.reason);
            if (ratRes.status === 'fulfilled') rating = ratRes.value; else console.log('Rating not available:', ratRes.reason?.message || ratRes.reason);
            if (tagRes.status === 'fulfilled') tags = tagRes.value; else console.log('Tags not available:', tagRes.reason?.message || tagRes.reason);
            if (simRes.status === 'fulfilled') similar = simRes.value; else console.log('Similar books not available:', simRes.reason?.message || simRes.reason);
            if (aiRes.status === 'fulfilled') aiSummary = aiRes.value; else aiSummary = aiSummary || null;

            const ratingStars = '⭐'.repeat(Math.round(rating.average_rating || 0));
            const emptyStars = '☆'.repeat(5 - Math.round(rating.average_rating || 0));

            // Ensure the catalog reflects newly added books (e.g., from Similar)
            try {
                if (book && !allBooks.some(b => b.isbn === book.isbn)) {
                    allBooks.unshift(book);
                    // Make sure it becomes visible: clear search and set filter to 'all'
                    if (typeof searchInput !== 'undefined' && searchInput) {
                        searchInput.value = '';
                    }
                    if (typeof filterSelect !== 'undefined' && filterSelect) {
                        filterSelect.value = 'all';
                    }
                    handleSearch();
                    // Optionally refresh stats to reflect the addition in the header
                    buildCharts();
                    fetchAndDisplayStats();
                }
            } catch (e) {
                console.log('Catalog update after add failed:', e.message);
            }
            
            // Etiket seçenekleri için mevcut/uygun etiket listeleri
            const currentTagIds = new Set((tags || []).map(t => t.id));
            const availableTags = (allTags || []).filter(t => !currentTagIds.has(t.id));

            modalContent.innerHTML = `
                <div class="detail-cover">
                    <img src="${API_BASE}/covers/${book.isbn}" alt="${book.title}" onerror="this.src='/static/default-cover.svg'">
                </div>
                <div class="detail-info" style="max-height: 80vh; overflow-y: auto;">
                    <h2>${book.title}</h2>
                    <p><strong>Yazar:</strong> ${book.author}</p>
                    <p><strong>ISBN:</strong> ${book.isbn}</p>
                    ${book.publish_year ? `<p><strong>Yayın Yılı:</strong> ${book.publish_year}</p>` : ''}
                    ${book.page_count ? `<p><strong>Sayfa:</strong> ${book.page_count}</p>` : ''}
                    ${book.publisher ? `<p><strong>Yayıncı:</strong> ${book.publisher}</p>` : ''}
                    ${book.language ? `<p><strong>Dil:</strong> ${book.language.toUpperCase()}</p>` : ''}
                    ${book.categories && book.categories.length ? `<p><strong>Kategoriler:</strong> ${book.categories.slice(0, 3).join(', ')}</p>` : ''}
                    
                    <div class="book-rating">
                        <span>${ratingStars}${emptyStars}</span>
                        <span>(${rating.average_rating?.toFixed(1) || 0}/5 - ${rating.review_count} değerlendirme)</span>
                    </div>
                    
                    <div class="book-tags">
                        ${tags.length > 0 ? tags.map(tag => `
                            <span class="tag" style="--tag-color: ${tag.color};">
                                ${tag.name}
                                <button class="tag-remove" title="Kaldır" onclick="removeBookTag('${book.isbn}', ${tag.id})">×</button>
                            </span>
                        `).join('') : '<span class="text-muted">Bu kitap için etiket yok.</span>'}
                    </div>
                    <div class="tag-assign">
                        <select id="addTagSelect">
                            ${availableTags.map(t => `<option value="${t.id}">${t.name}</option>`).join('')}
                        </select>
                        <button class="btn btn-sm" onclick="addBookTag('${book.isbn}')" ${availableTags.length === 0 ? 'disabled aria-disabled="true"' : ''} title="${availableTags.length === 0 ? 'Tüm etiketler atanmış' : 'Seçili etiketi ekle'}">
                            <i class="fas fa-tag"></i> Ekle
                        </button>
                    </div>
                    
                    ${aiSummary ? `
                        <div class="ai-summary-section">
                            <h3><i class="fas fa-robot"></i> AI Özeti</h3>
                            <div class="ai-summary">
                                <p>${aiSummary}</p>
                                <button class="btn btn-sm btn-secondary" onclick="regenerateAISummary('${book.isbn}')">
                                    <i class="fas fa-sync"></i> Yeniden Oluştur
                                </button>
                            </div>
                        </div>
                    ` : `
                        <div class="ai-summary-section">
                            <button class="btn btn-sm btn-primary" onclick="generateAISummary('${book.isbn}')">
                                <i class="fas fa-magic"></i> AI Özeti Oluştur
                            </button>
                        </div>
                    `}
                    
                    ${book.description ? `
                        <div class="description-section">
                            <h3><i class="fas fa-info-circle"></i> Açıklama</h3>
                            <p class="description">${book.description}</p>
                        </div>
                    ` : ''}
                    
                    ${similar.length > 0 ? `
                        <div class="similar-books-section">
                            <h3><i class="fas fa-lightbulb"></i> Benzer Kitaplar</h3>
                            <div class="similar-books">
                                ${similar.map(similarBook => `
                                    <div class="similar-book" onclick="window.openDetailModal('${similarBook.isbn}')">
                                        <img src="${similarBook.cover_url || API_BASE + '/covers/' + similarBook.isbn}" alt="${similarBook.title}" onerror="this.src='/static/default-cover.svg'">
                                        <div class="similar-info">
                                            <h4>${similarBook.title}</h4>
                                            <p>${similarBook.author}</p>
                                            ${similarBook.google_rating ? `<div class="rating"><i class="fas fa-star"></i> ${similarBook.google_rating}/5</div>` : ''}
                                        </div>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    ` : ''}
                    
                    <div class="sentiment-section">
                        <h3><i class="fas fa-heart"></i> Duygu Analizi</h3>
                        <div class="review-form">
                            <textarea id="reviewText" placeholder="Bu kitap hakkında ne düşünüyorsunuz?" rows="2"></textarea>
                            <button class="btn btn-sm btn-primary" onclick="analyzeReviewSentiment('${book.isbn}')">
                                <i class="fas fa-search"></i> Analiz Et
                            </button>
                        </div>
                        <div id="sentimentResult" class="sentiment-result"></div>
                    </div>
                    
                    <div class="reviews-section" style="margin-top: 20px;">
                        <h3>Yorumlar</h3>
                        <div class="add-review" style="margin-bottom: 15px;">
                            <input type="text" id="reviewUser" placeholder="Adınız" style="width: 100%; margin-bottom: 5px;">
                            <select id="reviewRating" style="width: 100%; margin-bottom: 5px;">
                                <option value="5">⭐⭐⭐⭐⭐ (5)</option>
                                <option value="4">⭐⭐⭐⭐ (4)</option>
                                <option value="3">⭐⭐⭐ (3)</option>
                                <option value="2">⭐⭐ (2)</option>
                                <option value="1">⭐ (1)</option>
                            </select>
                            <textarea id="reviewComment" placeholder="Yorumunuz..." style="width: 100%; min-height: 60px; margin-bottom: 5px;"></textarea>
                            <button class="btn btn-sm" onclick="addReview('${isbn}')">Yorum Ekle</button>
                        </div>
                        
                        <div class="reviews-list">
                            ${reviews.map(review => `
                                <div class="review-item" style="border-bottom: 1px solid #ddd; padding: 10px 0;">
                                    <strong>${review.user_name}</strong> - ${'⭐'.repeat(review.rating)}
                                    ${review.comment ? `<p>${review.comment}</p>` : ''}
                                    <small>${new Date(review.created_at).toLocaleDateString('tr-TR')}</small>
                                </div>
                            `).join('') || '<p>Henüz yorum yok.</p>'}
                        </div>
                    </div>
                </div>
            `;
            
        } catch (error) {
            if (error?.name === 'AbortError') {
                // Yeni bir modal isteği geldi, bu hatayı kullanıcıya göstermeyelim
                return;
            }
            showToast(`Detaylar yüklenemedi: ${error.message}`, 'error');
        } finally {
            hideModalLoading();
        }
    }
    
    // Yorum ekleme fonksiyonu - global scope'a ekle
    window.addReview = async function(isbn) {
        const user = document.getElementById('reviewUser').value.trim();
        const rating = parseInt(document.getElementById('reviewRating').value);
        const comment = document.getElementById('reviewComment').value.trim();
        
        if (!user) {
            showToast('Lütfen adınızı girin', 'warning');
            return;
        }
        
        try {
            await apiFetch(`/books/${isbn}/reviews`, {
                method: 'POST',
                body: JSON.stringify({
                    user_name: user,
                    rating: rating,
                    comment: comment || null
                })
            });
            
            showToast('Yorumunuz eklendi!', 'success');
            // Modalı yeniden yükle
            showBookDetailsExtended(isbn);
        } catch (error) {
            showToast('Yorum eklenemedi: ' + error.message, 'error');
        }
    };
    
    // Etiket ekleme/çıkarma fonksiyonları - global scope'a ekle
    window.addBookTag = async function(isbn) {
        try {
            const select = document.getElementById('addTagSelect');
            if (!select || !select.value) {
                showToast('Eklenecek etiketi seçin.', 'warning');
                return;
            }
            const tagId = parseInt(select.value);
            await apiFetch(`/books/${isbn}/tags`, {
                method: 'POST',
                body: JSON.stringify(tagId)
            });
            try {
                if (etagStore) {
                    etagStore.delete(`/books/${isbn}/tags`);
                    etagStore.delete('/tags');
                }
            } catch (_) {}
            showToast('Etiket eklendi.', 'success');
            // Modal içeriğini tazele
            await showBookDetailsExtended(isbn);
            // Etiketleri yeniden yükle ve grafikleri güncelle (yenilemeden)
            try { if (typeof loadTags === 'function') { await loadTags(); } } catch (_) {}
            try { buildCharts(); } catch (_) {}
        } catch (error) {
            showToast('Etiket eklenemedi: ' + (error?.message || error), 'error');
        }
    };

    window.removeBookTag = async function(isbn, tagId) {
        try {
            await apiFetch(`/books/${isbn}/tags/${tagId}`, { method: 'DELETE' });
            try {
                if (etagStore) {
                    etagStore.delete(`/books/${isbn}/tags`);
                    etagStore.delete('/tags');
                }
            } catch (_) {}
            showToast('Etiket kaldırıldı.', 'success');
            await showBookDetailsExtended(isbn);
            // Etiketleri yeniden yükle ve grafikleri güncelle (yenilemeden)
            try { if (typeof loadTags === 'function') { await loadTags(); } } catch (_) {}
            try { buildCharts(); } catch (_) {}
        } catch (error) {
            showToast('Etiket kaldırılamadı: ' + (error?.message || error), 'error');
        }
    };

    // openDetailModal fonksiyonunu güncelle - genişletilmiş detayları göster
    window.openDetailModal = async function(isbn) {
        // Modal'ı aç ve loading göster
        if (currentModalController) {
            try { currentModalController.abort(); } catch (e) {}
        }
        currentModalController = new AbortController();
        modal.style.display = 'flex';
        setTimeout(() => modal.classList.add('open'), 10);
        showModalLoading('Kitap detayları yükleniyor...');
        
        // showBookDetailsExtended'i çağır (AbortController sinyali ile)
        await showBookDetailsExtended(isbn, { signal: currentModalController.signal });
    };

    // --- BAŞLANGIÇ ---
    initialize();
});
// Toast notifications (Toastify.js ile)
function showToast(message, type = 'info', options = {}) {
    const theme = document.documentElement.getAttribute('data-theme') || 'dark';
    const duration = options.duration || 3000;
    const gravity = options.gravity || 'top';
    const position = options.position || 'right';

    const palette = theme === 'dark' ? {
        success: '#16a34a',
        error:   '#ef4444',
        warning: '#f59e0b',
        info:    '#3b82f6'
    } : {
        success: '#15803d',
        error:   '#dc2626',
        warning: '#d97706',
        info:    '#2563eb'
    };

    if (typeof Toastify !== 'undefined') {
        try {
            Toastify({
                text: message,
                duration,
                gravity,
                position,
                close: true,
                stopOnFocus: true,
                className: `toastify-${type} theme-${theme}`,
                style: {
                    background: palette[type] || palette.info,
                    color: theme === 'dark' ? '#fff' : '#111',
                    boxShadow: theme === 'dark' ? '0 8px 24px rgba(0,0,0,0.35)' : '0 8px 24px rgba(0,0,0,0.15)',
                    borderRadius: '10px'
                },
                onClick: options.onClick || null,
            }).showToast();
            return;
        } catch (e) {
            // Fallback'a geç
        }
    }

    // Fallback: eski #toast elemanı ile göster
    const fallback = document.getElementById('toast');
    if (!fallback) return;
    fallback.textContent = message;
    fallback.className = `toast toast-${type} show`;
    if (showToast._timer) clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => {
        fallback.classList.remove('show');
    }, duration);
}
window.showToast = showToast;

// AI özet yardımcıları ve eylemleri
function getAISummarySection() {
    return document.querySelector('.ai-summary-section');
}
function setAISummaryButtonLoading(sectionEl, isLoading, kind) {
    const btn = sectionEl ? sectionEl.querySelector('button') : null;
    if (!btn) return;
    if (isLoading) {
        btn.disabled = true;
        btn.dataset.originalLabel = btn.innerHTML;
        btn.innerHTML = kind === 'regen'
            ? '<i class="fas fa-sync fa-spin"></i> Yeniden Oluşturuluyor...'
            : '<i class="fas fa-magic"></i> Oluşturuluyor...';
    } else {
        btn.disabled = false;
        if (btn.dataset.originalLabel) {
            btn.innerHTML = btn.dataset.originalLabel;
            delete btn.dataset.originalLabel;
        }
    }
}

async function generateAISummary(isbn) {
    const section = getAISummarySection();
    try {
        setAISummaryButtonLoading(section, true, 'gen');
        showToast('AI özeti oluşturuluyor...', 'info');
        const response = await window.apiFetch(`/books/${isbn}/generate-summary`, {
            method: 'POST',
            body: JSON.stringify({ force_regenerate: false })
        });
        // Gelecekteki açılışlar için cache temizle
        window.invalidateBookCaches?.(isbn);
        // Modalı kapatmadan AI bölümünü güncelle
        if (section && response?.summary) {
            section.innerHTML = `
                <h3><i class="fas fa-robot"></i> AI Özeti</h3>
                <div class="ai-summary">
                    <p>${response.summary}</p>
                    <button class="btn btn-sm btn-secondary" onclick="regenerateAISummary('${isbn}')">
                        <i class="fas fa-sync"></i> Yeniden Oluştur
                    </button>
                </div>
            `;
        }
        showToast('AI özeti oluşturuldu!', 'success');
    } catch (error) {
        showToast(`AI özeti oluşturulamadı: ${error.message}`, 'error');
    } finally {
        setAISummaryButtonLoading(section, false, 'gen');
    }
}

async function regenerateAISummary(isbn) {
    const section = getAISummarySection();
    try {
        setAISummaryButtonLoading(section, true, 'regen');
        showToast('AI özeti yeniden oluşturuluyor...', 'info');
        const response = await window.apiFetch(`/books/${isbn}/generate-summary`, {
            method: 'POST',
            body: JSON.stringify({ force_regenerate: true })
        });
        // Gelecekteki açılışlar için cache temizle
        window.invalidateBookCaches?.(isbn);
        // Mevcut AI özet paragrafını yerinde güncelle
        if (section && response?.summary) {
            const p = section.querySelector('.ai-summary p');
            if (p) {
                p.textContent = response.summary;
            } else {
                section.innerHTML = `
                    <h3><i class=\"fas fa-robot\"></i> AI Özeti</h3>
                    <div class=\"ai-summary\">\n
                        <p>${response.summary}</p>
                        <button class=\"btn btn-sm btn-secondary\" onclick=\"regenerateAISummary('${isbn}')\">\n
                            <i class=\"fas fa-sync\"></i> Yeniden Oluştur
                        </button>
                    </div>
                `;
            }
        }
        showToast('AI özeti yenilendi!', 'success');
    } catch (error) {
        showToast(`AI özeti yenilenemedi: ${error.message}`, 'error');
    } finally {
        setAISummaryButtonLoading(section, false, 'regen');
    }
}

async function analyzeReviewSentiment(isbn) {
    const reviewText = document.getElementById('reviewText').value.trim();
    if (!reviewText) {
        showToast('Lütfen bir yorum yazın.', 'warning');
        return;
    }
    try {
        showToast('Duygu analizi yapılıyor...', 'info');
        const response = await apiFetch(`/books/${isbn}/analyze-sentiment`, {
            method: 'POST',
            body: JSON.stringify({ text: reviewText })
        });
        const resultDiv = document.getElementById('sentimentResult');
        const emoji = response.label === 'POSITIVE' ? '😊' : response.label === 'NEGATIVE' ? '😞' : '😐';
        const color = response.label === 'POSITIVE' ? 'success' : response.label === 'NEGATIVE' ? 'danger' : 'warning';
        resultDiv.innerHTML = `
            <div class="sentiment-result-card text-${color}">
                <div class="sentiment-emoji">${emoji}</div>
                <div class="sentiment-info">
                    <strong>${response.label}</strong>
                    <small>Güven: ${(response.score * 100).toFixed(1)}%</small>
                </div>
            </div>
        `;
        showToast(`Duygu analizi: ${response.label}`, 'success');
    } catch (error) {
        showToast(`Duygu analizi başarısız: ${error.message}`, 'error');
    }
}

// Global fonksiyonları dışa aktar
window.generateAISummary = generateAISummary;
window.regenerateAISummary = regenerateAISummary;
window.analyzeReviewSentiment = analyzeReviewSentiment;
    
    // API durumunu kontrol et
    async function checkAPIStatus() {
        try {
            // Önce UI öğelerini kontrol et; yoksa ağ çağrısını atla
            const aiSummaryStatus = document.getElementById('aiSummaryStatus');
            const sentimentStatus = document.getElementById('sentimentStatus');
            const recommendationStatus = document.getElementById('recommendationStatus');
            const apiUsage = document.getElementById('apiUsage');

            if (!aiSummaryStatus && !sentimentStatus && !recommendationStatus && !apiUsage) {
                return; // İlgili öğe yoksa API'yi sorgulama
            }

            const stats = await apiFetch('/admin/api-usage');

            const services = stats.services_available;
            
            // Durum güncellemeleri
            if (aiSummaryStatus) {
                aiSummaryStatus.innerHTML = services.hugging_face ? 
                    '<i class="fas fa-circle text-success"></i> Aktif' : 
                    '<i class="fas fa-circle text-danger"></i> Pasif';
            }
            
            if (sentimentStatus) {
                sentimentStatus.innerHTML = services.hugging_face ? 
                    '<i class="fas fa-circle text-success"></i> Aktif' : 
                    '<i class="fas fa-circle text-danger"></i> Pasif';
            }
            
            if (recommendationStatus) {
                recommendationStatus.innerHTML = services.google_books ? 
                    '<i class="fas fa-circle text-success"></i> Aktif' : 
                    '<i class="fas fa-circle text-danger"></i> Pasif';
            }
            
            // API kullanım bilgileri
            if (apiUsage && stats.hugging_face) {
                const hf = stats.hugging_face;
                apiUsage.innerHTML = `
                    <small>
                        <i class="fas fa-robot"></i> AI: ${hf.characters_remaining.toLocaleString()}/${hf.monthly_limit.toLocaleString()} karakter kaldı<br>
                        <i class="fas fa-book"></i> Google Books: ${stats.google_books ? stats.google_books.calls_remaining : 'N/A'}/1000 çağrı kaldı
                    </small>
                `;
            }
        } catch (error) {
            console.log('API status check failed:', error.message);
        }
    }

    // Global fonksiyonlar
    window.generateAISummary = generateAISummary;
    window.regenerateAISummary = regenerateAISummary;
    window.analyzeReviewSentiment = analyzeReviewSentiment;
    // expose cache invalidator for global handlers
    window.invalidateBookCaches = function(isbn) {
        // Inline tanım: kapsam/hoisting sorunlarını önler
        detailCache.delete(isbn);
        aiSummaryCache.delete(isbn);
        // ETag kayıtlarını da temizle
        try {
            if (etagStore) {
                etagStore.delete('/books');
                etagStore.delete(`/books/${isbn}`);
                etagStore.delete(`/books/${isbn}/enhanced`);
                etagStore.delete(`/books/${isbn}/enriched`);
                etagStore.delete(`/books/${isbn}/ai-summary`);
                etagStore.delete(`/books/${isbn}/reviews`);
                etagStore.delete(`/books/${isbn}/rating`);
                etagStore.delete(`/books/${isbn}/tags`);
                etagStore.delete(`/books/${isbn}/similar?limit=3`);
            }
        } catch (_) {}
    };

    // Sayfa yüklendiğinde API durumunu kontrol et
    checkAPIStatus();
    
    // Debug function for modal issues
    window.debugModal = function(isbn) {
        console.log('Debug modal for ISBN:', isbn);
        console.log('Modal element:', modal);
        console.log('Modal content element:', modalContent);
        
        // Test API call
        apiFetch(`/books/${isbn}/enhanced`)
            .then(book => {
                console.log('Book data:', book);
                console.log('Modal will show:', {
                    title: book.title,
                    author: book.author,
                    hasDescription: !!book.description,
                    hasAISummary: !!book.ai_summary,
                    dataSourcesCount: book.data_sources ? book.data_sources.length : 0
                });
            })
            .catch(error => {
                console.error('API error:', error);
            });
    };
    
    // Test modal with sample data
    window.testModal = function() {
        const sampleBook = {
            isbn: '9780134685991',
            title: 'Test Kitap',
            author: 'Test Yazar',
            description: 'Bu bir test açıklamasıdır.',
            page_count: 300,
            google_rating: 4.5,
            data_sources: ['google_books', 'open_library']
        };
        
        modalContent.innerHTML = `
            <div class="enhanced-modal">
                <div class="detail-cover">
                    <img src="/static/default-cover.svg" alt="${sampleBook.title}">
                </div>
                <div class="detail-info">
                    <h2>${sampleBook.title}</h2>
                    <p><strong>Yazar:</strong> ${sampleBook.author}</p>
                    <p><strong>ISBN:</strong> ${sampleBook.isbn}</p>
                    <p><strong>Sayfa:</strong> ${sampleBook.page_count}</p>
                    <div class="description-section">
                        <h3>Açıklama</h3>
                        <p>${sampleBook.description}</p>
                    </div>
                    <div class="modal-actions">
                        <button class="btn btn-secondary" onclick="closeModal()">Kapat</button>
                    </div>
                </div>
            </div>
        `;
        
        modal.style.display = 'flex';
        requestAnimationFrame(() => modal.classList.add('open'));
    };