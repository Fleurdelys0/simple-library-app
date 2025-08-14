import os
from typing import List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Body, Query, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from library import Library, ExternalServiceError
from book import Book
from config import settings


library = Library()

app = FastAPI(title="Library Management API")

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

@app.get("/books", response_model=List[BookModel])
def get_books(q: Optional[str] = None):
    """Get a list of all books, with optional search query."""
    if q:
        books = library.search_books(q)
    else:
        books = library.list_books()
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
        except ExternalServiceError:
            raise HTTPException(status_code=503, detail="External service unavailable.")
        except LookupError:
            raise HTTPException(status_code=404, detail=f"Book not found for ISBN {payload.isbn}.")
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

@app.post("/test-post")
def test_post():
    return {"message": "POST request received successfully!"}

# --- Static Files ---
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    """Serve the main HTML page."""
    return FileResponse('static/index.html')