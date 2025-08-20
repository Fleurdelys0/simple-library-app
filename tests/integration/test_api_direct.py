#!/usr/bin/env python3
"""
Direct API test without external server
Bu script API'yi doğrudan test eder.
"""

import asyncio
import os
from dotenv import load_dotenv
from fastapi.testclient import TestClient
import pytest

# Mark the entire module as integration to allow skipping by default
pytestmark = pytest.mark.integration

# Load environment variables
load_dotenv()

# Set environment variables for testing
os.environ['ENABLE_GOOGLE_BOOKS'] = 'true'
os.environ['ENABLE_AI_FEATURES'] = 'true'
os.environ['HUGGING_FACE_API_KEY'] = os.getenv('HUGGING_FACE_API_KEY', '')

# Import after setting environment variables
from api import app

client = TestClient(app)
API_KEY = "super-secret-key"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


def test_enhanced_api_direct():
    """Test enhanced API endpoints directly"""
    print("🌐 Direct Enhanced API Test Başlıyor...")
    print("=" * 60)
    
    # Test 1: Health check
    print("❤️  Test 1: Health Check")
    print("-" * 50)
    
    response = client.get("/health")
    if response.status_code == 200:
        print(f"   ✅ API sağlıklı: {response.json()}")
    else:
        print(f"   ❌ API sorunu: {response.status_code}")
    print()
    
    # Test 2: API Usage Stats
    print("📊 Test 2: API Usage Statistics")
    print("-" * 50)
    
    response = client.get("/admin/api-usage")
    if response.status_code == 200:
        stats = response.json()
        print(f"   ✅ İstatistikler alındı:")
        
        services = stats.get('services_available', {})
        print(f"      Google Books: {'✅ Aktif' if services.get('google_books') else '❌ Pasif'}")
        print(f"      Hugging Face: {'✅ Aktif' if services.get('hugging_face') else '❌ Pasif'}")
        
        if stats.get('google_books'):
            gb = stats['google_books']
            print(f"      Google Books Quota: {gb['calls_remaining']}/{gb['daily_limit']}")
        
        if stats.get('hugging_face'):
            hf = stats['hugging_face']
            print(f"      Hugging Face Quota: {hf['characters_remaining']:,}/{hf['monthly_limit']:,}")
    else:
        print(f"   ❌ Hata: {response.status_code} - {response.text}")
    print()
    
    # Test 3: Add enhanced book
    print("📚 Test 3: Enhanced Book Addition")
    print("-" * 50)
    
    test_isbn = "9780134685991"  # Effective Java
    
    response = client.post(
        "/books",
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
        
        if book_data.get('description'):
            desc_preview = book_data['description'][:100] + "..." if len(book_data['description']) > 100 else book_data['description']
            print(f"      Açıklama: {desc_preview}")
    else:
        print(f"   ❌ Hata: {response.status_code} - {response.text}")
    print()
    
    # Test 4: Get enhanced book details
    print("📖 Test 4: Enhanced Book Details")
    print("-" * 50)
    
    response = client.get(f"/books/{test_isbn}/enhanced")
    
    if response.status_code == 200:
        book_data = response.json()
        print(f"   ✅ Enhanced detaylar alındı: {book_data['title']}")
        print(f"      AI Özeti: {'✅ Var (' + str(len(book_data['ai_summary'])) + ' karakter)' if book_data.get('ai_summary') else '❌ Yok'}")
        print(f"      Açıklama: {'✅ Var (' + str(len(book_data['description'])) + ' karakter)' if book_data.get('description') else '❌ Yok'}")
        print(f"      Kategoriler: {len(book_data.get('categories', []))} adet")
        print(f"      Dil: {book_data.get('language', 'Bilinmiyor')}")
    else:
        print(f"   ❌ Hata: {response.status_code} - {response.text}")
    print()
    
    # Test 5: Get AI Summary
    print("🤖 Test 5: AI Summary")
    print("-" * 50)
    
    response = client.get(f"/books/{test_isbn}/ai-summary")
    
    if response.status_code == 200:
        summary_data = response.json()
        print(f"   ✅ AI özeti alındı:")
        print(f"      Özet: {summary_data['summary'][:100]}...")
        print(f"      Uzunluk: {summary_data['summary_length']} karakter")
        print(f"      Oluşturulma: {summary_data['generated_at']}")
        print(f"      Kaynak: {summary_data['source']}")
    else:
        print(f"   ❌ Hata: {response.status_code} - {response.text}")
    print()
    
    # Test 6: Sentiment Analysis
    print("😊 Test 6: Sentiment Analysis")
    print("-" * 50)
    
    test_reviews = [
        "Bu kitap gerçekten harika! Java öğrenmek için mükemmel.",
        "Kitap çok karmaşık, anlamakta zorlandım.",
        "Ortalama bir kitap, bazı bölümler iyi."
    ]
    
    for i, review in enumerate(test_reviews, 1):
        response = client.post(
            f"/books/{test_isbn}/analyze-sentiment",
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
        print()
    
    # Test 7: Similar Books
    print("🔗 Test 7: Similar Books")
    print("-" * 50)
    
    response = client.get(f"/books/{test_isbn}/similar?limit=3")
    
    if response.status_code == 200:
        similar_books = response.json()
        print(f"   ✅ {len(similar_books)} benzer kitap bulundu:")
        
        for i, book in enumerate(similar_books, 1):
            print(f"      {i}. {book['title']}")
            print(f"         Yazar: {book['author']}")
            print(f"         ISBN: {book['isbn']}")
            if book.get('categories'):
                print(f"         Kategori: {', '.join(book['categories'][:2])}")
            if book.get('google_rating'):
                print(f"         Puan: {book['google_rating']}/5")
    else:
        print(f"   ❌ Hata: {response.status_code} - {response.text}")
    print()
    
    # Final stats
    print("📈 Final İstatistikler")
    print("-" * 50)
    
    response = client.get("/admin/api-usage")
    if response.status_code == 200:
        final_stats = response.json()
        
        if final_stats.get('google_books'):
            gb = final_stats['google_books']
            print(f"Google Books: {gb['daily_calls_used']}/{gb['daily_limit']} ({gb['usage_percentage']:.1f}%)")
            print(f"   Başarı oranı: {gb['success_rate']:.1f}%")
        
        if final_stats.get('hugging_face'):
            hf = final_stats['hugging_face']
            print(f"Hugging Face: {hf['monthly_characters_used']:,}/{hf['monthly_limit']:,} ({hf['usage_percentage']:.1f}%)")
            print(f"   Başarı oranı: {hf['success_rate']:.1f}%")
    print()
    
    print("🎉 Direct Enhanced API test tamamlandı!")


if __name__ == "__main__":
    print("🔧 Environment Kontrolü:")
    print(f"   ENABLE_GOOGLE_BOOKS: {os.getenv('ENABLE_GOOGLE_BOOKS', 'false')}")
    print(f"   ENABLE_AI_FEATURES: {os.getenv('ENABLE_AI_FEATURES', 'false')}")
    print(f"   HUGGING_FACE_API_KEY: {'✅ Ayarlandı' if os.getenv('HUGGING_FACE_API_KEY') else '❌ Ayarlanmadı'}")
    print()
    
    test_enhanced_api_direct()