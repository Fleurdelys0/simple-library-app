#!/usr/bin/env python3
"""
Test script for Google Books API integration
Bu script Google Books servisini test etmek için kullanılır.
"""

import asyncio
import os
from dotenv import load_dotenv
from google_books_service import GoogleBooksService
import pytest

# Mark the entire module as integration to allow skipping by default
pytestmark = pytest.mark.integration

# Load environment variables from .env file
load_dotenv()


async def test_google_books_service():
    """Test Google Books service functionality"""
    print("📚 Google Books API Test Başlıyor...")
    print("=" * 50)
    
    # Initialize service
    service = GoogleBooksService()
    
    # Check if service is available
    if not service.is_available():
        print("❌ Google Books servisi kullanılamıyor.")
        print("   - ENABLE_GOOGLE_BOOKS=true ayarlandı mı?")
        return
    
    print("✅ Google Books servisi hazır!")
    print(f"   - API Key: {'✅ Ayarlandı' if service.api_key else '❌ Ayarlanmadı (çalışır ama düşük limit)'}")
    print(f"   - Günlük Limit: {service.daily_limit:,} çağrı")
    
    # Get usage stats
    stats = service.get_usage_stats()
    print(f"   - Kullanılan: {stats['daily_calls_used']:,} çağrı")
    print(f"   - Kalan: {stats['calls_remaining']:,} çağrı")
    print()
    
    # Test 1: Fetch book by ISBN
    print("📖 Test 1: ISBN ile Kitap Getirme")
    print("-" * 40)
    
    test_isbns = [
        "9780321765723",  # Effective Java
        "9781491950357",  # Learning Python
        "9780134685991",  # Effective Modern C++
        "9780596009205",  # Head First Design Patterns
        "9781234567890"   # Invalid ISBN
    ]
    
    for i, isbn in enumerate(test_isbns, 1):
        print(f"Test {i}: ISBN {isbn}")
        try:
            book = await service.fetch_book_by_isbn(isbn)
            if book:
                print(f"   ✅ Bulundu: {book.title}")
                print(f"      Yazar(lar): {', '.join(book.authors)}")
                print(f"      Sayfa: {book.page_count or 'Bilinmiyor'}")
                print(f"      Kategori: {', '.join(book.categories[:2]) if book.categories else 'Bilinmiyor'}")
                print(f"      Yayın: {book.published_date or 'Bilinmiyor'}")
                if book.average_rating:
                    print(f"      Puan: {book.average_rating}/5 ({book.ratings_count} değerlendirme)")
            else:
                print("   ❌ Bulunamadı")
        except Exception as e:
            print(f"   ❌ Hata: {e}")
        print()
    
    # Test 2: Search books
    print("🔍 Test 2: Kitap Arama")
    print("-" * 40)
    
    search_queries = [
        "Python programming",
        "JavaScript",
        "Machine Learning",
        "Yapay Zeka"
    ]
    
    for i, query in enumerate(search_queries, 1):
        print(f"Arama {i}: '{query}'")
        try:
            books = await service.search_books(query, max_results=3)
            if books:
                print(f"   ✅ {len(books)} kitap bulundu:")
                for j, book in enumerate(books, 1):
                    print(f"      {j}. {book.title}")
                    print(f"         Yazar: {', '.join(book.authors[:2])}")
                    if book.published_date:
                        print(f"         Yayın: {book.published_date}")
            else:
                print("   ❌ Kitap bulunamadı")
        except Exception as e:
            print(f"   ❌ Hata: {e}")
        print()
    
    # Test 3: Similar books
    print("🔗 Test 3: Benzer Kitap Önerileri")
    print("-" * 40)
    
    reference_isbn = "9780321765723"  # Effective Java
    print(f"Referans ISBN: {reference_isbn}")
    
    try:
        similar_books = await service.get_similar_books(reference_isbn, max_results=3)
        if similar_books:
            print(f"   ✅ {len(similar_books)} benzer kitap bulundu:")
            for i, book in enumerate(similar_books, 1):
                print(f"      {i}. {book.title}")
                print(f"         Yazar: {', '.join(book.authors[:2])}")
                print(f"         Kategori: {', '.join(book.categories[:2]) if book.categories else 'Bilinmiyor'}")
        else:
            print("   ❌ Benzer kitap bulunamadı")
    except Exception as e:
        print(f"   ❌ Hata: {e}")
    print()
    
    # Final stats
    print("📊 Final İstatistikler")
    print("-" * 40)
    final_stats = service.get_usage_stats()
    print(f"Günlük kullanım: {final_stats['daily_calls_used']:,}/{final_stats['daily_limit']:,}")
    print(f"Kalan çağrı: {final_stats['calls_remaining']:,}")
    print(f"Kullanım oranı: {final_stats['usage_percentage']:.1f}%")
    print(f"30 günlük çağrı: {final_stats['total_calls_30_days']}")
    print(f"Başarı oranı: {final_stats['success_rate']:.1f}%")
    print(f"Ortalama yanıt süresi: {final_stats['avg_response_time_ms']:.0f}ms")
    print()
    
    print("🎉 Test tamamlandı!")


if __name__ == "__main__":
    # API key kontrolü
    api_key = os.getenv("GOOGLE_BOOKS_API_KEY")
    if not api_key:
        print("ℹ️  GOOGLE_BOOKS_API_KEY ayarlanmamış - API key olmadan da çalışır!")
        print("   Daha yüksek limitler için Google Cloud Console'dan ücretsiz key alabilirsiniz.")
        print("   https://console.cloud.google.com/apis/library/books.googleapis.com")
        print()
    else:
        print(f"✅ Google Books API key ayarlandı: {api_key[:10]}...")
        print()
    
    # Run the test
    asyncio.run(test_google_books_service())