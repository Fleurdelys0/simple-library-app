import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from urllib.parse import quote

import httpx

from config.config import settings
from src.services.http_client import get_http_client
from src.database import get_db_connection


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class GoogleBookData:
    """Data structure for Google Books API response"""
    isbn: str
    title: str
    authors: List[str] = field(default_factory=list)
    description: Optional[str] = None
    page_count: Optional[int] = None
    categories: List[str] = field(default_factory=list)
    published_date: Optional[str] = None
    publisher: Optional[str] = None
    language: Optional[str] = None
    average_rating: Optional[float] = None
    ratings_count: Optional[int] = None
    thumbnail_url: Optional[str] = None
    preview_link: Optional[str] = None
    info_link: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "isbn": self.isbn,
            "title": self.title,
            "authors": self.authors,
            "description": self.description,
            "page_count": self.page_count,
            "categories": self.categories,
            "published_date": self.published_date,
            "publisher": self.publisher,
            "language": self.language,
            "average_rating": self.average_rating,
            "ratings_count": self.ratings_count,
            "thumbnail_url": self.thumbnail_url,
            "preview_link": self.preview_link,
            "info_link": self.info_link
        }


class GoogleBooksAPIError(Exception):
    """Custom exception for Google Books API errors"""
    pass


class RateLimitExceeded(GoogleBooksAPIError):
    """Exception raised when rate limit is exceeded"""
    pass


class GoogleBooksService:
    """Service for interacting with Google Books API"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.google_books_api_key
        self.base_url = "https://www.googleapis.com/books/v1"
        self.daily_limit = settings.google_books_daily_limit
        self.timeout = settings.google_books_timeout
        
        # Initialize usage tracking
        self._init_usage_tracking()
    
    def _init_usage_tracking(self) -> None:
        """Initialize usage tracking in database"""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Create API usage logs table if not exists
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
            
            # Create or update usage stats table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_usage_stats (
                    id INTEGER PRIMARY KEY,
                    google_books_daily_calls INTEGER DEFAULT 0,
                    hugging_face_monthly_chars INTEGER DEFAULT 0,
                    last_reset_date TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert initial record if not exists
            cursor.execute("SELECT COUNT(*) FROM api_usage_stats")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO api_usage_stats (google_books_daily_calls, hugging_face_monthly_chars, last_reset_date)
                    VALUES (0, 0, ?)
                """, (datetime.now().strftime("%Y-%m-%d"),))
            
            # Add google_books_daily_calls column if it doesn't exist
            cursor.execute("PRAGMA table_info(api_usage_stats)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'google_books_daily_calls' not in columns:
                cursor.execute("ALTER TABLE api_usage_stats ADD COLUMN google_books_daily_calls INTEGER DEFAULT 0")
            
            conn.commit()
        finally:
            conn.close()
    
    def _check_rate_limit(self) -> bool:
        """Check if we're within daily rate limit"""
        current_usage = self._get_daily_usage()
        
        if current_usage >= self.daily_limit:
            logger.warning(f"Daily rate limit exceeded: {current_usage}/{self.daily_limit}")
            return False
        
        return True
    
    def _get_daily_usage(self) -> int:
        """Get current daily API usage"""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT google_books_daily_calls, last_reset_date FROM api_usage_stats WHERE id = 1")
            row = cursor.fetchone()
            
            if not row:
                return 0
            
            usage, last_reset = row
            
            # Check if we need to reset daily counter
            last_reset_date = datetime.strptime(last_reset, "%Y-%m-%d")
            current_date = datetime.now()
            
            # Reset if it's a new day
            if current_date.date() > last_reset_date.date():
                cursor.execute("""
                    UPDATE api_usage_stats 
                    SET google_books_daily_calls = 0, 
                        last_reset_date = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, (current_date.strftime("%Y-%m-%d"),))
                conn.commit()
                return 0
            
            return usage or 0
        finally:
            conn.close()
    
    def _log_api_usage(self, endpoint: str, success: bool, response_time_ms: int = 0) -> None:
        """Log API usage to database"""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Log the API call
            cursor.execute("""
                INSERT INTO api_usage_logs (api_name, endpoint, success, response_time_ms, characters_used)
                VALUES (?, ?, ?, ?, ?)
            """, ("google_books", endpoint, success, response_time_ms, 0))
            
            # Update daily usage if successful
            if success:
                cursor.execute("""
                    UPDATE api_usage_stats 
                    SET google_books_daily_calls = google_books_daily_calls + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """)
            
            conn.commit()
            logger.info(f"Google Books API usage logged: endpoint={endpoint}, success={success}")
        except Exception as e:
            logger.error(f"Failed to log API usage: {e}")
        finally:
            conn.close()
    
    async def _make_api_request(self, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Make an API request to Google Books"""
        url = f"{self.base_url}/{endpoint}"
        
        # Add API key if available
        if self.api_key:
            params["key"] = self.api_key
        
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                
                response_time_ms = int((time.time() - start_time) * 1000)
                
                if response.status_code == 200:
                    self._log_api_usage(endpoint, True, response_time_ms)
                    return response.json()
                elif response.status_code == 429:
                    logger.warning("Rate limit exceeded for Google Books API")
                    self._log_api_usage(endpoint, False, response_time_ms)
                    raise RateLimitExceeded("Rate limit exceeded")
                else:
                    logger.error(f"API request failed: {response.status_code} - {response.text}")
                    self._log_api_usage(endpoint, False, response_time_ms)
                    return None
                    
        except httpx.TimeoutException:
            logger.error(f"API request timed out after {self.timeout}s")
            self._log_api_usage(endpoint, False)
            return None
        except Exception as e:
            logger.error(f"API request failed: {e}")
            self._log_api_usage(endpoint, False)
            return None
    
    def _parse_volume_info(self, volume_data: Dict[str, Any], isbn: str) -> Optional[GoogleBookData]:
        """Parse volume info from Google Books API response"""
        try:
            volume_info = volume_data.get("volumeInfo", {})
            
            # Extract basic info
            title = volume_info.get("title", "")
            authors = volume_info.get("authors", [])
            description = volume_info.get("description", "")
            
            # Extract additional details
            page_count = volume_info.get("pageCount")
            categories = volume_info.get("categories", [])
            published_date = volume_info.get("publishedDate")
            publisher = volume_info.get("publisher")
            language = volume_info.get("language", "en")
            
            # Extract ratings
            average_rating = volume_info.get("averageRating")
            ratings_count = volume_info.get("ratingsCount")
            
            # Extract links and images
            image_links = volume_data.get("volumeInfo", {}).get("imageLinks", {})
            thumbnail_url = None
            # Prefer highest resolution available
            for key in [
                "extraLarge",
                "large",
                "medium",
                "small",
                "thumbnail",
                "smallThumbnail",
            ]:
                url = image_links.get(key)
                if url:
                    thumbnail_url = url
                    break
            
            access_info = volume_data.get("accessInfo", {})
            preview_link = access_info.get("webReaderLink")
            info_link = volume_data.get("volumeInfo", {}).get("infoLink")
            
            return GoogleBookData(
                isbn=isbn,
                title=title,
                authors=authors,
                description=description,
                page_count=page_count,
                categories=categories,
                published_date=published_date,
                publisher=publisher,
                language=language,
                average_rating=average_rating,
                ratings_count=ratings_count,
                thumbnail_url=thumbnail_url,
                preview_link=preview_link,
                info_link=info_link
            )
            
        except Exception as e:
            logger.error(f"Failed to parse volume info: {e}")
            return None
    
    async def fetch_book_by_isbn(self, isbn: str) -> Optional[GoogleBookData]:
        """
        Fetch book data by ISBN from Google Books API
        
        Args:
            isbn: Book ISBN (10 or 13 digits)
            
        Returns:
            GoogleBookData object or None if not found
        """
        if not isbn or not isbn.strip():
            logger.warning("Empty ISBN provided")
            return None
        
        # Check rate limit
        if not self._check_rate_limit():
            raise RateLimitExceeded("Daily rate limit exceeded")
        
        # Clean ISBN
        clean_isbn = ''.join(c for c in isbn if c.isalnum())
        
        # Search by ISBN
        params = {
            "q": f"isbn:{clean_isbn}",
            "maxResults": 1
        }
        
        try:
            response = await self._make_api_request("volumes", params)
            
            if response and response.get("totalItems", 0) > 0:
                items = response.get("items", [])
                if items:
                    volume_data = items[0]
                    book_data = self._parse_volume_info(volume_data, clean_isbn)
                    
                    if book_data:
                        logger.info(f"Book found via Google Books: {book_data.title} by {', '.join(book_data.authors)}")
                        return book_data
            
            logger.info(f"Book not found in Google Books: ISBN {clean_isbn}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to fetch book by ISBN {clean_isbn}: {e}")
            return None
    
    async def search_books(self, query: str, max_results: int = 10) -> List[GoogleBookData]:
        """
        Search for books using a text query
        
        Args:
            query: Search query (title, author, etc.)
            max_results: Maximum number of results to return
            
        Returns:
            List of GoogleBookData objects
        """
        if not query or not query.strip():
            logger.warning("Empty search query provided")
            return []
        
        # Check rate limit
        if not self._check_rate_limit():
            raise RateLimitExceeded("Daily rate limit exceeded")
        
        params = {
            "q": quote(query.strip()),
            "maxResults": min(max_results, 40)  # Google Books API limit
        }
        
        try:
            response = await self._make_api_request("volumes", params)
            
            if response and response.get("totalItems", 0) > 0:
                items = response.get("items", [])
                books = []
                
                for item in items:
                    # Try to extract ISBN from identifiers
                    volume_info = item.get("volumeInfo", {})
                    identifiers = volume_info.get("industryIdentifiers", [])
                    
                    isbn = None
                    for identifier in identifiers:
                        if identifier.get("type") in ["ISBN_13", "ISBN_10"]:
                            isbn = identifier.get("identifier")
                            break
                    
                    if not isbn:
                        # Use Google Books ID as fallback
                        isbn = item.get("id", "")
                    
                    if isbn:
                        book_data = self._parse_volume_info(item, isbn)
                        if book_data:
                            books.append(book_data)
                
                logger.info(f"Found {len(books)} books for query: {query}")
                return books
            
            logger.info(f"No books found for query: {query}")
            return []
            
        except Exception as e:
            logger.error(f"Failed to search books with query '{query}': {e}")
            return []
    
    async def get_similar_books(self, isbn: str, max_results: int = 5) -> List[GoogleBookData]:
        """
        Get books similar to the one with given ISBN
        
        Args:
            isbn: ISBN of the reference book
            max_results: Maximum number of similar books to return
            
        Returns:
            List of GoogleBookData objects
        """
        # First get the reference book
        reference_book = await self.fetch_book_by_isbn(isbn)
        
        if not reference_book:
            logger.warning(f"Reference book not found for ISBN: {isbn}")
            return []
        
        # Search for similar books using categories and authors
        search_queries = []
        
        # Search by categories
        if reference_book.categories:
            for category in reference_book.categories[:2]:  # Use first 2 categories
                search_queries.append(f"subject:{category}")
        
        # Search by authors
        if reference_book.authors:
            for author in reference_book.authors[:1]:  # Use first author
                search_queries.append(f"inauthor:{author}")
        
        # If no specific queries, use title keywords
        if not search_queries and reference_book.title:
            title_words = reference_book.title.split()[:3]  # First 3 words
            search_queries.append(" ".join(title_words))
        
        similar_books = []
        seen_isbns = {isbn}  # Exclude the reference book
        
        for query in search_queries:
            if len(similar_books) >= max_results:
                break
                
            try:
                books = await self.search_books(query, max_results - len(similar_books))
                
                for book in books:
                    if book.isbn not in seen_isbns and len(similar_books) < max_results:
                        similar_books.append(book)
                        seen_isbns.add(book.isbn)
                        
            except Exception as e:
                logger.error(f"Failed to search similar books with query '{query}': {e}")
                continue
        
        logger.info(f"Found {len(similar_books)} similar books for ISBN: {isbn}")
        return similar_books
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get current API usage statistics"""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Get daily usage
            cursor.execute("SELECT google_books_daily_calls, last_reset_date FROM api_usage_stats WHERE id = 1")
            row = cursor.fetchone()
            
            daily_usage = row[0] if row else 0
            last_reset = row[1] if row else datetime.now().strftime("%Y-%m-%d")
            
            # Get recent API calls
            cursor.execute("""
                SELECT COUNT(*) as total_calls,
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_calls,
                       AVG(response_time_ms) as avg_response_time
                FROM api_usage_logs 
                WHERE api_name = 'google_books' 
                AND created_at >= datetime('now', '-30 days')
            """)
            
            stats_row = cursor.fetchone()
            total_calls = stats_row[0] if stats_row else 0
            successful_calls = stats_row[1] if stats_row else 0
            avg_response_time = stats_row[2] if stats_row else 0
            
            return {
                "daily_calls_used": daily_usage,
                "daily_limit": self.daily_limit,
                "calls_remaining": max(0, self.daily_limit - daily_usage),
                "usage_percentage": (daily_usage / self.daily_limit) * 100,
                "last_reset_date": last_reset,
                "total_calls_30_days": total_calls,
                "successful_calls_30_days": successful_calls,
                "success_rate": (successful_calls / total_calls * 100) if total_calls > 0 else 0,
                "avg_response_time_ms": avg_response_time or 0,
                "api_available": True,  # Google Books doesn't require API key
                "api_key_configured": self.api_key is not None,
                "features_enabled": {
                    "book_search": settings.enable_google_books,
                    "enhanced_metadata": settings.enable_google_books
                }
            }
        finally:
            conn.close()
    
    def is_available(self) -> bool:
        """Check if the service is available and within limits"""
        if not settings.enable_google_books:
            return False
        
        current_usage = self._get_daily_usage()
        return current_usage < self.daily_limit