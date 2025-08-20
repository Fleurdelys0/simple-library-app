#!/usr/bin/env python3
"""Gelişmiş uç nokta sorununu ayıkla"""

import sys
sys.path.append(".")

from typing import cast

from library import Library
from book import Book
from fastapi import Request
from fastapi.responses import Response
from starlette.requests import Request as StarletteRequest
from starlette.types import Scope

def debug_enhanced_issue():
    print("🔍 Gelişmiş Uç Nokta Ayıklama")
    print("=" * 50)
    
    # Test 1: Kütüphane başlatma
    print("1. Kütüphane başlatılıyor...")
    try:
        library = Library()
        print("   ✅ Kütüphane başarıyla başlatıldı")
    except Exception as e:
        print(f"   ❌ Kütüphane başlatma hatası: {e}")
        return
    
    # Test 2: Var olmayan kitabı bul
    test_isbn = "9789750806452"
    print(f"\n2. {test_isbn} kitabı aranıyor...")
    try:
        book = library.find_book(test_isbn)
        if book:
            print(f"   ✅ Kitap bulundu: {book.title}")
        else:
            print(f"   ⚠️  Kitap bulunamadı (beklenen)")
    except Exception as e:
        print(f"   ❌ Kitap bulma hatası: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Test 3: Mevcut bir kitabı bul
    print(f"\n3. Mevcut kitaplar aranıyor...")
    all_books = []  # Initialize to avoid unbound variable error
    try:
        all_books = library.list_books()
        print(f"   📚 Toplam kitap: {len(all_books)}")
        if all_books:
            test_book = all_books[0]
            print(f"   📖 Şununla test ediliyor: {test_book.isbn} - {test_book.title}")
            
            # to_dict'i test et
            book_dict = test_book.to_dict()
            print(f"   ✅ to_dict çalışıyor: {len(book_dict)} alan")
            
            # EnhancedBookModel oluşturmayı test et
            from api import EnhancedBookModel, _normalize_enhanced_payload
            try:
                # Uç nokta ile aynı normalleştirmeyi kullan
                normalized_dict = _normalize_enhanced_payload(book_dict)
                enhanced_model = EnhancedBookModel(**normalized_dict)
                print(f"   ✅ EnhancedBookModel başarıyla oluşturuldu")
                print(f"      Başlık: {enhanced_model.title}")
                print(f"      Yazar: {enhanced_model.author}")
            except Exception as e:
                print(f"   ❌ EnhancedBookModel hatası: {e}")
                print(f"      Kitap sözlük anahtarları: {list(book_dict.keys())}")
                import traceback
                traceback.print_exc()
        
    except Exception as e:
        print(f"   ❌ Kitapları listeleme hatası: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 4: Tam gelişmiş uç nokta mantığını test et
    print(f"\n4. Gelişmiş uç nokta mantığı test ediliyor...")
    try:
        from api import get_enhanced_book
        
        # Gerçek Starlette/FastAPI Request ve Response örnekleri oluştur
        scope: Scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [],  # if-none-match vs. test için eklenebilir
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
        }
        mock_request: Request = cast(Request, StarletteRequest(scope))
        mock_response: Response = Response()
        
        # Var olmayan kitapla test et (404 vermeli)
        try:
            result = get_enhanced_book("9789750806452", mock_request, mock_response)
            print(f"   ❌ 404 hatası vermeliydi, alınan: {result}")
        except Exception as e:
            print(f"   ✅ Beklenen hata alındı: {e}")
        
        # Mevcut kitapla test et
        if all_books:
            try:
                result = get_enhanced_book(all_books[0].isbn, mock_request, mock_response)
                print(f"   ✅ Gelişmiş uç nokta mevcut kitap için çalışıyor")
                print(f"      Sonuç türü: {type(result)}")
            except Exception as e:
                print(f"   ❌ Gelişmiş uç nokta hatası: {e}")
                import traceback
                traceback.print_exc()
        
    except Exception as e:
        print(f"   ❌ Gelişmiş uç nokta test hatası: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_enhanced_issue()