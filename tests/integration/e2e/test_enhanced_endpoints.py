#!/usr/bin/env python3
"""
Test script for Enhanced API Endpoints
Bu script yeni API endpoint'lerini test eder.
"""

import asyncio
import os
import requests
import json
from dotenv import load_dotenv
import pytest

# Mark as integration and require RUN_E2E to actually run (needs running API server)
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("RUN_E2E"), reason="Requires running API server. Set RUN_E2E=1 to enable.")
]

# Load environment variables
load_dotenv()

# Set environment variables for testing
os.environ['ENABLE_GOOGLE_BOOKS'] = 'true'
os.environ['ENABLE_AI_FEATURES'] = 'true'
os.environ['HUGGING_FACE_API_KEY'] = os.getenv('HUGGING_FACE_API_KEY', '')

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "super-secret-key"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


def test_enhanced_endpoints():
    """Test enhanced API endpoints"""
    print("🌐 Enhanced API Endpoints Test Başlıyor...")
    print("=" * 60)
    
    # Test 1: Add enhanced book
    print("📚 Test 1: Enhanced Book Addition")
    print("-" * 50)
    
    test_isbn = "9780134685991"  # Effective Java
    
    try:
        response = requests.post(
            f"{BASE_URL}/books",
            headers=HEADERS,
            json={"isbn": test_isbn}
        )
        
        if response.status_code == 200:
            book_data = response.json()
            print(f"   ✅ Kitap eklendi: {book_data['title']}")
            print(f"      Yazar: {book_data['author']}")
            print(f"      Sayfa: {book_data.get('page_count', 'Bilinmiyor')}")
            print(f"      Kategori: {', '.join(book_data.get('categories', [])[:2])}")
            print(f"      Yayın: {book_data.get('published_date', 'Bilinmiyor')}")
            print(f"      Google Puanı: {book_data.get('google_rating', 'Yok')}")
            print(f"      Veri Kaynakları: {', '.join(book_data.get('data_sources', []))}")
        else:
            print(f"   ❌ Hata: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"   ❌ Bağlantı hatası: {e}")
    print()
    
    # Test 2: Get enhanced book details
    print("📖 Test 2: Enhanced Book Details")
    print("-" * 50)
    
    try:
        response = requests.get(f"{BASE_URL}/books/{test_isbn}/enhanced")
        
        if response.status_code == 200:
            book_data = response.json()
            print(f"   ✅ Enhanced detaylar alındı: {book_data['title']}")
            print(f"      AI Özeti: {'✅ Var' if book_data.get('ai_summary') else '❌ Yok'}")
            print(f"      Açıklama: {'✅ Var' if book_data.get('description') else '❌ Yok'}")
            print(f"      Kategoriler: {len(book_data.get('categories', []))} adet")
        else:
            print(f"   ❌ Hata: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"   ❌ Bağlantı hatası: {e}")
    print()
    
    # Test 3: Get AI Summary
    print("🤖 Test 3: AI Summary")
    print("-" * 50)
    
    try:
        response = requests.get(f"{BASE_URL}/books/{test_isbn}/ai-summary")
        
        if response.status_code == 200:
            summary_data = response.json()
            print(f"   ✅ AI özeti alındı:")
            print(f"      Özet: {summary_data['summary'][:100]}...")
            print(f"      Uzunluk: {summary_data['summary_length']} karakter")
            print(f"      Oluşturulma: {summary_data['generated_at']}")
        else:
            print(f"   ❌ Hata: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"   ❌ Bağlantı hatası: {e}")
    print()
    
    # Test 4: Generate new AI Summary
    print("🔄 Test 4: Generate AI Summary")
    print("-" * 50)
    
    try:
        response = requests.post(
            f"{BASE_URL}/books/{test_isbn}/generate-summary",
            headers=HEADERS,
            json={"force_regenerate": True}
        )
        
        if response.status_code == 200:
            summary_data = response.json()
            print(f"   ✅ Yeni AI özeti oluşturuldu:")
            print(f"      Özet: {summary_data['summary'][:100]}...")
            print(f"      Uzunluk: {summary_data['summary_length']} karakter")
        else:
            print(f"   ❌ Hata: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"   ❌ Bağlantı hatası: {e}")
    print()
    
    # Test 5: Sentiment Analysis
    print("😊 Test 5: Sentiment Analysis")
    print("-" * 50)
    
    test_reviews = [
        "Bu kitap gerçekten harika! Java öğrenmek için mükemmel.",
        "Kitap çok karmaşık, anlamakta zorlandım.",
        "Ortalama bir kitap, bazı bölümler iyi."
    ]
    
    for i, review in enumerate(test_reviews, 1):
        try:
            response = requests.post(
                f"{BASE_URL}/books/{test_isbn}/analyze-sentiment",
                headers={"Content-Type": "application/json"},
                json={"text": review}
            )
            
            if response.status_code == 200:
                sentiment_data = response.json()
                label = sentiment_data['label']
                score = sentiment_data['score']
                emoji = "😊" if label == "POSITIVE" else "😞" if label == "NEGATIVE" else "😐"
                print(f"   {i}. {emoji} {label} (Güven: {score:.2f})")
                print(f"      Yorum: {review}")
            else:
                print(f"   ❌ Hata: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"   ❌ Bağlantı hatası: {e}")
        print()
    
    # Test 6: Similar Books
    print("🔗 Test 6: Similar Books")
    print("-" * 50)
    
    try:
        response = requests.get(f"{BASE_URL}/books/{test_isbn}/similar?limit=3")
        
        if response.status_code == 200:
            similar_books = response.json()
            print(f"   ✅ {len(similar_books)} benzer kitap bulundu:")
            
            for i, book in enumerate(similar_books, 1):
                print(f"      {i}. {book['title']}")
                print(f"         Yazar: {book['author']}")
                print(f"         ISBN: {book['isbn']}")
                if book.get('categories'):
                    print(f"         Kategori: {', '.join(book['categories'][:2])}")
        else:
            print(f"   ❌ Hata: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"   ❌ Bağlantı hatası: {e}")
    print()
    
    # Test 7: API Usage Statistics
    print("📊 Test 7: API Usage Statistics")
    print("-" * 50)
    
    try:
        response = requests.get(f"{BASE_URL}/admin/api-usage")
        
        if response.status_code == 200:
            stats_data = response.json()
            print(f"   ✅ API istatistikleri alındı:")
            
            if stats_data.get('google_books'):
                gb_stats = stats_data['google_books']
                print(f"      Google Books: {gb_stats['daily_calls_used']}/{gb_stats['daily_limit']} ({gb_stats['usage_percentage']:.1f}%)")
            
            if stats_data.get('hugging_face'):
                hf_stats = stats_data['hugging_face']
                print(f"      Hugging Face: {hf_stats['monthly_characters_used']:,}/{hf_stats['monthly_limit']:,} ({hf_stats['usage_percentage']:.1f}%)")
            
            services = stats_data.get('services_available', {})
            print(f"      Aktif Servisler: Google Books: {'✅' if services.get('google_books') else '❌'}, AI: {'✅' if services.get('hugging_face') else '❌'}")
        else:
            print(f"   ❌ Hata: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"   ❌ Bağlantı hatası: {e}")
    print()
    
    print("🎉 Enhanced Endpoints test tamamlandı!")


if __name__ == "__main__":
    print("⚠️  Bu test API sunucusunun çalışır durumda olmasını gerektirir!")
    print("   Başka bir terminalde şu komutu çalıştırın:")
    print("   uvicorn api:app --reload")
    print()
    
    input("API sunucusu hazır olduğunda Enter'a basın...")
    
    test_enhanced_endpoints()