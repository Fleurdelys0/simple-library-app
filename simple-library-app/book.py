from __future__ import annotations


class Book:
    """Represents a single book item in the library."""

    def __init__(self, title: str, author: str, isbn: str, cover_url: str | None = None) -> None:
        self.title = title.strip()
        self.author = author.strip()
        self.isbn = isbn.strip()
        self.cover_url = cover_url

    def __str__(self) -> str:  # pragma: no cover - string formatting trivial
        return f"{self.title} by {self.author} (ISBN: {self.isbn})"

    def to_dict(self) -> dict:
        return {"title": self.title, "author": self.author, "isbn": self.isbn, "cover_url": self.cover_url}

    @staticmethod
    def from_dict(data: dict) -> "Book":
        return Book(title=data["title"], author=data["author"], isbn=data["isbn"], cover_url=data.get("cover_url"))