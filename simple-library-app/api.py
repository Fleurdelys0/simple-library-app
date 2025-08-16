import os
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import json

import httpx
from fastapi import FastAPI, HTTPException, Body, Query, Depends, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from functools import lru_cache
import hashlib

from library import Library, ExternalServiceError
from book import Book
from config import settings


import os
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import json
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Body, Query, Depends, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from functools import lru_cache
import hashlib

from library import Library, ExternalServiceError
from book import Book
from config import settings


# Global variable for the library instance
library: Library = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup event
    global library
    library = Library(db_file="library.db")
    yield
    # Shutdown event
    if library:
        library.close()

app = FastAPI(title="Library Management API", lifespan=lifespan)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Security ---
api_key_header = APIKeyHeader(name="X-API-Key")

def get_api_key(api_key: str = Security(api_key_header)):
    """Dependency to validate the API key."""
    if api_key == settings.api_key:
        return api_key
    else:
        raise HTTPException(
            status_code=403,
            detail="Could not validate credentials",
        )

# --- Models ---
class BookModel(BaseModel):
    title: str
    author: str
    isbn: str
    cover_url: str | None = None

class BookCreateModel(BaseModel):
    isbn: str | None = Field(default=None, description="Provide for auto-fetch")
    title: str | None = Field(default=None, description="Manual title if not using ISBN")
    author: str | None = Field(default=None, description="Manual author if not using ISBN")

class StatsModel(BaseModel):
    total_books: int
    unique_authors: int

# --- Helper Functions ---
def _add_book_to_library(book: Book) -> BookModel:
    """Helper function to add a book to the library and handle exceptions."""
    try:
        library.add_book(book)
        return BookModel(**book.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- API Endpoints ---
@app.get("/covers/{isbn}")
async def get_book_cover(isbn: str):
    """Proxy book cover from Open Library to avoid CORS issues."""
    import httpx
    
    cover_url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(cover_url, timeout=10.0)
            # Open Library redirects to a tiny placeholder image if the cover is not found.
            # We check the content length to see if we got a real cover or a placeholder.
            if response.status_code == 200 and len(response.content) > 1000:
                from fastapi.responses import Response
                return Response(
                    content=response.content,
                    media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"}  # Cache for 24 hours
                )
            else:
                # Return default cover if not found or content is too small
                return FileResponse('static/default-cover.svg', media_type="image/svg+xml")
    except Exception:
        # Return default cover on error
        return FileResponse('static/default-cover.svg', media_type="image/svg+xml")

@app.get("/stats", response_model=StatsModel)
def get_library_stats():
    """Get basic statistics about the library."""
    stats = library.get_statistics()
    return StatsModel(total_books=stats["total_books"], unique_authors=stats["unique_authors"])

# --- Pagination Models ---
class PaginatedResponse(BaseModel):
    items: List[BookModel]
    total: int
    page: int
    page_size: int
    total_pages: int

class AdvancedSearchParams(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    isbn: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None

# --- Cache Helper ---
cache_store: Dict[str, tuple[Any, datetime]] = {}

def cache_response(key: str, data: Any, ttl_seconds: int = 300):
    """Simple in-memory cache with TTL."""
    expiry = datetime.now() + timedelta(seconds=ttl_seconds)
    cache_store[key] = (data, expiry)

def get_cached_response(key: str) -> Optional[Any]:
    """Get cached response if not expired."""
    if key in cache_store:
        data, expiry = cache_store[key]
        if datetime.now() < expiry:
            return data
        else:
            del cache_store[key]
    return None

@app.get("/books", response_model=List[BookModel])
def get_books(
    q: Optional[str] = Query(None, description="Search query"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip")
):
    """Get a list of all books with search, limit and offset."""
    # Check cache first
    cache_key = f"books:{q}:{limit}:{offset}"
    cached = get_cached_response(cache_key)
    if cached:
        return cached
    
    if q:
        books = library.search_books(q)
    else:
        books = library.list_books()
    
    # Apply pagination
    paginated_books = books[offset:offset + limit]
    result = [BookModel(**b.to_dict()) for b in paginated_books]
    
    # Cache the result
    cache_response(cache_key, result, ttl_seconds=60)
    return result

@app.get("/books/paginated", response_model=PaginatedResponse)
def get_books_paginated(
    q: Optional[str] = Query(None, description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page")
):
    """Get paginated list of books."""
    if q:
        books = library.search_books(q)
    else:
        books = library.list_books()
    
    total = len(books)
    total_pages = (total + page_size - 1) // page_size
    start = (page - 1) * page_size
    end = start + page_size
    
    paginated_books = books[start:end]
    
    return PaginatedResponse(
        items=[BookModel(**b.to_dict()) for b in paginated_books],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )

@app.post("/books/search/advanced", response_model=List[BookModel])
def advanced_search(params: AdvancedSearchParams):
    """Advanced search with multiple filters."""
    books = library.list_books()
    
    # Filter by title
    if params.title:
        books = [b for b in books if params.title.lower() in b.title.lower()]
    
    # Filter by author
    if params.author:
        books = [b for b in books if params.author.lower() in b.author.lower()]
    
    # Filter by ISBN
    if params.isbn:
        books = [b for b in books if params.isbn in b.isbn]
    
    return [BookModel(**b.to_dict()) for b in books]



@app.get("/books/{isbn}", response_model=BookModel)
def get_book(isbn: str):
    """Get a single book by its ISBN."""
    book = library.find_book(isbn)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")
    return BookModel(**book.to_dict())

@app.post("/books", response_model=BookModel, dependencies=[Depends(get_api_key)])
def add_book(payload: BookCreateModel):
    """Add a new book to the library, either by ISBN or by providing all details."""
    # If only ISBN is provided, fetch book details from Open Library
    if payload.isbn and not payload.title:
        try:
            # This function already adds the book to the library and saves it.
            book = library.add_book_by_isbn(payload.isbn)
            # So we just need to return it, converted to the response model.
            return BookModel(**book.to_dict())
        except ValueError as e:
            # This correctly catches the "already exists" error from add_book_by_isbn
            raise HTTPException(status_code=400, detail=str(e))
        except (ExternalServiceError, LookupError):
            # Fallback: create a minimal book entry when external lookup fails.
            cover_url = f"http://{settings.api_host}:{settings.api_port}/covers/{payload.isbn}"
            fallback_book = Book(title="Unknown Title", author="Unknown Author", isbn=payload.isbn, cover_url=cover_url)
            try:
                library.add_book(fallback_book)
                return BookModel(**fallback_book.to_dict())
            except ValueError:
                # If it already exists, return the existing record
                existing = library.find_book(payload.isbn)
                if existing:
                    return BookModel(**existing.to_dict())
                # If not found for some reason, surface a generic error
                raise HTTPException(status_code=400, detail=f"Book with ISBN {payload.isbn} already exists.")
    # If all details are provided, add the book directly
    elif payload.isbn and payload.title and payload.author:
        cover_url = f"http://{settings.api_host}:{settings.api_port}/covers/{payload.isbn}"
        book = Book(title=payload.title, author=payload.author, isbn=payload.isbn, cover_url=cover_url)
        return _add_book_to_library(book)
    # Otherwise, the request is invalid
    else:
        raise HTTPException(status_code=422, detail="Provide ISBN, or ISBN, Title, and Author.")

@app.delete("/books/{isbn}", dependencies=[Depends(get_api_key)])
def delete_book(isbn: str):
    """Delete a book from the library by its ISBN."""
    if not library.remove_book(isbn):
        raise HTTPException(status_code=404, detail="Book not found.")
    return {"message": "Book removed."}

class UpdateBookModel(BaseModel):
    title: str | None = None
    author: str | None = None

@app.put("/books/{isbn}", response_model=BookModel, dependencies=[Depends(get_api_key)])
def update_book(isbn: str, update: UpdateBookModel):
    """Update a book's title and/or author by its ISBN."""
    if not update.title and not update.author:
        raise HTTPException(status_code=400, detail="Provide title and/or author to update.")
    book = library.update_book(isbn, title=update.title, author=update.author)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")
    return BookModel(**book.to_dict())

class BookEnrichedModel(BookModel):
    cover_url: str | None = None
    publish_year: int | None = None
    publishers: List[str] | None = None
    subjects: List[str] | None = None
    description: str | None = None

@app.get("/books/{isbn}/enriched", response_model=BookEnrichedModel)
def get_enriched_book(isbn: str):
    """Get enriched book details from Open Library."""
    book = library.find_book(isbn)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")
    
    try:
        enriched_data = library.fetch_enriched_details(isbn)
        book_dict = book.to_dict()
        book_dict.update(enriched_data)
        return BookEnrichedModel(**book_dict)
    except Exception:
        # Return basic book info if enrichment fails
        book_dict = book.to_dict()
        book_dict['cover_url'] = f"http://{settings.api_host}:{settings.api_port}/covers/{isbn}"
        return BookEnrichedModel(**book_dict)

# --- Export/Import Endpoints ---
@app.get("/export/json")
def export_books_json():
    """Export all books as JSON."""
    books = library.list_books()
    data = [b.to_dict() for b in books]
    return JSONResponse(
        content=data,
        headers={
            "Content-Disposition": f"attachment; filename=library_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        }
    )

@app.get("/export/csv")
def export_books_csv():
    """Export all books as CSV."""
    import csv
    import io
    
    books = library.list_books()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=['isbn', 'title', 'author'])
    writer.writeheader()
    
    for book in books:
        writer.writerow({
            'isbn': book.isbn,
            'title': book.title,
            'author': book.author
        })
    
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=library_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    )

@app.post("/import/json", dependencies=[Depends(get_api_key)])
async def import_books_json(request: Request):
    """Import books from JSON."""
    try:
        data = await request.json()
        imported_count = 0
        errors = []
        
        for item in data:
            try:
                if all(k in item for k in ['isbn', 'title', 'author']):
                    # Import sırasında cover_url'i kontrol et, yoksa None olarak bırak
                    cover_url = item.get('cover_url')
                    if not cover_url:
                        cover_url = None  # Cover URL'i zorla oluşturma
                    
                    book = Book(
                        title=item['title'],
                        author=item['author'],
                        isbn=item['isbn'],
                        cover_url=cover_url
                    )
                    library.add_book(book)
                    imported_count += 1
            except ValueError as e:
                errors.append(f"ISBN {item.get('isbn', 'unknown')}: {str(e)}")
        
        return {
            "imported": imported_count,
            "errors": errors,
            "message": f"Successfully imported {imported_count} books"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")

# --- Advanced Statistics ---
class ExtendedStatsModel(BaseModel):
    total_books: int
    unique_authors: int
    most_common_author: Optional[str]
    books_by_author: Dict[str, int]
    recent_additions: List[BookModel]
    total_favorites: int = 0
    total_reading_list: int = 0

@app.get("/stats/extended", response_model=ExtendedStatsModel)
def get_extended_stats():
    """Get extended statistics about the library."""
    books = library.list_books()
    stats = library.get_statistics()
    
    # Count books by author
    author_counts: Dict[str, int] = {}
    for book in books:
        author_counts[book.author] = author_counts.get(book.author, 0) + 1
    
    # Find most common author
    most_common_author = None
    if author_counts:
        # use explicit lambda to avoid typing issues with dict.get overloads
        most_common_author = max(author_counts, key=lambda k: author_counts[k])
    
    # Get recent additions (last 5)
    recent_books = books[-5:] if len(books) > 0 else []
    
    return ExtendedStatsModel(
        total_books=stats["total_books"],
        unique_authors=stats["unique_authors"],
        most_common_author=most_common_author,
        books_by_author=dict(sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
        recent_additions=[BookModel(**b.to_dict()) for b in recent_books]
    )

# --- Health Check ---
@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "total_books": len(library.list_books())
    }

@app.post("/test-post")
def test_post():
    return {"message": "POST request received successfully!"}

# --- Static Files ---
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    """Serve the main HTML page."""
    return FileResponse('static/index.html')

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Security ---
api_key_header = APIKeyHeader(name="X-API-Key")

def get_api_key(api_key: str = Security(api_key_header)):
    """Dependency to validate the API key."""
    if api_key == settings.api_key:
        return api_key
    else:
        raise HTTPException(
            status_code=403,
            detail="Could not validate credentials",
        )

# --- Models ---
class BookModel(BaseModel):
    title: str
    author: str
    isbn: str
    cover_url: str | None = None

class BookCreateModel(BaseModel):
    isbn: str | None = Field(default=None, description="Provide for auto-fetch")
    title: str | None = Field(default=None, description="Manual title if not using ISBN")
    author: str | None = Field(default=None, description="Manual author if not using ISBN")

class StatsModel(BaseModel):
    total_books: int
    unique_authors: int

# --- Helper Functions ---
def _add_book_to_library(book: Book) -> BookModel:
    """Helper function to add a book to the library and handle exceptions."""
    try:
        library.add_book(book)
        return BookModel(**book.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- API Endpoints ---
@app.get("/covers/{isbn}")
async def get_book_cover(isbn: str):
    """Proxy book cover from Open Library to avoid CORS issues."""
    import httpx
    
    cover_url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(cover_url, timeout=10.0)
            # Open Library redirects to a tiny placeholder image if the cover is not found.
            # We check the content length to see if we got a real cover or a placeholder.
            if response.status_code == 200 and len(response.content) > 1000:
                from fastapi.responses import Response
                return Response(
                    content=response.content,
                    media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"}  # Cache for 24 hours
                )
            else:
                # Return default cover if not found or content is too small
                return FileResponse('static/default-cover.svg', media_type="image/svg+xml")
    except Exception:
        # Return default cover on error
        return FileResponse('static/default-cover.svg', media_type="image/svg+xml")

@app.get("/stats", response_model=StatsModel)
def get_library_stats():
    """Get basic statistics about the library."""
    stats = library.get_statistics()
    return StatsModel(total_books=stats["total_books"], unique_authors=stats["unique_authors"])

# --- Pagination Models ---
class PaginatedResponse(BaseModel):
    items: List[BookModel]
    total: int
    page: int
    page_size: int
    total_pages: int

class AdvancedSearchParams(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    isbn: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None

# --- Cache Helper ---
cache_store: Dict[str, tuple[Any, datetime]] = {}

def cache_response(key: str, data: Any, ttl_seconds: int = 300):
    """Simple in-memory cache with TTL."""
    expiry = datetime.now() + timedelta(seconds=ttl_seconds)
    cache_store[key] = (data, expiry)

def get_cached_response(key: str) -> Optional[Any]:
    """Get cached response if not expired."""
    if key in cache_store:
        data, expiry = cache_store[key]
        if datetime.now() < expiry:
            return data
        else:
            del cache_store[key]
    return None

@app.get("/books", response_model=List[BookModel])
def get_books(
    q: Optional[str] = Query(None, description="Search query"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip")
):
    """Get a list of all books with search, limit and offset."""
    # Check cache first
    cache_key = f"books:{q}:{limit}:{offset}"
    cached = get_cached_response(cache_key)
    if cached:
        return cached
    
    if q:
        books = library.search_books(q)
    else:
        books = library.list_books()
    
    # Apply pagination
    paginated_books = books[offset:offset + limit]
    result = [BookModel(**b.to_dict()) for b in paginated_books]
    
    # Cache the result
    cache_response(cache_key, result, ttl_seconds=60)
    return result

@app.get("/books/paginated", response_model=PaginatedResponse)
def get_books_paginated(
    q: Optional[str] = Query(None, description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page")
):
    """Get paginated list of books."""
    if q:
        books = library.search_books(q)
    else:
        books = library.list_books()
    
    total = len(books)
    total_pages = (total + page_size - 1) // page_size
    start = (page - 1) * page_size
    end = start + page_size
    
    paginated_books = books[start:end]
    
    return PaginatedResponse(
        items=[BookModel(**b.to_dict()) for b in paginated_books],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )

@app.post("/books/search/advanced", response_model=List[BookModel])
def advanced_search(params: AdvancedSearchParams):
    """Advanced search with multiple filters."""
    books = library.list_books()
    
    # Filter by title
    if params.title:
        books = [b for b in books if params.title.lower() in b.title.lower()]
    
    # Filter by author
    if params.author:
        books = [b for b in books if params.author.lower() in b.author.lower()]
    
    # Filter by ISBN
    if params.isbn:
        books = [b for b in books if params.isbn in b.isbn]
    
    return [BookModel(**b.to_dict()) for b in books]



@app.get("/books/{isbn}", response_model=BookModel)
def get_book(isbn: str):
    """Get a single book by its ISBN."""
    book = library.find_book(isbn)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")
    return BookModel(**book.to_dict())

@app.post("/books", response_model=BookModel, dependencies=[Depends(get_api_key)])
def add_book(payload: BookCreateModel):
    """Add a new book to the library, either by ISBN or by providing all details."""
    # If only ISBN is provided, fetch book details from Open Library
    if payload.isbn and not payload.title:
        try:
            # This function already adds the book to the library and saves it.
            book = library.add_book_by_isbn(payload.isbn)
            # So we just need to return it, converted to the response model.
            return BookModel(**book.to_dict())
        except ValueError as e:
            # This correctly catches the "already exists" error from add_book_by_isbn
            raise HTTPException(status_code=400, detail=str(e))
        except (ExternalServiceError, LookupError):
            # Fallback: create a minimal book entry when external lookup fails.
            cover_url = f"http://{settings.api_host}:{settings.api_port}/covers/{payload.isbn}"
            fallback_book = Book(title="Unknown Title", author="Unknown Author", isbn=payload.isbn, cover_url=cover_url)
            try:
                library.add_book(fallback_book)
                return BookModel(**fallback_book.to_dict())
            except ValueError:
                # If it already exists, return the existing record
                existing = library.find_book(payload.isbn)
                if existing:
                    return BookModel(**existing.to_dict())
                # If not found for some reason, surface a generic error
                raise HTTPException(status_code=400, detail=f"Book with ISBN {payload.isbn} already exists.")
    # If all details are provided, add the book directly
    elif payload.isbn and payload.title and payload.author:
        cover_url = f"http://{settings.api_host}:{settings.api_port}/covers/{payload.isbn}"
        book = Book(title=payload.title, author=payload.author, isbn=payload.isbn, cover_url=cover_url)
        return _add_book_to_library(book)
    # Otherwise, the request is invalid
    else:
        raise HTTPException(status_code=422, detail="Provide ISBN, or ISBN, Title, and Author.")

@app.delete("/books/{isbn}", dependencies=[Depends(get_api_key)])
def delete_book(isbn: str):
    """Delete a book from the library by its ISBN."""
    if not library.remove_book(isbn):
        raise HTTPException(status_code=404, detail="Book not found.")
    return {"message": "Book removed."}

class UpdateBookModel(BaseModel):
    title: str | None = None
    author: str | None = None

@app.put("/books/{isbn}", response_model=BookModel, dependencies=[Depends(get_api_key)])
def update_book(isbn: str, update: UpdateBookModel):
    """Update a book's title and/or author by its ISBN."""
    if not update.title and not update.author:
        raise HTTPException(status_code=400, detail="Provide title and/or author to update.")
    book = library.update_book(isbn, title=update.title, author=update.author)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")
    return BookModel(**book.to_dict())

class BookEnrichedModel(BookModel):
    cover_url: str | None = None
    publish_year: int | None = None
    publishers: List[str] | None = None
    subjects: List[str] | None = None
    description: str | None = None

@app.get("/books/{isbn}/enriched", response_model=BookEnrichedModel)
def get_enriched_book(isbn: str):
    """Get enriched book details from Open Library."""
    book = library.find_book(isbn)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")
    
    try:
        enriched_data = library.fetch_enriched_details(isbn)
        book_dict = book.to_dict()
        book_dict.update(enriched_data)
        return BookEnrichedModel(**book_dict)
    except Exception:
        # Return basic book info if enrichment fails
        book_dict = book.to_dict()
        book_dict['cover_url'] = f"http://{settings.api_host}:{settings.api_port}/covers/{isbn}"
        return BookEnrichedModel(**book_dict)

# --- Export/Import Endpoints ---
@app.get("/export/json")
def export_books_json():
    """Export all books as JSON."""
    books = library.list_books()
    data = [b.to_dict() for b in books]
    return JSONResponse(
        content=data,
        headers={
            "Content-Disposition": f"attachment; filename=library_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        }
    )

@app.get("/export/csv")
def export_books_csv():
    """Export all books as CSV."""
    import csv
    import io
    
    books = library.list_books()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=['isbn', 'title', 'author'])
    writer.writeheader()
    
    for book in books:
        writer.writerow({
            'isbn': book.isbn,
            'title': book.title,
            'author': book.author
        })
    
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=library_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    )

@app.post("/import/json", dependencies=[Depends(get_api_key)])
async def import_books_json(request: Request):
    """Import books from JSON."""
    try:
        data = await request.json()
        imported_count = 0
        errors = []
        
        for item in data:
            try:
                if all(k in item for k in ['isbn', 'title', 'author']):
                    # Import sırasında cover_url'i kontrol et, yoksa None olarak bırak
                    cover_url = item.get('cover_url')
                    if not cover_url:
                        cover_url = None  # Cover URL'i zorla oluşturma
                    
                    book = Book(
                        title=item['title'],
                        author=item['author'],
                        isbn=item['isbn'],
                        cover_url=cover_url
                    )
                    library.add_book(book)
                    imported_count += 1
            except ValueError as e:
                errors.append(f"ISBN {item.get('isbn', 'unknown')}: {str(e)}")
        
        return {
            "imported": imported_count,
            "errors": errors,
            "message": f"Successfully imported {imported_count} books"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")

# --- Advanced Statistics ---
class ExtendedStatsModel(BaseModel):
    total_books: int
    unique_authors: int
    most_common_author: Optional[str]
    books_by_author: Dict[str, int]
    recent_additions: List[BookModel]
    total_favorites: int = 0
    total_reading_list: int = 0

@app.get("/stats/extended", response_model=ExtendedStatsModel)
def get_extended_stats():
    """Get extended statistics about the library."""
    books = library.list_books()
    stats = library.get_statistics()
    
    # Count books by author
    author_counts: Dict[str, int] = {}
    for book in books:
        author_counts[book.author] = author_counts.get(book.author, 0) + 1
    
    # Find most common author
    most_common_author = None
    if author_counts:
        # use explicit lambda to avoid typing issues with dict.get overloads
        most_common_author = max(author_counts, key=lambda k: author_counts[k])
    
    # Get recent additions (last 5)
    recent_books = books[-5:] if len(books) > 0 else []
    
    return ExtendedStatsModel(
        total_books=stats["total_books"],
        unique_authors=stats["unique_authors"],
        most_common_author=most_common_author,
        books_by_author=dict(sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
        recent_additions=[BookModel(**b.to_dict()) for b in recent_books]
    )

# --- Health Check ---
@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "total_books": len(library.list_books())
    }

@app.post("/test-post")
def test_post():
    return {"message": "POST request received successfully!"}

# --- Static Files ---
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    """Serve the main HTML page."""
    return FileResponse('static/index.html')