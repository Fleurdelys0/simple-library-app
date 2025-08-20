from __future__ import annotations

import json


class Book:
    """Kütüphanedeki tek bir kitap öğesini temsil eder."""

    def __init__(self, title: str, author: str, isbn: str, cover_url: str | None = None, created_at: str | None = None,
                 # Google Books alanları
                 page_count: int | None = None, categories: list | None = None, published_date: str | None = None,
                 publisher: str | None = None, language: str | None = None, description: str | None = None,
                 google_rating: float | None = None, google_rating_count: int | None = None,
                 # AI alanları
                 ai_summary: str | None = None, ai_summary_generated_at: str | None = None,
                 sentiment_score: float | None = None, data_sources: list | None = None) -> None:
        self.title = title.strip()
        self.author = author.strip()
        self.isbn = isbn.strip()
        self.cover_url = cover_url
        self.created_at = created_at
        
        # Google Books alanları
        self.page_count = page_count
        self.categories = categories or []
        self.published_date = published_date
        self.publisher = publisher
        self.language = language or 'tr'
        self.description = description
        self.google_rating = google_rating
        self.google_rating_count = google_rating_count
        
        # AI tarafından oluşturulan alanlar
        self.ai_summary = ai_summary
        self.ai_summary_generated_at = ai_summary_generated_at
        self.sentiment_score = sentiment_score
        self.data_sources = data_sources or []

    def __str__(self) -> str:  # pragma: no cover - string formatting trivial
        return f"{self.title} by {self.author} (ISBN: {self.isbn})"

    def to_dict(self) -> dict:
        return {
            "title": self.title, 
            "author": self.author, 
            "isbn": self.isbn, 
            "cover_url": self.cover_url, 
            "created_at": self.created_at,
            # Google Books alanları
            "page_count": self.page_count,
            "categories": self.categories,
            "published_date": self.published_date,
            "publisher": self.publisher,
            "language": self.language,
            "description": self.description,
            "google_rating": self.google_rating,
            "google_rating_count": self.google_rating_count,
            # AI alanları
            "ai_summary": self.ai_summary,
            "ai_summary_generated_at": self.ai_summary_generated_at,
            "sentiment_score": self.sentiment_score,
            "data_sources": self.data_sources
        }

    @staticmethod
    def from_dict(data: dict) -> "Book":
        # SQLite'tan gelen JSON dize alanlarını Python listelerine normalleştirin
        cats = data.get("categories")
        if isinstance(cats, str):
            try:
                cats = json.loads(cats)
            except Exception:
                cats = [cats] if cats else []

        sources = data.get("data_sources")
        if isinstance(sources, str):
            try:
                sources = json.loads(sources)
            except Exception:
                sources = [sources] if sources else []

        return Book(
            title=data["title"], 
            author=data["author"], 
            isbn=data["isbn"], 
            cover_url=data.get("cover_url"), 
            created_at=data.get("created_at"),
            # Google Books alanları
            page_count=data.get("page_count"),
            categories=cats,
            published_date=data.get("published_date"),
            publisher=data.get("publisher"),
            language=data.get("language"),
            description=data.get("description"),
            google_rating=data.get("google_rating"),
            google_rating_count=data.get("google_rating_count"),
            # AI alanları
            ai_summary=data.get("ai_summary"),
            ai_summary_generated_at=data.get("ai_summary_generated_at"),
            sentiment_score=data.get("sentiment_score"),
            data_sources=sources
        )