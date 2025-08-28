import asyncio
from src.library import Library

async def main():
    """Mevcut tüm kitapları yineler ve onları Google Books'tan gelen verilerle zenginleştirir."""
    library = Library()
    books = library.list_books()
    print(f"Zenginleştirilecek {len(books)} kitap bulundu.")

    for book in books:
        print(f"{book.title} ({book.isbn}) zenginleştiriliyor...")
        enriched_book = await library.enrich_book(book)
        if enriched_book:
            print(f"  -> Başarıyla zenginleştirildi.")
        else:
            print(f"  -> Kitap zenginleştirilemedi.")

if __name__ == "__main__":
    asyncio.run(main())