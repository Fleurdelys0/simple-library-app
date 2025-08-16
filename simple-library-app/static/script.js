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
    let favoriteBooks = JSON.parse(localStorage.getItem('favorites') || '[]');
    let readingList = JSON.parse(localStorage.getItem('readingList') || '[]');
    let viewMode = localStorage.getItem('viewMode') || 'grid'; // grid veya list
    const REDUCED_MOTION = (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    // Local override: 'on' | 'off' | 'auto' (default 'on' for your device)
    const MOTION_PREF = (localStorage.getItem('motion') || 'on');
    document.documentElement.setAttribute('data-motion', MOTION_PREF);
    const EFFECTIVE_REDUCED = MOTION_PREF === 'off' ? true : (MOTION_PREF === 'on' ? false : REDUCED_MOTION);

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
        
        card.style.setProperty('--rx', `${rotateX}deg`);
        card.style.setProperty('--ry', `${rotateY}deg`);
        card.style.setProperty('--mx', `${spotlightX}%`);
        card.style.setProperty('--my', `${spotlightY}%`);
    }

    function handleTiltLeave(e) {
        const card = e.currentTarget;
        card.style.setProperty('--rx', '0deg');
        card.style.setProperty('--ry', '0deg');
        card.style.setProperty('--mx', '50%');
        card.style.setProperty('--my', '50%');
    }

    // --- API FONKSİYONLARI ---
    async function apiFetch(endpoint, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': API_KEY
            }
        };
        const response = await fetch(`${API_BASE}${endpoint}`, { ...defaultOptions, ...options });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Bilinmeyen bir hata oluştu.' }));
            throw new Error(errorData.detail);
        }
        return response.status !== 204 ? response.json() : null;
    }

    // Backend health kontrolü (bağlantı hatası için hızlı uyarı)
    async function checkBackend() {
        try {
            await fetch(`${API_BASE}/health`, { method: 'GET' });
        } catch (e) {
            showToast('Sunucuya bağlanılamıyor. Lütfen backend\'i çalıştırın (http://127.0.0.1:8000).', 'error');
        }
    }

    // --- ANA İŞLEVLER ---
    async function fetchAndDisplayStats() {
        try {
            const stats = await apiFetch('/stats');
            const statsCard = document.getElementById('statsCard');
            statsCard.innerHTML = `
                <h2><i class="fas fa-chart-bar"></i> İstatistikler</h2>
                <div class="stat-line"><i class="fas fa-book"></i><p><strong>Toplam Kitap:</strong> <span id="statTotal">0</span></p></div>
                <div class="stat-line"><i class="fas fa-user-pen"></i><p><strong>Benzersiz Yazar:</strong> <span id="statAuthors">0</span></p></div>
            `;
            animateNumber(document.getElementById('statTotal'), stats.total_books, 700);
            animateNumber(document.getElementById('statAuthors'), stats.unique_authors, 700);
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
    async function initialize() {
        try {
            checkBackend();
            await fetchAndDisplayStats();
            allBooks = await apiFetch('/books');
            handleSearch(); // Başlangıçta tüm kitapları filtrele ve render et
        } catch (error) {
            showToast(`Kitaplar yüklenemedi: ${error.message}`, 'error');
        }
    }

    async function handleAddBook() {
        const isbn = isbnInput.value.trim();
        if (!isbn) return showToast('Lütfen bir ISBN girin.', 'warning');
        
        addBtn.disabled = true;
        addBtn.textContent = 'Ekleniyor...';
        try {
            const newBook = await apiFetch('/books', { method: 'POST', body: JSON.stringify({ isbn }) });
            allBooks.unshift(newBook);
            isbnInput.value = '';
            handleSearch();
            showToast(`"${newBook.title}" eklendi!`, 'success');
            fetchAndDisplayStats(); // İstatistikleri güncelle
        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            addBtn.disabled = false;
            addBtn.textContent = 'Ekle';
        }
    }

    async function handleDeleteBook(isbn) {
        if (!confirm('Bu kitabı silmek istediğinizden emin misiniz?')) return;
        try {
            await apiFetch(`/books/${isbn}`, { method: 'DELETE' });
            allBooks = allBooks.filter(b => b.isbn !== isbn);
            handleSearch();
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
            const index = allBooks.findIndex(b => b.isbn === isbn);
            if (index !== -1) allBooks[index] = updatedBook;
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
        searchTimeout = setTimeout(() => {
            const searchTerm = searchInput.value.toLowerCase();
            const currentFilter = (filterSelect?.value || 'all');
            // Metin araması
            filteredBooks = allBooks.filter(book =>
                book.title.toLowerCase().includes(searchTerm) ||
                book.author.toLowerCase().includes(searchTerm) ||
                book.isbn.toLowerCase().includes(searchTerm)
            );
            // Ek filtre (favoriler/okuma listesi)
            if (currentFilter === 'favorites') {
                filteredBooks = filteredBooks.filter(b => favoriteBooks.includes(b.isbn));
            } else if (currentFilter === 'reading') {
                filteredBooks = filteredBooks.filter(b => readingList.includes(b.isbn));
            }
            currentIndex = 0; // Aramadan sonra slider'ı başa sar
            renderBooks();
        }, DEBOUNCE_DELAY);
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
            const bookCard = document.createElement('div');
            bookCard.className = 'book-card';
            bookCard.innerHTML = `
                <div class="book-cover">
                    <img src="${API_BASE}/covers/${book.isbn}" alt="${book.title}" loading="lazy" onerror="this.src='/static/default-cover.svg'">
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
                    <div class="book-badges">
                        ${isFavorite ? '<span class="badge badge-favorite">❤️ Favori</span>' : ''}
                        ${isInReadingList ? '<span class="badge badge-reading">📖 Okuma Listesi</span>' : ''}
                    </div>
                </div>
            `;
            bookGrid.appendChild(bookCard);
            bookCard.addEventListener('click', (e) => {
                if (!e.target.closest('.action-icon')) {
                    openDetailModal(book.isbn);
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

        updateSlider();
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
    async function openDetailModal(isbn) {
        try {
            const book = await apiFetch(`/books/${isbn}/enriched`);
            modalContent.innerHTML = `
                <div class="detail-cover">
                     <img src="${API_BASE}/covers/${book.isbn}" alt="${book.title}" onerror="this.src='/static/default-cover.svg'">
                </div>
                <div class="detail-info">
                    <h2>${book.title}</h2>
                    <p><strong>Yazar:</strong> ${book.author}</p>
                    <p><strong>ISBN:</strong> ${book.isbn}</p>
                    ${book.publish_year ? `<p><strong>Yayın Yılı:</strong> ${book.publish_year}</p>` : ''}
                    ${book.publishers ? `<p><strong>Yayınevi:</strong> ${book.publishers.join(', ')}</p>` : ''}
                    ${book.subjects ? `<p><strong>Konular:</strong> ${book.subjects.slice(0, 5).join(', ')}</p>` : ''}
                    ${book.description ? `<p><strong>Açıklama:</strong> ${book.description}</p>` : ''}
                </div>
            `;
            modal.style.display = 'flex';
            // allow transition
            requestAnimationFrame(() => modal.classList.add('open'));
        } catch (error) {
            showToast(`Detaylar yüklenemedi: ${error.message}`, 'error');
        }
    }

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

    // --- YARDIMCI FONKSİYONLAR ---
    function showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = `toast toast-${type} show`;
        setTimeout(() => { toast.classList.remove('show'); }, 3000);
    }

    // Parçacıklar artık theme.js tarafından yönetiliyor.

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
            fetchAndDisplayStats();
            
            // Input'ı temizle
            event.target.value = '';
        } catch (error) {
            showToast('Import hatası: ' + error.message, 'error');
            event.target.value = '';
        }
    }

    // --- BAŞLANGIÇ ---
    initialize();
});