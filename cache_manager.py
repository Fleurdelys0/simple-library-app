"""
Gelişmiş performans için Redis destekli gelişmiş önbellek yöneticisi.
Redis kullanılamıyorsa bellek içi önbelleğe geri döner.
"""

import json
import logging
import pickle
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union
import hashlib
import threading
from functools import wraps

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from config import settings

logger = logging.getLogger(__name__)

class CacheManager:
    """Redis ve bellek içi geri dönüşlü yüksek performanslı önbellek yöneticisi."""
    
    def __init__(self):
        self.redis_client = None
        self.memory_cache = {}
        self.memory_cache_lock = threading.RLock()
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'redis_hits': 0,
            'memory_hits': 0
        }
        
        # Redis'i başlatmayı dene
        self._init_redis()
    
    def _init_redis(self):
        """Varsa Redis bağlantısını başlat."""
        if not REDIS_AVAILABLE:
            logger.info("Redis mevcut değil, yalnızca bellek içi önbellek kullanılıyor")
            return
        
        try:
            redis_url = getattr(settings, 'redis_url', 'redis://localhost:6379/0')
            self.redis_client = redis.from_url(
                redis_url,
                decode_responses=False,  # Kodlamayı kendimiz halledeceğiz
                socket_connect_timeout=1,
                socket_timeout=1,
                retry_on_timeout=True,
                health_check_interval=30
            )
            # Bağlantıyı test et
            self.redis_client.ping()
            logger.info("Redis önbelleği başarıyla başlatıldı")
        except Exception as e:
            logger.warning(f"Redis başlatılamadı: {e}. Yalnızca bellek önbelleği kullanılıyor.")
            self.redis_client = None
    
    def _make_key(self, key: str) -> str:
        """Önek ile tutarlı bir önbellek anahtarı oluştur."""
        return f"library_cache:{key}"
    
    def _serialize_value(self, value: Any) -> bytes:
        """Depolama için değeri serileştir."""
        try:
            # Basit türler için önce JSON'u dene (daha taşınabilir)
            json_str = json.dumps(value, default=str, ensure_ascii=False)
            return b'j:' + json_str.encode('utf-8')
        except (TypeError, ValueError):
            # Karmaşık nesneler için pickle'a geri dön
            return b'p:' + pickle.dumps(value)
    
    def _deserialize_value(self, data: bytes) -> Any:
        """Depolamadan değeri seri durumdan çıkar."""
        if data.startswith(b'j:'):
            return json.loads(data[2:].decode('utf-8'))
        elif data.startswith(b'p:'):
            return pickle.loads(data[2:])
        else:
            # Eski destek
            try:
                return json.loads(data.decode('utf-8'))
            except:
                return pickle.loads(data)
    
    def get(self, key: str) -> Optional[Any]:
        """Önbellekten değer al."""
        cache_key = self._make_key(key)
        
        # Önce Redis'i dene
        if self.redis_client:
            try:
                data = self.redis_client.get(cache_key)
                if data is not None:
                    self.cache_stats['hits'] += 1
                    self.cache_stats['redis_hits'] += 1
                    return self._deserialize_value(data)
            except Exception as e:
                logger.warning(f"Redis get hatası: {e}")
        
        # Bellek önbelleğine geri dön
        with self.memory_cache_lock:
            cache_entry = self.memory_cache.get(key)
            if cache_entry:
                value, expires_at = cache_entry
                if datetime.now() < expires_at:
                    self.cache_stats['hits'] += 1
                    self.cache_stats['memory_hits'] += 1
                    return value
                else:
                    # Süresi dolmuş, kaldır
                    del self.memory_cache[key]
        
        self.cache_stats['misses'] += 1
        return None
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> bool:
        """Önbellekte TTL ile değer ayarla."""
        cache_key = self._make_key(key)
        serialized_value = self._serialize_value(value)
        
        # Varsa Redis'te sakla
        redis_success = False
        if self.redis_client:
            try:
                self.redis_client.setex(cache_key, ttl_seconds, serialized_value)
                redis_success = True
            except Exception as e:
                logger.warning(f"Redis set hatası: {e}")
        
        # Ayrıca yedek olarak bellek önbelleğinde sakla
        with self.memory_cache_lock:
            expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
            self.memory_cache[key] = (value, expires_at)
            
            # Bellek önbellek boyutunu sınırla (yalnızca en son 1000 öğeyi tut)
            if len(self.memory_cache) > 1000:
                # En eski öğelerin %10'unu kaldır
                sorted_items = sorted(
                    self.memory_cache.items(), 
                    key=lambda x: x[1][1]  # Son kullanma tarihine göre sırala
                )
                for k, _ in sorted_items[:100]:
                    self.memory_cache.pop(k, None)
        
        return redis_success or True  # Bellekte sakladıysak her zaman True döndür
    
    def delete(self, key: str) -> bool:
        """Önbellekten anahtarı sil."""
        cache_key = self._make_key(key)
        
        redis_deleted = False
        if self.redis_client:
            try:
                redis_deleted = bool(self.redis_client.delete(cache_key))
            except Exception as e:
                logger.warning(f"Redis delete hatası: {e}")
        
        with self.memory_cache_lock:
            memory_deleted = key in self.memory_cache
            self.memory_cache.pop(key, None)
        
        return redis_deleted or memory_deleted
    
    def invalidate_pattern(self, pattern: str) -> int:
        """Desenle eşleşen tüm anahtarları geçersiz kıl."""
        cache_pattern = self._make_key(pattern)
        count = 0
        
        # Redis'ten geçersiz kıl
        if self.redis_client:
            try:
                keys = self.redis_client.keys(cache_pattern)
                if keys:
                    count += self.redis_client.delete(*keys)
            except Exception as e:
                logger.warning(f"Redis desen geçersiz kılma hatası: {e}")
        
        # Bellek önbelleğinden geçersiz kıl
        with self.memory_cache_lock:
            keys_to_remove = []
            # Bellek önbelleği için deseni basit önek eşleştirmeye dönüştür
            prefix = pattern.replace('*', '')
            for key in self.memory_cache:
                if key.startswith(prefix):
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                self.memory_cache.pop(key, None)
                count += 1
        
        return count
    
    def clear(self) -> bool:
        """Tüm önbelleği temizle."""
        redis_cleared = False
        if self.redis_client:
            try:
                pattern = self._make_key("*")
                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
                redis_cleared = True
            except Exception as e:
                logger.warning(f"Redis temizleme hatası: {e}")
        
        with self.memory_cache_lock:
            self.memory_cache.clear()
        
        return redis_cleared
    
    def get_stats(self) -> Dict[str, Any]:
        """Önbellek istatistiklerini al."""
        stats = self.cache_stats.copy()
        stats['redis_available'] = self.redis_client is not None
        stats['memory_cache_size'] = len(self.memory_cache)
        
        if stats['hits'] + stats['misses'] > 0:
            stats['hit_ratio'] = stats['hits'] / (stats['hits'] + stats['misses'])
        else:
            stats['hit_ratio'] = 0.0
        
        return stats

# Global önbellek yöneticisi örneği
cache_manager = CacheManager()

def cached(ttl_seconds: int = 300, key_prefix: str = ""):
    """İşlev sonuçlarını önbelleğe almak için dekoratör."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # İşlev adı ve argümanlarından önbellek anahtarı oluştur
            func_name = f"{key_prefix}:{func.__name__}" if key_prefix else func.__name__
            
            # Tutarlı anahtar için argümanlardan bir karma oluştur
            args_str = str(args) + str(sorted(kwargs.items()))
            args_hash = hashlib.md5(args_str.encode('utf-8')).hexdigest()
            cache_key = f"{func_name}:{args_hash}"
            
            # Önbellekten almayı dene
            result = cache_manager.get(cache_key)
            if result is not None:
                return result
            
            # İşlevi yürüt ve sonucu önbelleğe al
            result = func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl_seconds)
            return result
        
        # Dekore edilmiş işleve önbellek kontrol yöntemleri ekle
        wrapper.clear_cache = lambda: cache_manager.invalidate_pattern(f"{key_prefix}:{func.__name__}:*")
        wrapper.cache_info = lambda: cache_manager.get_stats()
        
        return wrapper
    return decorator