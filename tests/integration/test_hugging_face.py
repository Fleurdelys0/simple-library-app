#!/usr/bin/env python3
"""
Test script for HuggingFace API integration
Bu script HuggingFace servisini test etmek için kullanılır.
"""

import asyncio
import os
from dotenv import load_dotenv
from src.services.hugging_face_service import HuggingFaceService, SentimentLabel
import pytest

# Mark the entire module as integration to allow skipping by default
pytestmark = pytest.mark.integration

# Load environment variables from .env file
load_dotenv()


async def test_hugging_face_service():
    """Test HuggingFace service functionality"""
    print("🤖 HuggingFace API Test Başlıyor...")
    print("=" * 50)
    
    # Initialize service
    service = HuggingFaceService()
    
    # Check if service is available
    if not service.is_available():
        print("❌ HuggingFace servisi kullanılamıyor.")
        print("   - API key ayarlandı mı? (HUGGING_FACE_API_KEY)")
        print("   - AI özellikler etkin mi? (ENABLE_AI_FEATURES)")
        return
    
    print("✅ HuggingFace servisi hazır!")
    print(f"   - API Key: {'✅ Ayarlandı' if service.api_key else '❌ Ayarlanmadı'}")
    print(f"   - Aylık Limit: {service.monthly_limit:,} karakter")
    
    # Get usage stats
    stats = service.get_usage_stats()
    print(f"   - Kullanılan: {stats['monthly_characters_used']:,} karakter")
    print(f"   - Kalan: {stats['characters_remaining']:,} karakter")
    print()
    
    # Test 1: Sentiment Analysis
    print("📊 Test 1: Sentiment Analysis")
    print("-" * 30)
    
    test_texts = [
        "Bu kitap gerçekten harika! Çok beğendim ve herkese tavsiye ederim.",
        "Kitap çok sıkıcıydı, hiç beğenmedim. Zaman kaybı oldu.",
        "Ortalama bir kitap. Ne çok iyi ne çok kötü.",
        "Amazing book! I loved every page of it.",
        "This book was terrible, couldn't finish it."
    ]
    
    for i, text in enumerate(test_texts, 1):
        print(f"Test {i}: {text[:50]}...")
        try:
            result = await service.analyze_sentiment(text)
            if result:
                emoji = "😊" if result.label == SentimentLabel.POSITIVE else "😞" if result.label == SentimentLabel.NEGATIVE else "😐"
                print(f"   Sonuç: {emoji} {result.label.value} (Güven: {result.score:.2f})")
            else:
                print("   ❌ Analiz başarısız")
        except Exception as e:
            print(f"   ❌ Hata: {e}")
        print()
    
    # Test 2: Text Summarization
    print("📝 Test 2: Text Summarization")
    print("-" * 30)
    
    long_text = """
    Yapay zeka (AI), makinelerin insan benzeri zeka gerektiren görevleri yerine getirme yeteneğidir. 
    Bu teknoloji, öğrenme, problem çözme, karar verme ve dil anlama gibi bilişsel işlevleri simüle eder. 
    Modern yapay zeka sistemleri, büyük veri setlerinden öğrenen makine öğrenmesi algoritmalarını kullanır. 
    Derin öğrenme, yapay sinir ağları aracılığıyla karmaşık desenleri tanıma konusunda özellikle başarılıdır. 
    Günümüzde AI, sağlık, finans, ulaşım, eğitim ve eğlence sektörlerinde yaygın olarak kullanılmaktadır. 
    Chatbot'lar, görüntü tanıma sistemleri, öneri algoritmaları ve otonom araçlar AI'nın pratik uygulamalarıdır. 
    Ancak AI'nın gelişimi, etik sorunlar, iş kaybı endişeleri ve güvenlik riskleri gibi zorlukları da beraberinde getirir. 
    Gelecekte AI'nın daha da gelişmesi beklenmekte ve insan yaşamının her alanında daha büyük bir rol oynaması öngörülmektedir.
    """
    
    print(f"Orijinal metin: {len(long_text)} karakter")
    print(f"İlk 100 karakter: {long_text[:100]}...")
    print()
    
    try:
        result = await service.summarize_text(long_text, max_length=100)
        if result:
            print(f"✅ Özet oluşturuldu!")
            print(f"   Özet: {result.summary}")
            print(f"   Orijinal: {result.original_length} karakter")
            print(f"   Özet: {result.summary_length} karakter")
            print(f"   Sıkıştırma oranı: {result.compression_ratio:.2f}")
        else:
            print("❌ Özet oluşturulamadı")
    except Exception as e:
        print(f"❌ Hata: {e}")
    print()
    
    # Test 3: Book Summary Generation
    print("📚 Test 3: Book Summary Generation")
    print("-" * 30)
    
    book_title = "1984"
    book_author = "George Orwell"
    book_description = """
    1984, George Orwell tarafından yazılan distopik bir romandır. 
    Kitap, totaliter bir rejimin kontrolü altındaki gelecekteki bir toplumu anlatır. 
    Ana karakter Winston Smith, Büyük Birader'in sürekli gözetimi altında yaşar. 
    Roman, düşünce suçu, gerçeğin manipülasyonu ve bireysel özgürlüğün yok edilmesi temalarını işler.
    """
    
    print(f"Kitap: {book_title} - {book_author}")
    print(f"Açıklama: {len(book_description)} karakter")
    print()
    
    try:
        summary = await service.generate_book_summary(book_title, book_author, book_description)
        if summary:
            print(f"✅ Kitap özeti oluşturuldu!")
            print(f"   Özet: {summary}")
        else:
            print("❌ Kitap özeti oluşturulamadı")
    except Exception as e:
        print(f"❌ Hata: {e}")
    print()
    
    # Final stats
    print("📈 Final İstatistikler")
    print("-" * 30)
    final_stats = service.get_usage_stats()
    print(f"Toplam kullanım: {final_stats['monthly_characters_used']:,} karakter")
    print(f"Kalan quota: {final_stats['characters_remaining']:,} karakter")
    print(f"Kullanım oranı: {final_stats['usage_percentage']:.1f}%")
    print(f"30 günlük çağrı sayısı: {final_stats['total_calls_30_days']}")
    print(f"Başarı oranı: {final_stats['success_rate']:.1f}%")
    print()
    
    print("🎉 Test tamamlandı!")


if __name__ == "__main__":
    # API key kontrolü
    if not os.getenv("HUGGING_FACE_API_KEY"):
        print("⚠️  HUGGING_FACE_API_KEY environment variable ayarlanmamış!")
        print("   Test için ücretsiz bir API key alabilirsiniz: https://huggingface.co/settings/tokens")
        print("   Sonra şu komutu çalıştırın:")
        print("   export HUGGING_FACE_API_KEY='your_token_here'")
        print()
        print("🔄 API key olmadan da test çalışacak (mock mode)")
        print()
    
    # Run the test
    asyncio.run(test_hugging_face_service())