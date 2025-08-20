#!/usr/bin/env python3
"""
Test script for Enhanced API integration (Google Books + Hugging Face + Open Library)
Bu script tüm API'lerin birlikte çalışmasını test eder.
"""

import asyncio
import os
import tempfile
from dotenv import load_dotenv
from library import Library
from book import Book
import pytest

# Mark the entire module as integration to allow skipping by default
pytestmark = pytest.mark.integration

# Load environment variables from .env file
load_dotenv()


async def test_enhanced_integration():
    """Test enhanced API integration with all services"""
    print("🚀 Enhanced API Integration Test Başlıyor...")
    print("=" * 60)
    
    # Set environment variables
    os.environ['ENABLE_GOOGLE_BOOKS'] = 'true'
    os.environ['ENABLE_AI_FEATURES'] = 'true'
    os.environ['HUGGING_FACE_API_KEY'] = os.getenv('HUGGING_FACE_API_KEY', '')
    
    # Create a temporary database for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
        db_path = tmp_db.name
    
    try:
        # Initialize library with test database
        library = Library(db_file=db_path)
        
        # Check service availability
        stats = library.get_enhanced_usage_stats()
        print("📊 Servis Durumu:")
        print(f"   Google Books: {'✅ Aktif' if stats['services_available']['google_books'] else '❌ Pasif'}")
        print(f"   Hugging Face: {'✅ Aktif' if stats['services_available']['hugging_face'] else '❌ Pasif'}")
        print()
        
        if stats['google_books']:
            gb_stats = stats['google_books']
            print(f"   Google Books Quota: {gb_stats['calls_remaining']}/{gb_stats['daily_limit']}")
        
        if stats['hugging_face']:
            hf_stats = stats['hugging_face']
            print(f"   Hugging Face Quota: {hf_stats['characters_remaining']:,}/{hf_stats['monthly_limit']:,}")
        print()
        
        # Test 1: Enhanced book addition
        print("📚 Test 1: Enhanced Kitap Ekleme")
        print("-" * 50)
        
        test_isbns = [
            "9780134685991",  # Effective Java (Google Books'ta var)
            "9781491950357",  # Building Microservices
            "9780321765723",  # Test ISBN
        ]
        
        added_books = []
        
        for i, isbn in enumerate(test_isbns, 1):
            print(f"Test {i}: ISBN {isbn}")
            try:
                book = await library.add_book_by_isbn_enhanced(isbn)
                added_books.append(book)
                
                print(f"   ✅ Kitap eklendi: {book.title}")
                print(f"      Yazar: {book.author}")
                print(f"      Sayfa: {book.page_count or 'Bilinmiyor'}")
                print(f"      Kategori: {', '.join(book.categories[:2]) if book.categories else 'Bilinmiyor'}")
                print(f"      Yayın: {book.published_date or 'Bilinmiyor'}")
                print(f"      Dil: {book.language or 'Bilinmiyor'}")
                print(f"      Veri Kaynakları: {', '.join(book.data_sources) if book.data_sources else 'Bilinmiyor'}")
                
                if book.google_rating:
                    print(f"      Google Puanı: {book.google_rating}/5 ({book.google_rating_count} değerlendirme)")
                
                if book.description:
                    desc_preview = book.description[:100] + "..." if len(book.description) > 100 else book.description
                    print(f"      Açıklama: {desc_preview}")
                
                if hasattr(book, 'ai_summary') and book.ai_summary:
                    print(f"      AI Özeti: {book.ai_summary[:80]}...")
                    
            except Exception as e:
                print(f"   ❌ Hata: {e}")
            print()
        
        # Test 2: Search enhanced books
        print("🔍 Test 2: Gelişmiş Arama")
        print("-" * 50)
        
        if added_books:
            # Search by title
            search_term = added_books[0].title.split()[0]  # First word of title
            print(f"Arama terimi: '{search_term}'")
            
            found_books = library.search_books(search_term)
            print(f"   ✅ {len(found_books)} kitap bulundu")
            
            for book in found_books:
                print(f"      - {book.title} ({', '.join(book.data_sources) if book.data_sources else 'legacy'})")
        print()
        
        # Test 3: AI features on enhanced books
        print("🤖 Test 3: AI Özellikleri")
        print("-" * 50)
        
        if added_books and library.hugging_face and library.hugging_face.is_available():
            test_book = added_books[0]
            
            # Test AI summary
            print(f"AI özeti test ediliyor: {test_book.title}")
            ai_summary = await library.generate_ai_summary(test_book)
            
            if ai_summary:
                print(f"   ✅ AI Özeti: {ai_summary}")
            else:
                print("   ❌ AI özeti oluşturulamadı")
            
            # Test sentiment analysis
            test_review = f"{test_book.title} harika bir kitap! Çok beğendim."
            print(f"\nSentiment analizi test ediliyor: '{test_review}'")
            
            sentiment = await library.analyze_review_sentiment(test_review)
            if sentiment:
                emoji = "😊" if sentiment['label'] == "POSITIVE" else "😞" if sentiment['label'] == "NEGATIVE" else "😐"
                print(f"   ✅ Sentiment: {emoji} {sentiment['label']} (Güven: {sentiment['score']:.2f})")
            else:
                print("   ❌ Sentiment analizi başarısız")
        else:
            print("   ⚠️  AI servisi kullanılamıyor veya kitap yok")
        print()
        
        # Test 4: Database integration
        print("💾 Test 4: Veritabanı Entegrasyonu")
        print("-" * 50)
        
        # Reload library to test persistence
        library2 = Library(db_file=db_path)
        reloaded_books = library2.list_books()
        
        print(f"   ✅ {len(reloaded_books)} kitap veritabanından yüklendi")
        
        for book in reloaded_books:
            enhanced_fields = []
            if book.page_count:
                enhanced_fields.append(f"sayfa: {book.page_count}")
            if book.categories:
                enhanced_fields.append(f"kategori: {len(book.categories)}")
            if book.google_rating:
                enhanced_fields.append(f"puan: {book.google_rating}")
            if book.data_sources:
                enhanced_fields.append(f"kaynak: {len(book.data_sources)}")
            
            enhanced_info = f" ({', '.join(enhanced_fields)})" if enhanced_fields else " (temel)"
            print(f"      - {book.title}{enhanced_info}")
        print()
        
        # Final statistics
        print("📈 Final İstatistikler")
        print("-" * 50)
        
        final_stats = library.get_enhanced_usage_stats()
        
        if final_stats['google_books']:
            gb = final_stats['google_books']
            print(f"Google Books:")
            print(f"   Kullanım: {gb['daily_calls_used']}/{gb['daily_limit']} ({gb['usage_percentage']:.1f}%)")
            print(f"   Başarı oranı: {gb['success_rate']:.1f}%")
            print(f"   Ortalama yanıt: {gb['avg_response_time_ms']:.0f}ms")
        
        if final_stats['hugging_face']:
            hf = final_stats['hugging_face']
            print(f"Hugging Face:")
            print(f"   Kullanım: {hf['monthly_characters_used']:,}/{hf['monthly_limit']:,} ({hf['usage_percentage']:.1f}%)")
            print(f"   Başarı oranı: {hf['success_rate']:.1f}%")
            print(f"   Ortalama yanıt: {hf['avg_response_time_ms']:.0f}ms")
        
        print(f"\nToplam kitap: {len(library.list_books())}")
        print()
        
        print("🎉 Enhanced Integration test tamamlandı!")
        
    finally:
        # Cleanup
        try:
            os.unlink(db_path)
        except:
            pass


if __name__ == "__main__":
    # Environment check
    print("🔧 Environment Kontrolü:")
    print(f"   ENABLE_GOOGLE_BOOKS: {os.getenv('ENABLE_GOOGLE_BOOKS', 'false')}")
    print(f"   ENABLE_AI_FEATURES: {os.getenv('ENABLE_AI_FEATURES', 'false')}")
    print(f"   GOOGLE_BOOKS_API_KEY: {'✅ Ayarlandı' if os.getenv('GOOGLE_BOOKS_API_KEY') else '❌ Ayarlanmadı'}")
    print(f"   HUGGING_FACE_API_KEY: {'✅ Ayarlandı' if os.getenv('HUGGING_FACE_API_KEY') else '❌ Ayarlanmadı'}")
    print()
    
    # Run the test
    asyncio.run(test_enhanced_integration())