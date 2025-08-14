document.addEventListener('DOMContentLoaded', () => {
    // --- SABİTLER ve DEĞİŞKENLER ---
    const API_BASE = 'http://127.0.0.1:8000';
    const API_KEY = 'super-secret-key';
    const BOOKS_PER_PAGE = 3;

    let allBooks = [];
    let filteredBooks = [];
    let currentIndex = 0;

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

    // --- OLAY DİNLEYİCİLER ---
    addBtn.addEventListener('click', handleAddBook);
    isbnInput.addEventListener('keypress', (e) => e.key === 'Enter' && handleAddBook());
    searchInput.addEventListener('input', handleSearch);
    modalClose.addEventListener('click', closeModal);
    window.addEventListener('click', (e) => e.target === modal && closeModal());
    scrollLeftBtn.addEventListener('click', () => changePage(-1));
    scrollRightBtn.addEventListener('click', () => changePage(1));

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

    // --- ANA İŞLEVLER ---
    async function fetchAndDisplayStats() {
        try {
            const stats = await apiFetch('/stats');
            const statsCard = document.getElementById('statsCard');
            statsCard.innerHTML = `
                <h2>İstatistikler</h2>
                <p><strong>Toplam Kitap:</strong> <span id="statTotal">0</span></p>
                <p><strong>Benzersiz Yazar:</strong> <span id="statAuthors">0</span></p>
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
            await fetchAndDisplayStats();
            allBooks = await apiFetch('/books');
            handleSearch(); // Başlangıçta tüm kitapları filtrele ve render et
            initParticles();
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
        const searchTerm = searchInput.value.toLowerCase();
        filteredBooks = allBooks.filter(book =>
            book.title.toLowerCase().includes(searchTerm) ||
            book.author.toLowerCase().includes(searchTerm)
        );
        currentIndex = 0; // Aramadan sonra slider'ı başa sar
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
            const bookCard = document.createElement('div');
            bookCard.className = 'book-card';
            bookCard.innerHTML = `
                <div class="book-cover">
                    <img src="${API_BASE}/covers/${book.isbn}" alt="${book.title}" onerror="this.src='/static/default-cover.svg'">
                    <div class="book-actions">
                        <button class="action-icon edit-icon" data-isbn="${book.isbn}">✏️</button>
                        <button class="action-icon delete-icon" data-isbn="${book.isbn}">🗑️</button>
                    </div>
                </div>
                <div class="book-info">
                    <h3 class="book-title">${book.title}</h3>
                    <p class="book-author">${book.author}</p>
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

        updateSlider();
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
            document.getElementById('saveUpdateBtn').addEventListener('click', () => handleUpdateBook(isbn));
        } catch (error) {
            showToast(`Düzenleme için kitap yüklenemedi: ${error.message}`, 'error');
        }
    }

    function closeModal() {
        modal.style.display = 'none';
        modalContent.innerHTML = '';
    }

    // --- YARDIMCI FONKSİYONLAR ---
    function showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = `toast toast-${type} show`;
        setTimeout(() => { toast.classList.remove('show'); }, 3000);
    }

    // --- PARÇACIK EFEKTİ ---
    function initParticles() {
        const canvas = document.getElementById('particles');
        const ctx = canvas.getContext('2d');
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        let particlesArray = [];
        const numberOfParticles = 50;
        const particleColor = 'rgba(25, 118, 210, 0.4)'; // Mavi tema rengi

        class Particle {
            constructor() {
                this.x = Math.random() * canvas.width;
                this.y = Math.random() * canvas.height;
                this.size = Math.random() * 2.5 + 1;
                this.speedX = Math.random() * 0.4 - 0.2;
                this.speedY = Math.random() * 0.4 - 0.2;
            }
            update() {
                this.x += this.speedX;
                this.y += this.speedY;
                if (this.x > canvas.width || this.x < 0) this.speedX *= -1;
                if (this.y > canvas.height || this.y < 0) this.speedY *= -1;
            }
            draw() {
                ctx.fillStyle = particleColor;
                ctx.beginPath();
                ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
                ctx.fill();
            }
        }
        function createParticles() {
            particlesArray = [];
            for (let i = 0; i < numberOfParticles; i++) {
                particlesArray.push(new Particle());
            }
        }
        function animateParticles() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            for (let i = 0; i < particlesArray.length; i++) {
                particlesArray[i].update();
                particlesArray[i].draw();
            }
            requestAnimationFrame(animateParticles);
        }
        createParticles();
        animateParticles();
        window.addEventListener('resize', () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            createParticles();
        });
    }

    // --- BAŞLANGIÇ ---
    initialize();
});