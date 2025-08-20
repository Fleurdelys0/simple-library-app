import os
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import json
import random
import sqlite3
import asyncio

import httpx
from fastapi import FastAPI, HTTPException, Body, Query, Depends, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from functools import lru_cache
import hashlib
from threading import RLock
from http_client import get_http_client, cleanup_http_client
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager

from library import Library, ExternalServiceError
from book import Book
from config import settings
from database import get_db_connection


library = Library()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Başlangıçta kaynakları başlat
    await get_http_client()
    try:
        yield
    finally:
        # Kapanışta kaynakları temizle
        try:
            await cleanup_http_client()
        except Exception:
            pass
        # Kapanışta takılı kalmayı önlemek için devam eden AI görevlerini iptal et
        try:
            async with inflight_ai_lock:
                tasks = list(inflight_ai_tasks.values())
                inflight_ai_tasks.clear()
            for t in tasks:
                t.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            pass

app = FastAPI(title="Kütüphane Yönetim API'si", lifespan=lifespan)

# --- Performans Ara Katmanı ---
# 1KB'den büyük yanıtlar için GZip sıkıştırmasını etkinleştir
app.add_middleware(GZipMiddleware, minimum_size=1000)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Özel Önbellek Başlıkları Ara Katmanı ---
@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    response = await call_next(request)
    
    # Statik dosyalar için önbellek başlıkları ekle
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000"  # 1 yıl
        response.headers["ETag"] = f'"static-{hash(request.url.path)}"'
    
    # Kapak resimleri için önbellek başlıkları ekle
    elif request.url.path.startswith("/covers/"):
        response.headers["Cache-Control"] = "public, max-age=86400"  # 24 saat
    
    # Kitap listeleri için ETag ekle (istemci tarafı önbellekleme için)
    elif request.url.path == "/books" and request.method == "GET":
        # Kitap sayısına ve son değiştirilme zamanına dayalı basit ETag
        total_books = len(library.list_books())
        etag = f'"books-{total_books}-{hash(str(total_books))}"'
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = "public, max-age=60"  # 1 dakika
    
    # Performans başlıkları ekle
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    return response

# --- Başlatma ve Kapatma Olayları ---
# Yukarıdaki FastAPI lifespan tarafından yönetilir.

# --- Güvenlik ---
api_key_header = APIKeyHeader(name="X-API-Key")

def get_api_key(api_key: str = Security(api_key_header)):
    """API anahtarını doğrulamak için bağımlılık."""
    if api_key == settings.api_key:
        return api_key
    else:
        raise HTTPException(
            status_code=403,
            detail="Kimlik bilgileri doğrulanamadı",
        )

# --- Sağlık Kontrolü ---
@app.get("/health")
async def health():
    """Docker ve compose sağlık kontrolleri için hafif sağlık uç noktası.
    Hızlı bir veritabanı bağlantı denemesi yapar ve özellik bayraklarını döndürür.
    """
    db_ok = True
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
    except Exception:
        db_ok = False
    # Test beklentileriyle uyum için 'status' = 'healthy', 'timestamp' ve 'total_books' alanlarını ekle
    now_iso = datetime.utcnow().isoformat() + "Z"
    return {
        "status": "healthy",
        "timestamp": now_iso,
        "total_books": len(library.list_books()),
        # Geriye dönük uyumluluk için mevcut alanları koru
        "time": now_iso,
        "db": db_ok,
        "services": {
            "google_books": os.getenv("ENABLE_GOOGLE_BOOKS", "false").lower() == "true",
            "hugging_face": os.getenv("ENABLE_AI_FEATURES", "false").lower() == "true",
        },
    }

# Daha iyi performans için önbellek yöneticisini içe aktar
from cache_manager import cache_manager

# Geriye dönük uyumluluk için eski önbellek işlevleri
def get_cached_response(key: str) -> Any | None:
    """Varsa ve süresi dolmamışsa önbelleğe alınmış değeri döndür; aksi takdirde None."""
    return cache_manager.get(key)

def cache_response(key: str, value: Any, ttl_seconds: int = 60) -> None:
    """Bir yanıtı şu andan itibaren ttl_saniye boyunca önbelleğe al."""
    cache_manager.set(key, value, ttl_seconds)

def invalidate_cache(prefix: str) -> int:
    """Anahtarları verilen önekle başlayan tüm önbellek girişlerini geçersiz kıl.
    
    Kaldırılan girişlerin sayısını döndürür. Hiçbir anahtar eşleşmese bile çağırmak güvenlidir.
    """
    return cache_manager.invalidate_pattern(f"{prefix}*")

# --- Devam Eden AI Özet Birleştirme ---
# ISBN başına eşzamanlı AI özet oluşturmalarını tek bir asyncio.Task'ta birleştir
inflight_ai_tasks: Dict[str, asyncio.Task] = {}
inflight_ai_lock = asyncio.Lock()

def _compute_etag_from_dict(payload: Dict[str, Any]) -> str:
    """Bir sözlük yükünden deterministik olarak güçlü bir ETag hesapla."""
    try:
        raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    except Exception:
        raw = repr(payload).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    return f'""{digest}"'

def _ensure_list_of_str(value: Any) -> list[str] | None:
    """Gelen değeri mümkün olduğunda bir dize listesine zorla; aksi takdirde None.

    JSON dizelerini, düz dizeleri (liste içine sarar), yinelenebilirleri veya None'ı kabul eder.
    """
    if value is None:
        return None
    try:
        # Veritabanında JSON olarak depolanmışsa ve sızdırılmışsa, ayrıştır
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                value = parsed
            except Exception:
                return [value]
        # Zaten yinelenebilir ise (liste/tuple/set), öğeleri dizeye zorla
        if isinstance(value, (list, tuple, set)):
            return [str(x) for x in value]
        # Yedek: tek değer -> liste
        return [str(value)]
    except Exception:
        return None

def _normalize_enhanced_payload(d: Dict[str, Any]) -> Dict[str, Any]:
    """Pydantic doğrulama sorunlarını önlemek için EnhancedBookModel alanlarını normalleştir."""
    out = dict(d)
    out["categories"] = _ensure_list_of_str(out.get("categories"))
    out["data_sources"] = _ensure_list_of_str(out.get("data_sources"))
    # Sayısal alanlar dize olarak gelirse zorla
    for k in ("page_count", "google_rating_count"):
        v = out.get(k)
        if v is not None and isinstance(v, str):
            try:
                out[k] = int(float(v))
            except Exception:
                out[k] = None
    if (v := out.get("google_rating")) is not None and isinstance(v, str):
        try:
            out["google_rating"] = float(v)
        except Exception:
            out["google_rating"] = None
    # Tarih/saat benzeri alanların dize olduğundan emin ol
    for k in ("created_at", "ai_summary_generated_at", "published_date"):
        v = out.get(k)
        if v is not None and not isinstance(v, str):
            out[k] = str(v)
    # Varsa dilin dize olduğundan emin ol
    v = out.get("language")
    if v is not None and not isinstance(v, str):
        out["language"] = str(v)
    return out

async def _coalesced_generate_ai_summary(isbn: str, coro_factory):
    """ISBN başına tek bir devam eden AI özet oluşturma görevinin sonucunu döndür."""
    async with inflight_ai_lock:
        task = inflight_ai_tasks.get(isbn)
        if task and not task.done():
            return await task
        # yeni görev oluştur
        task = asyncio.create_task(coro_factory())
        inflight_ai_tasks[isbn] = task
    try:
        return await task
    finally:
        async with inflight_ai_lock:
            # yalnızca aynı görevse kaldır
            if inflight_ai_tasks.get(isbn) is task:
                inflight_ai_tasks.pop(isbn, None)

# --- Modeller ---
class BookModel(BaseModel):
    title: str
    author: str
    isbn: str
    cover_url: str | None = None

class BookCreateModel(BaseModel):
    isbn: str | None = Field(default=None, description="Otomatik getirme için sağlayın")
    title: str | None = Field(default=None, description="ISBN kullanılmıyorsa manuel başlık")
    author: str | None = Field(default=None, description="ISBN kullanılmıyorsa manuel yazar")

class StatsModel(BaseModel):
    total_books: int
    unique_authors: int

# Geliştirilmiş API Modelleri
class EnhancedBookModel(BaseModel):
    """Google Books ve AI verileriyle geliştirilmiş kitap modeli"""
    # Temel alanlar
    isbn: str
    title: str
    author: str
    cover_url: str | None = None
    created_at: str | None = None
    
    # Google Books alanları
    page_count: int | None = None
    categories: List[str] | None = None
    published_date: str | None = None
    publisher: str | None = None
    language: str | None = None
    description: str | None = None
    google_rating: float | None = None
    google_rating_count: int | None = None
    
    # AI alanları
    ai_summary: str | None = None
    ai_summary_generated_at: str | None = None
    sentiment_score: float | None = None
    data_sources: List[str] | None = None

class AISummaryRequest(BaseModel):
    """AI özet oluşturma için istek modeli"""
    force_regenerate: bool = False

class AISummaryResponse(BaseModel):
    """AI özeti için yanıt modeli"""
    isbn: str
    summary: str
    generated_at: str
    original_length: int | None = None
    summary_length: int
    source: str = "hugging_face"

class SentimentAnalysisRequest(BaseModel):
    """Duygu analizi için istek modeli"""
    text: str

class SentimentAnalysisResponse(BaseModel):
    """Duygu analizi için yanıt modeli"""
    text: str
    label: str  # POSITIVE, NEGATIVE, NEUTRAL
    score: float  # Güven puanı
    analysis_time: str

class APIUsageStatsResponse(BaseModel):
    """API kullanım istatistikleri için yanıt modeli"""
    google_books: Dict[str, Any] | None = None
    hugging_face: Dict[str, Any] | None = None
    services_available: Dict[str, bool]

# --- Yardımcı Fonksiyonlar ---
def _add_book_to_library(book: Book) -> BookModel:
    """Kütüphaneye bir kitap eklemek ve istisnaları işlemek için yardımcı fonksiyon."""
    try:
        library.add_book(book)
        return BookModel(**book.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

def _add_link_headers(response: Response, offset: Optional[int], limit: Optional[int], total: int, 
                     q: Optional[str] = None, sort_by: Optional[str] = None, 
                     order: Optional[str] = None, page: Optional[int] = None,
                     page_size: Optional[int] = None):
    """Sayfalandırma için Link başlıkları ekle."""
    if not response:
        return
    
    links = []
    base_url = f"http://{settings.api_host}:{settings.api_port}"
    
    # Ofset tabanlı sayfalandırma için
    if page is None:
        # Koruma: ofset/limit eksikse, ofset tabanlı başlıkları oluşturmayı atla
        if offset is None or limit is None:
            response.headers["Link"] = ", ".join(links) if links else ""
            return
        # Sonraki ve önceki ofsetleri hesapla
        if offset > 0:
            prev_offset = max(0, offset - limit)
            params = [f"offset={prev_offset}", f"limit={limit}"]
            if q:
                params.append(f"q={q}")
            if sort_by:
                params.append(f"sort_by={sort_by}")
            if order:
                params.append(f"order={order}")
            links.append(f'<{base_url}/books?{"&".join(params)}>; rel="prev"')
        
        if offset + limit < total:
            next_offset = offset + limit
            params = [f"offset={next_offset}", f"limit={limit}"]
            if q:
                params.append(f"q={q}")
            if sort_by:
                params.append(f"sort_by={sort_by}")
            if order:
                params.append(f"order={order}")
            links.append(f'<{base_url}/books?{"&".join(params)}>; rel="next"')
        
        # İlk sayfa
        params = [f"offset=0", f"limit={limit}"]
        if q:
            params.append(f"q={q}")
        if sort_by:
            params.append(f"sort_by={sort_by}")
        if order:
            params.append(f"order={order}")
        links.append(f'<{base_url}/books?{"&".join(params)}>; rel="first"')
        
        # Son sayfa
        last_offset = max(0, total - limit)
        params = [f"offset={last_offset}", f"limit={limit}"]
        if q:
            params.append(f"q={q}")
        if sort_by:
            params.append(f"sort_by={sort_by}")
        if order:
            params.append(f"order={order}")
        links.append(f'<{base_url}/books?{"&".join(params)}>; rel="last"')
    
    # Sayfa tabanlı sayfalandırma için
    else:
        # Koruma: sayfa tabanlı başlıklar kullanırken sayfa boyutunun sağlandığından emin ol
        if page_size is None:
            response.headers["Link"] = ", ".join(links) if links else ""
            return
        total_pages = (total + page_size - 1) // page_size
        
        if page > 1:
            params = [f"page={page - 1}", f"page_size={page_size}"]
            if q:
                params.append(f"q={q}")
            links.append(f'<{base_url}/books/paginated?{"&".join(params)}>; rel="prev"')
        
        if page < total_pages:
            params = [f"page={page + 1}", f"page_size={page_size}"]
            if q:
                params.append(f"q={q}")
            links.append(f'<{base_url}/books/paginated?{"&".join(params)}>; rel="next"')
        
        # İlk sayfa
        params = [f"page=1", f"page_size={page_size}"]
        if q:
            params.append(f"q={q}")
        links.append(f'<{base_url}/books/paginated?{"&".join(params)}>; rel="first"')
        
        # Son sayfa
        params = [f"page={total_pages}", f"page_size={page_size}"]
        if q:
            params.append(f"q={q}")
        links.append(f'<{base_url}/books/paginated?{"&".join(params)}>; rel="last"')
    
    if links:
        response.headers["Link"] = ", ".join(links)

# --- API Uç Noktaları ---
@app.get("/covers/{isbn}")
async def get_book_cover(isbn: str, size: Optional[str] = Query("L", description="Kapak boyutu: S, M, L")):
    """Optimizasyon ve önbellekleme ile Open Library'den kitap kapağını proxy'le."""
    # Boyut parametresini doğrula
    if size not in ["S", "M", "L"]:
        size = "L"
    
    # Önce önbelleği kontrol et
    cache_key = f"cover:{isbn}:{size}"
    cached_response = get_cached_response(cache_key)
    if cached_response:
        return Response(
            content=cached_response["content"],
            media_type=cached_response["media_type"],
            headers=cached_response["headers"]
        )
    
    # Daha iyi kalite için farklı boyutları dene, en büyükten başlayarak
    if size == "L":
        # Önce XL'yi dene, sonra L'yi yedek olarak kullan
        cover_urls = [
            f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg",  # Orijinal büyük
            f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg",  # Orta yedek
        ]
    else:
        cover_urls = [f"https://covers.openlibrary.org/b/isbn/{isbn}-{size}.jpg"]
    
    # Çalışan bir tane bulana kadar her URL'yi dene
    response = None
    for cover_url in cover_urls:
        try:
            http_client = await get_http_client()
            temp_response = await http_client.get_with_retry(cover_url, retries=1, backoff=0.2)
            if temp_response and temp_response.status_code == 200 and len(temp_response.content) > 1000:
                response = temp_response
                break
        except Exception:
            continue
    
    # Hiçbir URL çalışmazsa, varsayılan kapağı döndür
    if not response:
        default_headers = {
            "Cache-Control": "public, max-age=3600",
            "Content-Type": "image/svg+xml"
        }
        return FileResponse(
            'static/default-cover.svg', 
            media_type="image/svg+xml",
            headers=default_headers
        )
    
    try:
        
        if response and response.status_code == 200 and len(response.content) > 1000:
            # Görüntü büyükse optimize et
            optimized_content = response.content
            media_type = "image/jpeg"
            
            # Büyük kapaklar için akıllı optimizasyon uygula
            if size == "L" and len(response.content) > 50000:  # > 50KB eşiği
                try:
                    from PIL import Image
                    import io
                    
                    # Görüntüyü aç ve optimize et
                    image = Image.open(io.BytesIO(response.content))
                    
                    # Gerekirse RGB'ye dönüştür
                    if image.mode in ("RGBA", "P"):
                        image = image.convert("RGB")
                    
                    # Daha iyi kalitede yeniden boyutlandır - daha keskin görüntü için artırılmış maksimum genişlik
                    max_width = 900  # Daha iyi kalite için 700'den artırıldı
                    if image.width > max_width:
                        ratio = max_width / image.width
                        new_height = int(image.height * ratio)
                        # Yüksek kaliteli yeniden boyutlandırma için LANCZOS kullan
                        image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)
                    
                    # Daha iyi kalite için görüntüyü keskinleştir
                    from PIL import ImageFilter
                    image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=125, threshold=3))
                    
                    # Optimize edilmiş görüntüyü daha yüksek kalitede kaydet
                    output = io.BytesIO()
                    image.save(output, format="JPEG", quality=95, optimize=True)
                    optimized_content = output.getvalue()
                    
                except ImportError:
                    # PIL mevcut değil, orijinal içeriği kullan
                    pass
                except Exception:
                    # Görüntü işleme başarısız oldu, orijinal içeriği kullan
                    pass
            
            headers = {
                "Cache-Control": "public, max-age=86400",  # 24 saat önbelleğe al
                "ETag": f'"cover-{isbn}-{size}-{hash(optimized_content)}"',
                "Content-Length": str(len(optimized_content))
            }
            
            # Yanıtı 1 saat önbelleğe al
            cache_response(cache_key, {
                "content": optimized_content,
                "media_type": media_type,
                "headers": headers
            }, ttl_seconds=3600)
            
            return Response(
                content=optimized_content,
                media_type=media_type,
                headers=headers
            )
        else:
            # Uygun önbellekleme ile varsayılan kapağı döndür
            default_headers = {
                "Cache-Control": "public, max-age=3600",  # 1 saat önbelleğe al
                "Content-Type": "image/svg+xml"
            }
            return FileResponse(
                'static/default-cover.svg', 
                media_type="image/svg+xml",
                headers=default_headers
            )
    except Exception as e:
        # Hata durumunda varsayılan kapağı döndür
        return FileResponse(
            'static/default-cover.svg', 
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=3600"}
        )

@app.get("/stats", response_model=StatsModel)
def get_library_stats():
    """Kütüphane hakkında temel istatistikleri al."""
    stats = library.get_statistics()
    return StatsModel(total_books=stats["total_books"], unique_authors=stats["unique_authors"])

# --- Sayfalandırma Modelleri ---
class PaginatedResponse(BaseModel):
    items: List[BookModel]
    total: int
    page: int
    page_size: int
    total_pages: int

class AdvancedSearchParams(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    isbn: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    publish_year_from: Optional[int] = None
    publish_year_to: Optional[int] = None
    tag_ids: Optional[List[int]] = None
    min_rating: Optional[float] = None

@app.get("/books", response_model=List[EnhancedBookModel])
def get_books(
    response: Response,
    q: Optional[str] = Query(None, description="Arama sorgusu"),
    sort_by: Optional[str] = Query("title", description="Sıralama alanı: title|author|created_at"),
    order: Optional[str] = Query("asc", description="Sıralama düzeni: asc|desc"),
    limit: int = Query(100, ge=1, le=500, description="Maksimum sonuç sayısı"),
    offset: int = Query(0, ge=0, description="Atlanacak sonuç sayısı"),
):
    """Arama, sıralama, limit ve ofset ile tüm kitapların bir listesini al."""
    # FastAPI/Pydantic regex/desen uyumsuzluklarını önlemek için sort_by ve order'ı doğrula
    allowed_sort = {"title", "author", "created_at"}
    allowed_order = {"asc", "desc"}
    if sort_by not in allowed_sort:
        raise HTTPException(status_code=400, detail="Geçersiz sort_by. İzin verilenler: title, author, created_at")
    if order not in allowed_order:
        raise HTTPException(status_code=400, detail="Geçersiz order. İzin verilenler: asc, desc")
    # Önce önbelleği kontrol et
    cache_key = f"books:{q}:{sort_by}:{order}:{limit}:{offset}"
    cached = get_cached_response(cache_key)
    if cached:
        # Sayfalandırma için Link başlıkları ekle
        total_books = len(library.list_books()) if not q else len(library.search_books(q))
        _add_link_headers(response, offset, limit, total_books, q, sort_by, order)
        return cached
    
    if q:
        books = library.search_books(q)
    else:
        books = library.list_books()
    
    # Sıralamayı uygula
    reverse_order = (order == "desc")
    if sort_by == "title":
        books.sort(key=lambda b: b.title.lower(), reverse=reverse_order)
    elif sort_by == "author":
        books.sort(key=lambda b: b.author.lower(), reverse=reverse_order)
    elif sort_by == "created_at":
        books.sort(key=lambda b: b.created_at or "", reverse=reverse_order)
    
    total_books = len(books)
    
    # Sayfalandırmayı uygula
    paginated_books = books[offset:offset + limit]
    # Her kitap için geliştirilmiş alanları doğrudan döndür (normalleştirilmiş)
    result = [
        EnhancedBookModel(**_normalize_enhanced_payload(b.to_dict()))
        for b in paginated_books
    ]
    
    # Link başlıkları ekle
    _add_link_headers(response, offset, limit, total_books, q, sort_by, order)
    
    # Sonucu önbelleğe al
    cache_response(cache_key, result, ttl_seconds=60)
    return result

@app.get("/books/paginated", response_model=PaginatedResponse)
def get_books_paginated(
    response: Response,
    q: Optional[str] = Query(None, description="Arama sorgusu"),
    page: int = Query(1, ge=1, description="Sayfa numarası"),
    page_size: int = Query(20, ge=1, le=100, description="Sayfa başına öğe"),
):
    """Kitapların sayfalandırılmış listesini al."""
    if q:
        books = library.search_books(q)
    else:
        books = library.list_books()
    
    total = len(books)
    total_pages = (total + page_size - 1) // page_size
    start = (page - 1) * page_size
    end = start + page_size
    
    paginated_books = books[start:end]
    
    # Link başlıkları ekle
    _add_link_headers(response, None, None, total, q, None, None, page, page_size)
    
    return PaginatedResponse(
        items=[BookModel(**b.to_dict()) for b in paginated_books],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )

# --- Harici Haber Akışları (Anahtarsız) ---
@app.get("/news/books/nyt")
async def get_nyt_books_news(limit: int = Query(5, ge=1, le=20)):
    """NYT Books RSS akışını JSON'a proxy'le ve ayrıştır.

    En son kitapla ilgili makaleleri döndürür: başlık, bağlantı, yayınlanma tarihi, özet, resim (varsa).
    Harici istekleri azaltmak için bellek içi TTL önbelleği kullanır.
    """
    RSS_URL = "https://rss.nytimes.com/services/xml/rss/nyt/Books.xml"
    cache_key = f"news:nyt:books:{limit}"
    cached = get_cached_response(cache_key)
    if cached is not None:
        return JSONResponse(
            content=cached,
            headers={"Cache-Control": "public, max-age=300"}
        )

    try:
        http_client = await get_http_client()
        resp = await http_client.get_with_retry(RSS_URL, retries=2, backoff=0.4)
        if not resp or resp.status_code != 200 or not resp.text:
            raise HTTPException(status_code=502, detail="NYT RSS akışı getirilemedi")

        # XML'i güvenli bir şekilde ayrıştır
        try:
            root = ET.fromstring(resp.text)
        except Exception:
            raise HTTPException(status_code=502, detail="NYT RSS akışı ayrıştırılamadı")

        # Metni güvenli bir şekilde çıkarmak ve kırpmak için yardımcı
        def _t(el):
            if el is None:
                return ""
            try:
                return (el.text or "").strip()
            except Exception:
                return ""

        # Ad alanları (varsa resimler için medya ad alanı kullanılır)
        ns = {"media": "http://search.yahoo.com/mrss/"}
        channel = root.find("channel")
        items = []
        if channel is not None:
            for item in channel.findall("item"):
                title_el = item.find("title")
                link_el = item.find("link")
                pub_el = item.find("pubDate")
                desc_el = item.find("description")
                # Medya:içeriğini dene
                media_el = item.find("media:content", ns)
                image_url = None
                if media_el is not None:
                    image_url = media_el.attrib.get("url")
                # Bazı akışlar medya:küçük resim kullanır
                if not image_url:
                    thumb_el = item.find("media:thumbnail", ns)
                    if thumb_el is not None:
                        image_url = thumb_el.attrib.get("url")

                items.append({
                    "title": _t(title_el),
                    "link": _t(link_el),
                    "published_at": _t(pub_el),
                    "summary": _t(desc_el),
                    "image": image_url
                })

        # Kırp ve önbelleğe al
        result = items[:limit]
        cache_response(cache_key, result, ttl_seconds=300)
        return JSONResponse(
            content=result,
            headers={"Cache-Control": "public, max-age=300"}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NYT Books haberleri getirilemedi: {str(e)}")

@app.post("/books/search/advanced", response_model=List[BookModel])
def advanced_search(params: AdvancedSearchParams):
    """Birden çok filtreli gelişmiş arama."""
    books = library.list_books()
    
    # Başlığa göre filtrele
    if params.title:
        books = [b for b in books if params.title.lower() in b.title.lower()]
    
    # Yazara göre filtrele
    if params.author:
        books = [b for b in books if params.author.lower() in b.author.lower()]
    
    # ISBN'e göre filtrele
    if params.isbn:
        books = [b for b in books if params.isbn in b.isbn]
    
    return [BookModel(**b.to_dict()) for b in books]



@app.get("/books/random", response_model=BookModel)
def get_random_book():
    """Kütüphaneden rastgele bir kitap al."""
    books = library.list_books()
    if not books:
        raise HTTPException(status_code=404, detail="Kütüphanede kitap yok.")
    
    random_book = random.choice(books)
    return BookModel(**random_book.to_dict())

@app.get("/books/{isbn}", response_model=BookModel)
def get_book(isbn: str):
    """ISBN'sine göre tek bir kitap al."""
    book = library.find_book(isbn)
    if not book:
        raise HTTPException(status_code=404, detail="Kitap bulunamadı.")
    return BookModel(**book.to_dict())

@app.post("/books", response_model=EnhancedBookModel, dependencies=[Depends(get_api_key)])
async def add_book(payload: BookCreateModel):
    """Gelişmiş API entegrasyonunu kullanarak kütüphaneye yeni bir kitap ekle."""
    # Yalnızca ISBN sağlanırsa, geliştirilmiş kitap eklemeyi kullan
    if payload.isbn and not payload.title:
        try:
            # Birden çok API ile geliştirilmiş kitap eklemeyi kullan
            book = await library.add_book_by_isbn_enhanced(payload.isbn)
            # Bu ISBN ile ilgili önbellekleri geçersiz kıl
            invalidate_cache(f"enhanced:{payload.isbn}")
            invalidate_cache(f"ai_summary:{payload.isbn}")
            return EnhancedBookModel(**book.to_dict())
        except ValueError as e:
            # Bu, "zaten var" hatasını doğru bir şekilde yakalar
            raise HTTPException(status_code=400, detail=str(e))
        except LookupError:
            # Yedek: tüm API'ler başarısız olduğunda minimal bir kitap girişi oluştur
            cover_url = f"http://{settings.api_host}:{settings.api_port}/covers/{payload.isbn}"
            fallback_book = Book(title="Bilinmeyen Başlık", author="Bilinmeyen Yazar", isbn=payload.isbn, cover_url=cover_url)
            try:
                library.add_book(fallback_book)
                # Bu ISBN ile ilgili önbellekleri geçersiz kıl
                invalidate_cache(f"enhanced:{payload.isbn}")
                invalidate_cache(f"ai_summary:{payload.isbn}")
                return EnhancedBookModel(**fallback_book.to_dict())
            except ValueError:
                # Zaten varsa, mevcut kaydı döndür
                existing = library.find_book(payload.isbn)
                if existing:
                    # Bu ISBN ile ilgili önbellekleri geçersiz kıl (hiç olmasa bile güvenli)
                    invalidate_cache(f"enhanced:{payload.isbn}")
                    invalidate_cache(f"ai_summary:{payload.isbn}")
                    return EnhancedBookModel(**existing.to_dict())
                raise HTTPException(status_code=400, detail=f"ISBN'i {payload.isbn} olan kitap zaten var.")
    # Tüm ayrıntılar sağlanırsa, kitabı doğrudan ekle
    elif payload.isbn and payload.title and payload.author:
        cover_url = f"http://{settings.api_host}:{settings.api_port}/covers/{payload.isbn}"
        book = Book(title=payload.title, author=payload.author, isbn=payload.isbn, cover_url=cover_url)
        try:
            library.add_book(book)
            # Bu ISBN ile ilgili önbellekleri geçersiz kıl
            invalidate_cache(f"enhanced:{payload.isbn}")
            invalidate_cache(f"ai_summary:{payload.isbn}")
            return EnhancedBookModel(**book.to_dict())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    # Aksi takdirde, istek geçersizdir
    else:
        raise HTTPException(status_code=422, detail="ISBN veya ISBN, Başlık ve Yazar sağlayın.")

# Geriye dönük uyumluluk için eski uç nokta
@app.post("/books/legacy", response_model=BookModel, dependencies=[Depends(get_api_key)])
def add_book_legacy(payload: BookCreateModel):
    """Yalnızca eski Open Library'yi kullanarak yeni bir kitap ekle (geriye dönük uyumluluk için)."""
    # Yalnızca ISBN sağlanırsa, Open Library'den kitap ayrıntılarını getir
    if payload.isbn and not payload.title:
        try:
            book = library.add_book_by_isbn(payload.isbn)
            return BookModel(**book.to_dict())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except (ExternalServiceError, LookupError):
            # Yedek: harici arama başarısız olduğunda minimal bir kitap girişi oluştur.
            cover_url = f"http://{settings.api_host}:{settings.api_port}/covers/{payload.isbn}"
            fallback_book = Book(title="Bilinmeyen Başlık", author="Bilinmeyen Yazar", isbn=payload.isbn, cover_url=cover_url)
            try:
                library.add_book(fallback_book)
                return BookModel(**fallback_book.to_dict())
            except ValueError:
                existing = library.find_book(payload.isbn)
                if existing:
                    return BookModel(**existing.to_dict())
                raise HTTPException(status_code=400, detail=f"ISBN'i {payload.isbn} olan kitap zaten var.")
    # Tüm ayrıntılar sağlanırsa, kitabı doğrudan ekle
    elif payload.isbn and payload.title and payload.author:
        cover_url = f"http://{settings.api_host}:{settings.api_port}/covers/{payload.isbn}"
        book = Book(title=payload.title, author=payload.author, isbn=payload.isbn, cover_url=cover_url)
        return _add_book_to_library(book)
    else:
        raise HTTPException(status_code=422, detail="ISBN veya ISBN, Başlık ve Yazar sağlayın.")

@app.delete("/books/{isbn}", dependencies=[Depends(get_api_key)])
def delete_book(isbn: str):
    """ISBN'sine göre kütüphaneden bir kitabı sil."""
    if not library.remove_book(isbn):
        raise HTTPException(status_code=404, detail="Kitap bulunamadı.")
    # Bu ISBN ile ilgili önbellekleri geçersiz kıl
    invalidate_cache(f"enhanced:{isbn}")
    invalidate_cache(f"ai_summary:{isbn}")
    return {"message": "Kitap kaldırıldı."}

class UpdateBookModel(BaseModel):
    title: str | None = None
    author: str | None = None

@app.put("/books/{isbn}", response_model=BookModel, dependencies=[Depends(get_api_key)])
def update_book(isbn: str, update: UpdateBookModel):
    """ISBN'sine göre bir kitabın başlığını ve/veya yazarını güncelle."""
    if not update.title and not update.author:
        raise HTTPException(status_code=400, detail="Güncellemek için başlık ve/veya yazar sağlayın.")
    book = library.update_book(isbn, title=update.title, author=update.author)
    if not book:
        raise HTTPException(status_code=404, detail="Kitap bulunamadı.")
    # Bu ISBN ile ilgili önbellekleri geçersiz kıl
    invalidate_cache(f"enhanced:{isbn}")
    invalidate_cache(f"ai_summary:{isbn}")
    return BookModel(**book.to_dict())

class BookEnrichedModel(BookModel):
    cover_url: str | None = None
    publish_year: int | None = None
    publishers: List[str] | None = None
    subjects: List[str] | None = None
    description: str | None = None

# (yinelenen model bildirimleri kaldırıldı: EnhancedBookModel, AISummaryRequest, AISummaryResponse,
#  SentimentAnalysisRequest, SentimentAnalysisResponse, APIUsageStatsResponse)

@app.get("/books/{isbn}/enhanced", response_model=EnhancedBookModel)
def get_enhanced_book(isbn: str, request: Request, response: Response):
    """Google Books ve AI verileriyle geliştirilmiş kitap ayrıntılarını al."""
    try:
        book = library.find_book(isbn)
        if not book:
            raise HTTPException(status_code=404, detail="Kitap bulunamadı.")

        # Mevcut kitap sözlüğüne dayalı ETag (TTL boyunca kararlı)
        book_dict = book.to_dict()
        etag = _compute_etag_from_dict({"enhanced": True, **book_dict})
        cache_control = "public, max-age=300"
        # Koşullu GET işleme
        inm = request.headers.get("if-none-match")
        if inm == etag:
            return Response(status_code=304, headers={"ETag": etag, "Cache-Control": cache_control})

        # Gövde oluşturma için önbelleği dene (model örnekleri değil, düz sözlükleri sakla)
        cache_key = f"enhanced:{isbn}"
        cached = get_cached_response(cache_key)
        use_cached = False
        cached_payload: Dict[str, Any] | None = None
        if cached is not None:
            # Geriye dönük uyumluluk: sözlükleri veya önceden önbelleğe alınmış model örneklerini kabul et
            if isinstance(cached, dict):
                cached_payload = _normalize_enhanced_payload(cached)
            else:
                # Muhtemelen bir Pydantic model örneği; güvenli bir şekilde sözlüğe dönüştür
                try:
                    cached_payload = _normalize_enhanced_payload(cached.model_dump())  # Pydantic v2
                except AttributeError:
                    try:
                        cached_payload = _normalize_enhanced_payload(cached.dict())  # Pydantic v1
                    except Exception:
                        cached_payload = None
            # Yalnızca mevcut ETag ile aynı durumu temsil ediyorsa önbelleği kullan
            if cached_payload is not None:
                try:
                    cached_etag = _compute_etag_from_dict({"enhanced": True, **cached_payload})
                    use_cached = (cached_etag == etag)
                except Exception:
                    use_cached = False
        if use_cached and cached_payload is not None:
            result_model = EnhancedBookModel(**cached_payload)
        else:
            # Daha sonra tür sorunlarını önlemek için yeni model oluştur ve önbelleği sözlük olarak yenile
            book_dict = book.to_dict()
            fresh_payload = _normalize_enhanced_payload(book_dict)
            result_model = EnhancedBookModel(**fresh_payload)
            cache_response(cache_key, fresh_payload, ttl_seconds=300)

        # Normal yanıta başlıkları ayarla
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = cache_control
        return result_model
    except HTTPException:
        raise  # HTTP istisnalarını yeniden yükselt
    except Exception as e:
        print(f"Enhanced endpoint error for {isbn}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Sunucu hatası: {str(e)}")

@app.get("/books/{isbn}/enriched", response_model=BookEnrichedModel)
def get_enriched_book(isbn: str):
    """Open Library'den zenginleştirilmiş kitap ayrıntılarını al (eski uç nokta)."""
    book = library.find_book(isbn)
    if not book:
        raise HTTPException(status_code=404, detail="Kitap bulunamadı.")
    
    try:
        enriched_data = library.fetch_enriched_details(isbn)
        book_dict = book.to_dict()
        book_dict.update(enriched_data)
        return BookEnrichedModel(**book_dict)
    except Exception:
        # Zenginleştirme başarısız olursa temel kitap bilgilerini döndür
        book_dict = book.to_dict()
        book_dict['cover_url'] = f"http://{settings.api_host}:{settings.api_port}/covers/{isbn}"
        return BookEnrichedModel(**book_dict)

# --- AI Destekli Uç Noktalar ---
@app.get("/books/{isbn}/ai-summary", response_model=AISummaryResponse)
async def get_ai_summary(isbn: str, request: Request, response: Response):
    """Bir kitap için AI tarafından oluşturulmuş özeti al."""
    book = library.find_book(isbn)
    if not book:
        raise HTTPException(status_code=404, detail="Kitap bulunamadı.")

    # Önce önbelleği dene
    cache_key = f"ai_summary:{isbn}"
    cached = get_cached_response(cache_key)
    if cached is not None:
        # ETag'ı hesaplamadan önce önbelleğe alınmış yükü normalleştir (sözlük veya Pydantic modeli olabilir)
        cached_payload: Dict[str, Any] | None = None
        if isinstance(cached, dict):
            cached_payload = dict(cached)
        else:
            try:
                cached_payload = cached.model_dump()
            except AttributeError:
                try:
                    cached_payload = cached.dict()
                except Exception:
                    cached_payload = None
        if cached_payload is None:
            # Kullanılamaz önbellek girişi; geçersiz kıl ve yeni yola devam et
            invalidate_cache(cache_key)
        else:
            # Yükten yanıt modelini güvenli bir şekilde oluştur
            try:
                result = AISummaryResponse(**cached_payload)
            except Exception:
                # Önbelleğe alınmış yük isteğe bağlı alanları kaçırırsa minimal yeniden yapılandırma
                summary_text = str(cached_payload.get("summary", ""))
                result = AISummaryResponse(
                    isbn=str(cached_payload.get("isbn", isbn)),
                    summary=summary_text,
                    generated_at=str(cached_payload.get("generated_at", datetime.now().isoformat())),
                    summary_length=int(cached_payload.get("summary_length", len(summary_text))),
                    original_length=cached_payload.get("original_length"),
                    source=str(cached_payload.get("source", "hugging_face")),
                )
            # Önbelleğe alınmış sonuç için ETag/Cache-Control başlıkları
            data_for_etag = {"isbn": result.isbn, "summary": result.summary, "generated_at": result.generated_at}
            etag = _compute_etag_from_dict(data_for_etag)
            cache_control = "public, max-age=600"
            inm = request.headers.get("if-none-match")
            if inm == etag:
                return Response(status_code=304, headers={"ETag": etag, "Cache-Control": cache_control})
            response.headers["ETag"] = etag
            response.headers["Cache-Control"] = cache_control
            response.headers["Last-Modified"] = result.generated_at
            return result

    # AI özetinin zaten var olup olmadığını kontrol et
    if hasattr(book, 'ai_summary') and book.ai_summary:
        result = AISummaryResponse(
            isbn=isbn,
            summary=book.ai_summary,
            generated_at=book.ai_summary_generated_at or "unknown",
            summary_length=len(book.ai_summary),
            original_length=len(book.description) if book.description else None
        )
        # 10 dakika önbelleğe al
        cache_response(cache_key, result, ttl_seconds=600)
        # ETag/Önbellek başlıkları
        data_for_etag = {"isbn": isbn, "summary": result.summary, "generated_at": result.generated_at}
        etag = _compute_etag_from_dict(data_for_etag)
        cache_control = "public, max-age=600"
        inm = request.headers.get("if-none-match")
        if inm == etag:
            return Response(status_code=304, headers={"ETag": etag, "Cache-Control": cache_control})
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = cache_control
        response.headers["Last-Modified"] = result.generated_at
        return result

    # Yeni AI özeti oluştur
    try:
        async def _runner():
            return await library.generate_ai_summary(book)
        summary = await _coalesced_generate_ai_summary(isbn, _runner)
        if summary:
            result = AISummaryResponse(
                isbn=isbn,
                summary=summary,
                generated_at=datetime.now().isoformat(),
                summary_length=len(summary),
                original_length=len(book.description) if book.description else None
            )
            # 10 dakika önbelleğe al
            cache_response(cache_key, result, ttl_seconds=600)
            # Geliştirilmiş yük AI özetini içerir; yenilendiğinden emin ol
            invalidate_cache(f"enhanced:{isbn}")
            # ETag/Önbellek başlıkları
            data_for_etag = {"isbn": isbn, "summary": result.summary, "generated_at": result.generated_at}
            etag = _compute_etag_from_dict(data_for_etag)
            cache_control = "public, max-age=600"
            inm = request.headers.get("if-none-match")
            if inm == etag:
                return Response(status_code=304, headers={"ETag": etag, "Cache-Control": cache_control})
            response.headers["ETag"] = etag
            response.headers["Cache-Control"] = cache_control
            response.headers["Last-Modified"] = result.generated_at
            return result
        else:
            raise HTTPException(status_code=503, detail="AI özet hizmeti kullanılamıyor")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI özeti oluşturulamadı: {str(e)}")

@app.post("/books/{isbn}/generate-summary", response_model=AISummaryResponse, dependencies=[Depends(get_api_key)])
async def generate_ai_summary(isbn: str, request: AISummaryRequest, response: Response):
    """Bir kitap için AI özeti oluştur veya yeniden oluştur."""
    book = library.find_book(isbn)
    if not book:
        raise HTTPException(status_code=404, detail="Kitap bulunamadı.")
    
    # Yeniden oluşturmayı zorlamamız gerekip gerekmediğini kontrol et
    if not request.force_regenerate and hasattr(book, 'ai_summary') and book.ai_summary:
        result = AISummaryResponse(
            isbn=isbn,
            summary=book.ai_summary,
            generated_at=book.ai_summary_generated_at or "unknown",
            summary_length=len(book.ai_summary),
            original_length=len(book.description) if book.description else None
        )
        # Önbellekleme başlıklarını da ekle (POST yanıtında bile)
        data_for_etag = {"isbn": isbn, "summary": result.summary, "generated_at": result.generated_at}
        response.headers["ETag"] = _compute_etag_from_dict(data_for_etag)
        response.headers["Cache-Control"] = "public, max-age=600"
        response.headers["Last-Modified"] = result.generated_at
        return result
    
    try:
        # Yeniden oluşturmayı zorlarken önbelleği geçersiz kıl
        if request.force_regenerate:
            invalidate_cache(f"ai_summary:{isbn}")
        async def _runner():
            return await library.generate_ai_summary(book)
        summary = await _coalesced_generate_ai_summary(isbn, _runner)
        if summary:
            result = AISummaryResponse(
                isbn=isbn,
                summary=summary,
                generated_at=datetime.now().isoformat(),
                summary_length=len(summary),
                original_length=len(book.description) if book.description else None
            )
            # Önbelleği ve başlıkları güncelle
            cache_response(f"ai_summary:{isbn}", result, ttl_seconds=600)
            # Geliştirilmiş yük AI özetini içerir; yenilendiğinden emin ol
            invalidate_cache(f"enhanced:{isbn}")
            data_for_etag = {"isbn": isbn, "summary": result.summary, "generated_at": result.generated_at}
            response.headers["ETag"] = _compute_etag_from_dict(data_for_etag)
            response.headers["Cache-Control"] = "public, max-age=600"
            response.headers["Last-Modified"] = result.generated_at
            return result
        else:
            raise HTTPException(status_code=503, detail="AI özet hizmeti kullanılamıyor")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI özeti oluşturulamadı: {str(e)}")

@app.post("/books/{isbn}/analyze-sentiment", response_model=SentimentAnalysisResponse)
async def analyze_sentiment(isbn: str, request: SentimentAnalysisRequest):
    """Bir kitapla ilgili metnin duygu analizini yap."""
    book = library.find_book(isbn)
    if not book:
        raise HTTPException(status_code=404, detail="Kitap bulunamadı.")
    
    try:
        sentiment = await library.analyze_review_sentiment(request.text)
        if sentiment:
            return SentimentAnalysisResponse(
                text=request.text,
                label=sentiment['label'],
                score=sentiment['score'],
                analysis_time=datetime.now().isoformat()
            )
        else:
            raise HTTPException(status_code=503, detail="Duygu analizi hizmeti kullanılamıyor")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Duygu analizi yapılamadı: {str(e)}")

@app.get("/books/{isbn}/similar", response_model=List[EnhancedBookModel])
async def get_similar_books(isbn: str, limit: int = Query(5, ge=1, le=20)):
    """Google Books API'sini kullanarak benzer kitapları al."""
    book = library.find_book(isbn)
    if not book:
        raise HTTPException(status_code=404, detail="Kitap bulunamadı.")
    
    if not library.google_books or not library.google_books.is_available():
        raise HTTPException(status_code=503, detail="Google Books hizmeti kullanılamıyor")
    
    try:
        similar_books = await library.google_books.get_similar_books(isbn, limit)
        
        # Kitap formatımıza dönüştür ve kütüphanede olup olmadıklarını kontrol et
        result = []
        for gb_book in similar_books:
            # Kitabın kütüphanemizde olup olmadığını kontrol et
            existing_book = library.find_book(gb_book.isbn)
            if existing_book:
                result.append(EnhancedBookModel(**existing_book.to_dict()))
            else:
                # Görüntüleme için geçici bir kitap nesnesi oluştur
                temp_book_dict = {
                    "isbn": gb_book.isbn,
                    "title": gb_book.title,
                    "author": ", ".join(gb_book.authors) if gb_book.authors else "Bilinmeyen Yazar",
                    "cover_url": gb_book.thumbnail_url,
                    "page_count": gb_book.page_count,
                    "categories": gb_book.categories,
                    "published_date": gb_book.published_date,
                    "publisher": gb_book.publisher,
                    "language": gb_book.language,
                    "description": gb_book.description,
                    "google_rating": gb_book.average_rating,
                    "google_rating_count": gb_book.ratings_count,
                    "data_sources": ["google_books"]
                }
                result.append(EnhancedBookModel(**temp_book_dict))
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Benzer kitaplar alınamadı: {str(e)}")

# --- API Kullanım İstatistikleri ---
@app.get("/admin/api-usage", response_model=APIUsageStatsResponse)
def get_api_usage_stats():
    """Tüm hizmetler için API kullanım istatistiklerini al."""
    try:
        stats = library.get_enhanced_usage_stats()
        return APIUsageStatsResponse(**stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kullanım istatistikleri alınamadı: {str(e)}")

# --- Dışa/İçe Aktarma Uç Noktaları ---
@app.get("/export/json")
def export_books_json():
    """Tüm kitapları JSON olarak dışa aktar."""
    books = library.list_books()
    data = [b.to_dict() for b in books]
    return JSONResponse(
        content=data,
        headers={
            "Content-Disposition": f"attachment; filename=library_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        }
    )

@app.get("/export/csv")
def export_books_csv():
    """Tüm kitapları CSV olarak dışa aktar."""
    import csv
    import io
    
    books = library.list_books()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=['isbn', 'title', 'author'])
    writer.writeheader()
    
    for book in books:
        writer.writerow({
            'isbn': book.isbn,
            'title': book.title,
            'author': book.author
        })
    
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=library_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    )

@app.post("/import/json", dependencies=[Depends(get_api_key)])
async def import_books_json(request: Request):
    """JSON'dan kitapları içe aktar."""
    try:
        data = await request.json()
        imported_count = 0
        errors = []
        
        for item in data:
            try:
                if all(k in item for k in ['isbn', 'title', 'author']):
                    # İçe aktarma sırasında cover_url'yi kontrol et, yoksa None olarak bırak
                    cover_url = item.get('cover_url')
                    if not cover_url:
                        cover_url = None  # Cover URL'yi zorla oluşturma
                    
                    book = Book(
                        title=item['title'],
                        author=item['author'],
                        isbn=item['isbn'],
                        cover_url=cover_url
                    )
                    library.add_book(book)
                    imported_count += 1
            except ValueError as e:
                errors.append(f"ISBN {item.get('isbn', 'unknown')}: {str(e)}")
        
        return {
            "imported": imported_count,
            "errors": errors,
            "message": f"Successfully imported {imported_count} books"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"İçe aktarma başarısız: {str(e)}")

# --- Gelişmiş İstatistikler ---
class ExtendedStatsModel(BaseModel):
    total_books: int
    unique_authors: int
    most_common_author: Optional[str]
    books_by_author: Dict[str, int]
    recent_additions: List[BookModel]
    total_favorites: int = 0
    total_reading_list: int = 0

@app.get("/stats/extended", response_model=ExtendedStatsModel)
def get_extended_stats():
    """Kütüphane hakkında genişletilmiş istatistikleri al."""
    books = library.list_books()
    stats = library.get_statistics()
    
    # Yazara göre kitapları say
    author_counts: Dict[str, int] = {}
    for book in books:
        author_counts[book.author] = author_counts.get(book.author, 0) + 1
    
    # En yaygın yazarı bul
    most_common_author = None
    if author_counts:
        # dict.get aşırı yüklemeleriyle ilgili yazım sorunlarını önlemek için açık lambda kullan
        most_common_author = max(author_counts, key=lambda k: author_counts[k])
    
    # Son eklenenleri al (son 5)
    recent_books = books[-5:] if len(books) > 0 else []
    
    return ExtendedStatsModel(
        total_books=stats["total_books"],
        unique_authors=stats["unique_authors"],
        most_common_author=most_common_author,
        books_by_author=dict(sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
        recent_additions=[BookModel(**b.to_dict()) for b in recent_books]
    )

# --- Sağlık Kontrolü ---
@app.get("/health")
def health_check():
    """Sağlık kontrolü uç noktası."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "total_books": len(library.list_books())
    }

@app.post("/test-post")
def test_post():
    return {"message": "POST isteği başarıyla alındı!"}

# --- İnceleme/Puanlama Uç Noktaları ---
class ReviewModel(BaseModel):
    id: Optional[int] = None
    isbn: str
    user_name: str
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None
    created_at: Optional[str] = None

class ReviewCreateModel(BaseModel):
    user_name: str
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None

@app.get("/books/{isbn}/reviews", response_model=List[ReviewModel])
def get_book_reviews(isbn: str):
    """Belirli bir kitap için tüm incelemeleri al."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, isbn, user_name, rating, comment, created_at 
        FROM reviews 
        WHERE isbn = ?
        ORDER BY created_at DESC
    """, (isbn,))
    
    reviews = cursor.fetchall()
    conn.close()
    
    return [
        ReviewModel(
            id=r['id'],
            isbn=r['isbn'],
            user_name=r['user_name'],
            rating=r['rating'],
            comment=r['comment'],
            created_at=r['created_at']
        ) for r in reviews
    ]

@app.post("/books/{isbn}/reviews", response_model=ReviewModel)
def add_book_review(isbn: str, review: ReviewCreateModel):
    """Belirli bir kitap için bir inceleme ekle."""
    # Kitabın var olup olmadığını kontrol et
    book = library.find_book(isbn)
    if not book:
        raise HTTPException(status_code=404, detail="Kitap bulunamadı.")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO reviews (isbn, user_name, rating, comment)
        VALUES (?, ?, ?, ?)
    """, (isbn, review.user_name, review.rating, review.comment))
    
    review_id = cursor.lastrowid
    conn.commit()
    
    # Oluşturulan incelemeyi getir
    cursor.execute("""
        SELECT id, isbn, user_name, rating, comment, created_at 
        FROM reviews 
        WHERE id = ?
    """, (review_id,))
    
    new_review = cursor.fetchone()
    conn.close()
    
    return ReviewModel(
        id=new_review['id'],
        isbn=new_review['isbn'],
        user_name=new_review['user_name'],
        rating=new_review['rating'],
        comment=new_review['comment'],
        created_at=new_review['created_at']
    )

@app.get("/books/{isbn}/rating")
def get_book_rating(isbn: str):
    """Bir kitap için ortalama puanı ve inceleme sayısını al."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT AVG(rating) as avg_rating, COUNT(*) as review_count
        FROM reviews
        WHERE isbn = ?
    """, (isbn,))
    
    result = cursor.fetchone()
    conn.close()
    
    return {
        "isbn": isbn,
        "average_rating": result['avg_rating'] if result['avg_rating'] else 0,
        "review_count": result['review_count']
    }

# --- Etiket Uç Noktaları ---
class TagModel(BaseModel):
    id: Optional[int] = None
    name: str
    color: str = '#3B82F6'
    book_count: Optional[int] = 0

class TagCreateModel(BaseModel):
    name: str
    color: str = '#3B82F6'

@app.get("/tags", response_model=List[TagModel])
def get_all_tags():
    """Kitap sayılarıyla birlikte mevcut tüm etiketleri al."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT t.id, t.name, t.color, COUNT(bt.isbn) as book_count
        FROM tags t
        LEFT JOIN book_tags bt ON t.id = bt.tag_id
        GROUP BY t.id, t.name, t.color
        ORDER BY t.name
    """)
    
    tags = cursor.fetchall()
    conn.close()
    
    return [
        TagModel(
            id=t['id'],
            name=t['name'],
            color=t['color'],
            book_count=t['book_count']
        ) for t in tags
    ]

@app.post("/tags", response_model=TagModel)
def create_tag(tag: TagCreateModel):
    """Yeni bir etiket oluştur."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO tags (name, color)
            VALUES (?, ?)
        """, (tag.name, tag.color))
        
        tag_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return TagModel(id=tag_id, name=tag.name, color=tag.color, book_count=0)
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Etiket zaten var.")

@app.get("/books/{isbn}/tags", response_model=List[TagModel])
def get_book_tags(isbn: str):
    """Belirli bir kitap için tüm etiketleri al."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT t.id, t.name, t.color
        FROM tags t
        JOIN book_tags bt ON t.id = bt.tag_id
        WHERE bt.isbn = ?
        ORDER BY t.name
    """, (isbn,))
    
    tags = cursor.fetchall()
    conn.close()
    
    return [
        TagModel(id=t['id'], name=t['name'], color=t['color'])
        for t in tags
    ]

@app.post("/books/{isbn}/tags")
def add_tag_to_book(isbn: str, tag_id: int = Body(...)):
    """Bir kitaba etiket ekle."""
    # Kitabın var olup olmadığını kontrol et
    book = library.find_book(isbn)
    if not book:
        raise HTTPException(status_code=404, detail="Kitap bulunamadı.")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO book_tags (isbn, tag_id)
            VALUES (?, ?)
        """, (isbn, tag_id))
        
        conn.commit()
        conn.close()
        
        return {"message": "Etiket başarıyla eklendi"}
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Etiket zaten bu kitaba atanmış.")

@app.delete("/books/{isbn}/tags/{tag_id}")
def remove_tag_from_book(isbn: str, tag_id: int):
    """Bir kitaptan etiketi kaldır."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        DELETE FROM book_tags
        WHERE isbn = ? AND tag_id = ?
    """, (isbn, tag_id))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    if affected == 0:
        raise HTTPException(status_code=404, detail="Bu kitap için etiket bulunamadı.")
    
    return {"message": "Etiket başarıyla kaldırıldı"}

# (Google Books tabanlı olanla ad çakışmasını önlemek için yinelenen yerel öneri uç noktası kaldırıldı)

# --- Filtrelerle Gelişmiş Arama ---
@app.post("/books/search/enhanced", response_model=List[BookModel])
def enhanced_search(params: AdvancedSearchParams):
    """Yıl aralığı ve etiketler dahil olmak üzere birden çok filtreli geliştirilmiş arama."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT DISTINCT b.* FROM books b"
    conditions = []
    joins = []
    query_params = []
    
    # Puan filtresi belirtilmişse incelemelerle birleştir
    if params.min_rating:
        joins.append("LEFT JOIN reviews r ON b.isbn = r.isbn")
    
    # Etiket filtresi belirtilmişse etiketlerle birleştir
    if params.tag_ids:
        joins.append("JOIN book_tags bt ON b.isbn = bt.isbn")
    
    # Sorguya birleştirmeler ekle
    if joins:
        query += " " + " ".join(joins)
    
    # Koşulları oluştur
    if params.title:
        conditions.append("b.title LIKE ?")
        query_params.append(f"%{params.title}%")
    
    if params.author:
        conditions.append("b.author LIKE ?")
        query_params.append(f"%{params.author}%")
    
    if params.isbn:
        conditions.append("b.isbn LIKE ?")
        query_params.append(f"%{params.isbn}%")
    
    if params.publish_year_from:
        conditions.append("b.publish_year >= ?")
        query_params.append(params.publish_year_from)
    
    if params.publish_year_to:
        conditions.append("b.publish_year <= ?")
        query_params.append(params.publish_year_to)
    
    if params.tag_ids:
        placeholders = ",".join("?" * len(params.tag_ids))
        conditions.append(f"bt.tag_id IN ({placeholders})")
        query_params.extend(params.tag_ids)
    
    # Koşullar varsa WHERE yan tümcesi ekle
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    # Puan filtresi için GROUP BY ve HAVING ekle
    if params.min_rating:
        query += " GROUP BY b.isbn HAVING AVG(r.rating) >= ?"
        query_params.append(params.min_rating)
    
    cursor.execute(query, query_params)
    results = cursor.fetchall()
    conn.close()
    
    books = []
    for row in results:
        book_dict = {
            'isbn': row['isbn'],
            'title': row['title'],
            'author': row['author'],
            'cover_url': row['cover_url'],
            'created_at': row['created_at']
        }
        books.append(Book.from_dict(book_dict))
    
    return [BookModel(**b.to_dict()) for b in books]

# --- Statik Dosyalar ---
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    """Ana HTML sayfasını sun."""
    return FileResponse('static/index.html')