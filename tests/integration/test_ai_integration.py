#!/usr/bin/env python3
"""
Test script for AI integration with Library
Bu script Library sınıfının AI özelliklerini test eder.
"""

import asyncio
import os
import tempfile
from dotenv import load_dotenv
from src.library import Library
from src.book import Book
import pytest

# Mark the entire module as integration to allow skipping by default
pytestmark = pytest.mark.integration

# Load environment variables from .env file
load_dotenv()


async def test_ai_integration():
    """Test AI integration with Library class"""
    print("🤖 AI Integration Test Başlıyor...")
    print("=" * 50)
    
    # Create a temporary database for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
        db_path = tmp_db.name
    
    try:
        # Initialize library with test database
        library = Library(db_file=db_path)
        
        # Check AI service availability
        if not library.hugging_face or not library.hugging_face.is_available():
            print("❌ AI servisi kullanılamıyor.")
            print("   HUGGING_FACE_API_KEY ayarlandı mı?")
            print("   ENABLE_AI_FEATURES=true ayarlandı mı?")
            
            # Show current stats anyway
            stats = library.get_ai_usage_stats()
            print(f"   AI Features Enabled: {stats.get('ai_features_enabled', False)}")
            if 'reason' in stats:
                print(f"   Reason: {stats['reason']}")
            return
        
        print("✅ AI servisi hazır!")
        
        # Get initial stats
        stats = library.get_ai_usage_stats()
        print(f"   Aylık kullanım: {stats['monthly_characters_used']:,}/{stats['monthly_limit']:,}")
        print(f"   Kalan quota: {stats['characters_remaining']:,}")
        print()
        
        # Test 1: Add a book and generate AI summary
        print("📚 Test 1: Kitap Ekleme ve AI Özet Oluşturma")
        print("-" * 40)
        
        test_book = Book(
            title="Yapay Zeka ve Gelecek",
            author="Test Yazar",
            isbn="9781234567890",
            description="""
            Bu kitap yapay zekanın gelişimi ve gelecekteki etkilerini ele alır. 
            Makine öğrenmesi, derin öğrenme ve doğal dil işleme gibi konuları detaylı şekilde inceler.
            Ayrıca AI'nın etik boyutları, iş dünyasına etkileri ve toplumsal dönüşüm süreçleri üzerinde durur.
            Kitap hem teknik hem de sosyal perspektiflerden konuya yaklaşarak kapsamlı bir bakış açısı sunar.
            """
        )
        
        # Add book to library
        library.add_book(test_book)
        print(f"✅ Kitap eklendi: {test_book.title}")
        desc_text = test_book.description or ""
        print(f"   Açıklama uzunluğu: {len(desc_text)} karakter")
        print()
        
        # Generate AI summary
        print("🧠 AI özeti oluşturuluyor...")
        ai_summary = await library.generate_ai_summary(test_book)
        
        if ai_summary:
            print(f"✅ AI özeti oluşturuldu!")
            summary_text = ai_summary if isinstance(ai_summary, str) else str(ai_summary)
            print(f"   Özet: {summary_text}")
            print(f"   Özet uzunluğu: {len(summary_text)} karakter")
        else:
            print("❌ AI özeti oluşturulamadı")
        print()
        
        # Test 2: Sentiment Analysis
        print("😊 Test 2: Yorum Sentiment Analizi")
        print("-" * 40)
        
        test_reviews = [
            "Bu kitap gerçekten muhteşem! AI konusunu çok iyi açıklıyor.",
            "Kitap çok karmaşık, anlamakta zorlandım. Pek beğenmedim.",
            "Ortalama bir kitap. Bazı bölümler iyi, bazıları sıkıcı.",
            "Harika bir kaynak! Herkese tavsiye ederim."
        ]
        
        for i, review in enumerate(test_reviews, 1):
            print(f"Yorum {i}: {review}")
            sentiment = await library.analyze_review_sentiment(review)
            
            if sentiment:
                label = sentiment['label']
                score = sentiment['score']
                emoji = "😊" if label == "POSITIVE" else "😞" if label == "NEGATIVE" else "😐"
                print(f"   Sonuç: {emoji} {label} (Güven: {score:.2f})")
            else:
                print("   ❌ Sentiment analizi başarısız")
            print()
        
        # Test 3: Book Enrichment
        print("✨ Test 3: Kitap Verisi Zenginleştirme")
        print("-" * 40)
        
        enriched_book = await library.enrich_book_with_ai(test_book)
        
        if hasattr(enriched_book, 'ai_summary') and enriched_book.ai_summary:
            print("✅ Kitap AI ile zenginleştirildi!")
            print(f"   AI Özeti var: {len(enriched_book.ai_summary)} karakter")
        else:
            print("❌ Kitap zenginleştirilemedi")
        print()
        
        # Final stats
        print("📊 Final İstatistikler")
        print("-" * 40)
        final_stats = library.get_ai_usage_stats()
        print(f"Toplam kullanım: {final_stats['monthly_characters_used']:,} karakter")
        print(f"Kalan quota: {final_stats['characters_remaining']:,} karakter")
        print(f"Kullanım oranı: {final_stats['usage_percentage']:.1f}%")
        print(f"30 günlük çağrı: {final_stats['total_calls_30_days']}")
        print(f"Başarı oranı: {final_stats['success_rate']:.1f}%")
        print()
        
        print("🎉 AI Integration test tamamlandı!")
        
    finally:
        # Cleanup
        try:
            os.unlink(db_path)
        except:
            pass


if __name__ == "__main__":
    # API key kontrolü
    if not os.getenv("HUGGING_FACE_API_KEY"):
        print("⚠️  HUGGING_FACE_API_KEY environment variable ayarlanmamış!")
        print("   Test için ücretsiz bir API key alabilirsiniz: https://huggingface.co/settings/tokens")
        print()
    
    # Run the test
    asyncio.run(test_ai_integration())