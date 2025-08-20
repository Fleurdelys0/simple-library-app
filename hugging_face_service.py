import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum

import httpx

from config import settings
from http_client import get_http_client
from database import get_db_connection


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SentimentLabel(Enum):
    """Sentiment analizi etiketleri"""
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"


@dataclass
class SentimentResult:
    """Sentiment analizi sonucu"""
    label: SentimentLabel
    score: float  # Confidence score between 0 and 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label.value,
            "score": self.score
        }


@dataclass
class SummaryResult:
    """Metin özetinin sonucu"""
    summary: str
    original_length: int
    summary_length: int
    compression_ratio: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "original_length": self.original_length,
            "summary_length": self.summary_length,
            "compression_ratio": self.compression_ratio
        }


class HuggingFaceAPIError(Exception):
    """Hugging Face API için özel hata"""
    pass


class RateLimitExceeded(HuggingFaceAPIError):
    """Rate limit exceeded"""
    pass


class CharacterLimitExceeded(HuggingFaceAPIError):
    """Character limit exceeded"""
    pass


class HuggingFaceService:
    """Hugging Face API ile AI metin işleme için servis"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.hugging_face_api_key
        self.base_url = "https://api-inference.huggingface.co"
        self.monthly_limit = settings.hugging_face_monthly_limit
        self.timeout = settings.hugging_face_timeout
        
        # Model endpoints
        self.summarization_model = "facebook/bart-large-cnn"
        self.sentiment_model = "cardiffnlp/twitter-roberta-base-sentiment"
        # Translation models
        self.translation_model_en_tr = "Helsinki-NLP/opus-mt-en-tr"
        
        # Initialize usage tracking
        self._init_usage_tracking()
    
    def _init_usage_tracking(self) -> None:
        """Veritabanında kullanım izleme"""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Create API usage logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_usage_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_name TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    success BOOLEAN NOT NULL,
                    response_time_ms INTEGER,
                    characters_used INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create usage stats table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_usage_stats (
                    id INTEGER PRIMARY KEY,
                    hugging_face_monthly_chars INTEGER DEFAULT 0,
                    last_reset_date TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert initial record if not exists
            cursor.execute("SELECT COUNT(*) FROM api_usage_stats")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO api_usage_stats (hugging_face_monthly_chars, last_reset_date)
                    VALUES (0, ?)
                """, (datetime.now().strftime("%Y-%m-%d"),))
            
            conn.commit()
        finally:
            conn.close()
    
    def _check_character_limit(self, text: str) -> bool:
        """Monthly character limit exceeded"""
        current_usage = self._get_monthly_usage()
        text_length = len(text)
        
        if current_usage + text_length > self.monthly_limit:
            logger.warning(f"Character limit would be exceeded: {current_usage + text_length}/{self.monthly_limit}")
            return False
        
        return True
    
    def _get_monthly_usage(self) -> int:
        """Get current monthly character usage"""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT hugging_face_monthly_chars, last_reset_date FROM api_usage_stats WHERE id = 1")
            row = cursor.fetchone()
            
            if not row:
                return 0
            
            usage, last_reset = row
            
            # Check if we need to reset monthly counter
            last_reset_date = datetime.strptime(last_reset, "%Y-%m-%d")
            current_date = datetime.now()
            
            # Reset if it's a new month
            if (current_date.year > last_reset_date.year or 
                current_date.month > last_reset_date.month):
                cursor.execute("""
                    UPDATE api_usage_stats 
                    SET hugging_face_monthly_chars = 0, 
                        last_reset_date = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, (current_date.strftime("%Y-%m-%d"),))
                conn.commit()
                return 0
            
            return usage
        finally:
            conn.close()
    
    def _log_api_usage(self, model: str, characters_used: int, success: bool, response_time_ms: int = 0) -> None:
        """API kullanımını veritabanına kaydet"""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # API çağrısını kaydet
            cursor.execute("""
                INSERT INTO api_usage_logs (api_name, endpoint, success, response_time_ms, characters_used)
                VALUES (?, ?, ?, ?, ?)
            """, ("hugging_face", model, success, response_time_ms, characters_used))
            
            # Update monthly usage if successful
            if success:
                cursor.execute("""
                    UPDATE api_usage_stats 
                    SET hugging_face_monthly_chars = hugging_face_monthly_chars + ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, (characters_used,))
            
            conn.commit()
            logger.info(f"HuggingFace API usage logged: model={model}, chars={characters_used}, success={success}")
        except Exception as e:
            logger.error(f"Failed to log API usage: {e}")
        finally:
            conn.close()
    
    async def _make_api_request(self, model: str, payload: Dict[str, Any]) -> Optional[List[Any]]:
        """Make an API request to Hugging Face
        
        Note: For the summarization and sentiment endpoints we use, the
        API returns a JSON array (list) of results. We reflect that in
        the return type so downstream indexing like response[0] is
        type-safe for Pyright.
        """
        if not self.api_key:
            logger.warning("Hugging Face API key not configured")
            return None
        
        url = f"{self.base_url}/models/{model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                
                response_time_ms = int((time.time() - start_time) * 1000)
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    logger.warning("Rate limit exceeded for Hugging Face API")
                    raise RateLimitExceeded("Rate limit exceeded")
                else:
                    logger.error(f"API request failed: {response.status_code} - {response.text}")
                    return None
                    
        except httpx.TimeoutException:
            logger.error(f"API request timed out after {self.timeout}s")
            return None
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return None
    
    async def summarize_text(self, text: str, max_length: int = 150, min_length: int = 30) -> Optional[SummaryResult]:
        """
        Metin özetleme
        
        Args:
            text: Text to summarize
            max_length: Maximum length of summary
            min_length: Minimum length of summary
            
        Returns:
            SummaryResult object or None if failed
        """
        if not text or len(text.strip()) < 50:
            logger.warning("Text too short for summarization")
            return None
        
        # Check character limit
        if not self._check_character_limit(text):
            raise CharacterLimitExceeded("Monthly character limit would be exceeded")
        
        # Truncate text if too long (BART has a limit)
        max_input_length = 1024
        if len(text) > max_input_length:
            text = text[:max_input_length] + "..."
            logger.info(f"Text truncated to {max_input_length} characters for summarization")
        
        payload = {
            "inputs": text,
            "parameters": {
                "max_length": max_length,
                "min_length": min_length,
                "do_sample": False
            }
        }
        
        start_time = time.time()
        characters_used = len(text)
        
        try:
            response = await self._make_api_request(self.summarization_model, payload)
            response_time_ms = int((time.time() - start_time) * 1000)
            
            if response and isinstance(response, list) and len(response) > 0:
                first = response[0]
                if isinstance(first, dict):
                    raw_summary = first.get("summary_text", "")
                    summary_text = str(raw_summary).strip()
                    if summary_text:
                        result = SummaryResult(
                            summary=summary_text,
                            original_length=len(text),
                            summary_length=len(summary_text),
                            compression_ratio=len(summary_text) / len(text)
                        )
                        
                        self._log_api_usage(self.summarization_model, characters_used, True, response_time_ms)
                        logger.info(f"Text summarized successfully: {len(text)} -> {len(summary_text)} chars")
                        return result
            
            self._log_api_usage(self.summarization_model, characters_used, False)
            return None
            
        except Exception as e:
            self._log_api_usage(self.summarization_model, characters_used, False)
            logger.error(f"Summarization failed: {e}")
            return None

    async def _translate_to_turkish(self, text: str) -> Optional[str]:
        """Metni Türkçe'ye çevir"""
        if not text:
            return None
        if not self._check_character_limit(text):
            raise CharacterLimitExceeded("Monthly character limit would be exceeded")

        payload = {"inputs": text}
        start_time = time.time()
        characters_used = len(text)

        try:
            response = await self._make_api_request(self.translation_model_en_tr, payload)
            response_time_ms = int((time.time() - start_time) * 1000)
            if response and isinstance(response, list) and len(response) > 0:
                first = response[0]
                if isinstance(first, dict):
                    translated = str(first.get("translation_text", "")).strip()
                    if translated:
                        self._log_api_usage(self.translation_model_en_tr, characters_used, True, response_time_ms)
                        return translated
            self._log_api_usage(self.translation_model_en_tr, characters_used, False)
            return None
        except Exception as e:
            self._log_api_usage(self.translation_model_en_tr, characters_used, False)
            logger.error(f"Translation failed: {e}")
            return None

    async def analyze_sentiment(self, text: str) -> Optional[SentimentResult]:
        """
        Metin sentimantasyonu analizi
        
        Argüman:
            text: Metin
            
        Dönüt:
            SentimentResult nesnesi veya başarısız olursa None
        """
        if not text or len(text.strip()) < 5:
            logger.warning("Text too short for sentiment analysis")
            return None
        
        # Check character limit
        if not self._check_character_limit(text):
            raise CharacterLimitExceeded("Monthly character limit would be exceeded")
        
        # Truncate text if too long
        max_input_length = 512
        if len(text) > max_input_length:
            text = text[:max_input_length]
            logger.info(f"Text truncated to {max_input_length} characters for sentiment analysis")
        
        payload = {"inputs": text}
        
        start_time = time.time()
        characters_used = len(text)
        
        try:
            response = await self._make_api_request(self.sentiment_model, payload)
            response_time_ms = int((time.time() - start_time) * 1000)
            
            if response and isinstance(response, list) and len(response) > 0:
                # En yüksek puanlı sentiment
                sentiments = response[0]
                if isinstance(sentiments, list) and len(sentiments) > 0:
                    dict_items = [s for s in sentiments if isinstance(s, dict)]
                    if dict_items:
                        best_sentiment = max(
                            dict_items,
                            key=lambda x: float(x.get("score", 0) or 0)
                        )
                        
                        label_mapping = {
                            "LABEL_0": SentimentLabel.NEGATIVE,
                            "LABEL_1": SentimentLabel.NEUTRAL,
                            "LABEL_2": SentimentLabel.POSITIVE,
                            "NEGATIVE": SentimentLabel.NEGATIVE,
                            "NEUTRAL": SentimentLabel.NEUTRAL,
                            "POSITIVE": SentimentLabel.POSITIVE
                        }
                        
                        raw_label = str(best_sentiment.get("label", "NEUTRAL"))
                        sentiment_label = label_mapping.get(raw_label, SentimentLabel.NEUTRAL)
                        score = float(best_sentiment.get("score", 0.0) or 0.0)
                        
                        result = SentimentResult(label=sentiment_label, score=score)
                        
                        self._log_api_usage(self.sentiment_model, characters_used, True, response_time_ms)
                        logger.info(f"Sentiment analyzed: {sentiment_label.value} (score: {score:.3f})")
                        return result
            
            self._log_api_usage(self.sentiment_model, characters_used, False)
            return None
            
        except Exception as e:
            self._log_api_usage(self.sentiment_model, characters_used, False)
            logger.error(f"Sentiment analysis failed: {e}")
            return None
    
    async def generate_book_summary(self, title: str, author: str, description: str = "") -> Optional[str]:
        """
        Kitap özeti oluştur
        
        Argüman:
            title: Kitap başlığı
            author: Kitap yazarı
            description: Kitap açıklaması (opsiyonel)
            
        Dönüt:
            Kitap özeti veya başarısız olursa None
        """
        desc = (description or "").strip()

        # Helper to take the first 1–2 sentences from the description as a concise blurb
        def take_first_sentences(text: str, max_chars: int = 240, max_sents: int = 2) -> str:
            normalized = " ".join(text.replace("\n", " ").split())
            parts = [p.strip() for p in normalized.split('.') if p.strip()]
            out: list[str] = []
            total = 0
            for p in parts:
                # +2 accounts for '. ' joining
                add_len = len(p) + (2 if out else 0)
                if len(out) < max_sents and total + add_len <= max_chars:
                    out.append(p)
                    total += add_len
                else:
                    break
            return ('. '.join(out) + ('.' if out else '')).strip()

        preferred_lang = (settings.ai_summary_language or "tr").lower()

        # Sufficiently informative descriptions için özeti oluştur
        if desc:
            try:
                # Uzun açıklamalar için özeti oluştur
                if len(desc) >= 500:
                    summary_result = await self.summarize_text(desc, max_length=120, min_length=50)
                    if summary_result and summary_result.summary:
                        summary_text = summary_result.summary.strip()
                        if preferred_lang == "tr":
                            translated = await self._translate_to_turkish(summary_text)
                            if translated:
                                return translated
                            # Çeviri başarısız olsa bile Türkçe özeti oluştur
                            return (
                                f"{author} tarafından yazılan '{title}', temel fikir ve temalarının kısa bir özetini sunar; "
                                f"okura konusunu ve neden ilgi çekici olduğunu net biçimde aktarır."
                            )
                        return summary_text
                elif len(desc) >= 120:
                    summary_result = await self.summarize_text(desc, max_length=100, min_length=40)
                    if summary_result and summary_result.summary:
                        summary_text = summary_result.summary.strip()
                        if preferred_lang == "tr":
                            translated = await self._translate_to_turkish(summary_text)
                            if translated:
                                return translated
                            # Çeviri başarısız olsa bile Türkçe özeti oluştur
                            return (
                                f"{author} tarafından yazılan '{title}', temel fikir ve temalarının kısa bir özetini sunar; "
                                f"okura konusunu ve neden ilgi çekici olduğunu net biçimde aktarır."
                            )
                        return summary_text
            except Exception:
                # Özeti oluştururken herhangi bir sorun olursa, alttaki çıkarımı kullan
                pass

            # Yedek: ilk bir veya iki cümleyi kısa bir açıklama olarak çıkar
            extracted = take_first_sentences(desc)
            if extracted:
                # Başlık/yazar öne çıkarmak için bağlam ver
                if preferred_lang == "tr":
                    # Çıkarılan kısmını da çeviri
                    translated_extracted = await self._translate_to_turkish(extracted)
                    if translated_extracted:
                        body = translated_extracted
                    else:
                        # Çeviri başarısız olsa bile Türkçe özeti oluştur
                        body = "kısa bir özet mevcut değil; temel konu ve temalara odaklanan genel bir bakış sunar."
                    return f"{author} tarafından yazılan '{title}': {body}"
                return f"{title} by {author}: {extracted}"

        # Final fallback: craft a short, informative generic summary rather than only title/author
        if preferred_lang == "tr":
            return (
                f"{author} tarafından yazılan '{title}', temel fikir ve temalarının kısa bir özetini sunar; "
                f"okura konusunu ve neden ilgi çekici olduğunu net biçimde aktarır."
            )
        return (
            f"'{title}' by {author} offers a concise overview of its core ideas and themes, "
            f"providing readers with a clear sense of its premise and appeal."
        )
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get current API usage statistics"""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Aylık kullanım
            cursor.execute("SELECT hugging_face_monthly_chars, last_reset_date FROM api_usage_stats WHERE id = 1")
            row = cursor.fetchone()
            
            monthly_usage = row[0] if row else 0
            last_reset = row[1] if row else datetime.now().strftime("%Y-%m-%d")
            
            # Son 30 gün API çağrıları
            cursor.execute("""
                SELECT COUNT(*) as total_calls,
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_calls,
                       AVG(response_time_ms) as avg_response_time
                FROM api_usage_logs 
                WHERE api_name = 'hugging_face' 
                AND created_at >= datetime('now', '-30 days')
            """)
            
            stats_row = cursor.fetchone()
            total_calls = stats_row[0] if stats_row else 0
            successful_calls = stats_row[1] if stats_row else 0
            avg_response_time = stats_row[2] if stats_row else 0
            
            return {
                "monthly_characters_used": monthly_usage,
                "monthly_limit": self.monthly_limit,
                "characters_remaining": max(0, self.monthly_limit - monthly_usage),
                "usage_percentage": (monthly_usage / self.monthly_limit) * 100,
                "last_reset_date": last_reset,
                "total_calls_30_days": total_calls,
                "successful_calls_30_days": successful_calls,
                "success_rate": (successful_calls / total_calls * 100) if total_calls > 0 else 0,
                "avg_response_time_ms": avg_response_time or 0,
                "api_available": self.api_key is not None,
                "features_enabled": {
                    "summarization": settings.enable_auto_summarization,
                    "sentiment_analysis": settings.enable_sentiment_analysis
                }
            }
        finally:
            conn.close()
    
    def is_available(self) -> bool:
        """Check if the service is available and within limits"""
        if not self.api_key:
            return False
        
        if not settings.enable_ai_features:
            return False
        
        current_usage = self._get_monthly_usage()
        return current_usage < self.monthly_limit