# Python Library Management System

A complete, incremental project that evolves from a CLI app to an API service. It follows four phases: OOP console app, external Open Library integration, FastAPI web API, and final packaging/documentation.

## Setup

1. Clone the repository
2. (Optional) Create a virtual environment
3. Install dependencies

```bash
pip install -r requirements.txt
```

## Phase 1: OOP Console Application

- Core classes: `Book` and `Library`
- Persistence in `library.json`
- CLI menu to add, remove, list, and find books

Run the CLI:

```bash
python main.py
```

## Phase 2: External API Integration

- Uses Open Library Books API to add books by ISBN
- Handles network errors and 404 responses gracefully

When choosing "Add Book", enter only the ISBN (e.g., `9780321765723`).

## Phase 3: FastAPI Web API

Start the API server:

```bash
uvicorn api:app --reload
```

Open interactive docs at `http://127.0.0.1:8000/docs`.

### Endpoints

- `GET /books`: List all books
- `POST /books` with JSON body `{ "isbn": "9780321765723" }`: Adds a book by ISBN
- `DELETE /books/{isbn}`: Deletes the specified book

Use the `LIBRARY_DATA_FILE` environment variable to change the persistence file for the API, e.g.:

```bash
set LIBRARY_DATA_FILE=./my_library.json  # Windows PowerShell: $env:LIBRARY_DATA_FILE="./my_library.json"
uvicorn api:app --reload
```

## Testing

Run unit tests:

```bash
pytest -q
```

Tests cover core library features, API integration logic (with mocked HTTP calls), and API endpoints.

## CLI Notları

Varsayılan CLI `main.py` üzerinden menü tabanlıdır. Web arayüzünü açmak için menüde "Open Web UI" seçeneğini kullanabilirsiniz.

## Configuration

Environment değişkenleri:

- `LIBRARY_DATA_FILE`: veri dosyası (varsayılan `library.json`)
- `OPENLIBRARY_TIMEOUT`: Open Library istek zaman aşımı (saniye)
- `API_HOST`, `API_PORT`: FastAPI host ve port (UI bağlantısı için de kullanılır)

## React Frontend (optional)

Yeni bir React UI `frontend/` klasörü altında gelir. Çalıştırmak için:

```bash
cd frontend
npm i
npm run dev
```

Geliştirme sırasında `/books` istekleri `http://127.0.0.1:8000` adresine proxylanır. Arka ucu `uvicorn api:app --reload` ile başlatmayı unutmayın.

