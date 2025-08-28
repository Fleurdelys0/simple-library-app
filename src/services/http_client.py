import httpx
import asyncio
import time
from typing import Optional, Dict, Any, List
from config.config import settings
import logging
from datetime import datetime, timedelta
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

# HTTP/2'nin mevcut olup olmadığını belirle ('h2' paketi gerektirir)
try:
    import h2  # type: ignore
    _HTTP2_AVAILABLE = True
except Exception:
    _HTTP2_AVAILABLE = False
    logger.debug("HTTP/2 devre dışı: 'h2' paketi yüklü değil.")


class OptimizedHTTPClient:
    """Bağlantı havuzu ve yeniden deneme mantığı ile optimize edilmiş HTTP istemcisi"""
    
    def __init__(self):
        # Daha iyi performans için bağlantı limitleri
        limits = httpx.Limits(
            max_keepalive_connections=20,
            max_connections=100,
            keepalive_expiry=30.0
        )
        
        # Zaman aşımı yapılandırması
        timeout = httpx.Timeout(
            timeout=10.0,
            connect=5.0,
            read=10.0,
            write=5.0
        )
        
        self._client = httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            follow_redirects=True,
            http2=_HTTP2_AVAILABLE  # Yalnızca 'h2' mevcutsa HTTP/2'yi etkinleştir
        )
        
        # Geriye dönük uyumluluk için senkron istemci
        self._sync_client = httpx.Client(
            limits=limits,
            timeout=timeout,
            follow_redirects=True
        )
    
    async def get(self, url: str, **kwargs) -> httpx.Response:
        """Bağlantı havuzu ile asenkron GET isteği"""
        return await self._client.get(url, **kwargs)
    
    async def post(self, url: str, **kwargs) -> httpx.Response:
        """Bağlantı havuzu ile asenkron POST isteği"""
        return await self._client.post(url, **kwargs)
    
    def get_sync(self, url: str, **kwargs) -> httpx.Response:
        """Geriye dönük uyumluluk için senkron GET isteği"""
        return self._sync_client.get(url, **kwargs)
    
    async def get_with_retry(self, url: str, retries: int = 3, backoff: float = 0.5, **kwargs) -> Optional[httpx.Response]:
        """Üstel geri çekilme yeniden deneme mantığı ile GET isteği"""
        for attempt in range(retries):
            try:
                response = await self.get(url, **kwargs)
                return response
            except httpx.RequestError as e:
                if attempt < retries - 1:
                    wait_time = backoff * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                    continue
                return None
            except Exception:
                return None
        return None
    
    async def close(self):
        """HTTP istemcilerini kapat"""
        await self._client.aclose()
        self._sync_client.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Global HTTP istemci örneği
_global_client: Optional[OptimizedHTTPClient] = None


async def get_http_client() -> OptimizedHTTPClient:
    """Global HTTP istemci örneğini al veya oluştur"""
    global _global_client
    if _global_client is None:
        _global_client = OptimizedHTTPClient()
    return _global_client


async def cleanup_http_client():
    """Global HTTP istemcisini temizle"""
    global _global_client
    if _global_client:
        await _global_client.close()
        _global_client = None