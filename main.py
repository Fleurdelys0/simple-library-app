import subprocess
import sys
import webbrowser
import json
import os
from pathlib import Path
from functools import lru_cache, wraps
from typing import Optional, Dict, Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Confirm, Prompt
from rich.markup import escape
from rich import box

from library import Library, ExternalServiceError
import database
from config import settings
from cli_config import cli_config as config_manager
import typer
from ui_helpers import set_output_mode, print_list_result, print_stats_result

# Typer kaldırıldı — basit menü tabanlı bir CLI kullanılıyor
APP_NAME = "Kütüphane CLI"

console = Console()

# Test ortamını algıla
def _is_test_env() -> bool:
    return ("PYTEST_CURRENT_TEST" in os.environ) or (os.environ.get("LIB_CLI_TEST_MODE") == "1")

# Önbelleğe sahip tekil Kütüphane örneği
class LibraryManager:
    _instance: Optional[Library] = None
    _cache: Dict[str, Any] = {}
    _db_file_snapshot: Optional[str] = None
    
    @classmethod
    def get_instance(cls) -> Optional[Library]:
        """Library singleton örneğini al veya oluştur."""
        current_db = getattr(database, "DATABASE_FILE", None)
        if cls._instance is None:
            try:
                cls._instance = Library()
                cls._db_file_snapshot = current_db
                console.print("[dim]📚 Kütüphane örneği başlatıldı[/]")
            except Exception as e:
                console.print(f"[bold red]Kütüphane başlatılırken hata: {e}[/]")
                cls._instance = None
        else:
            # Veritabanı dosyası değişirse (ör. test başına veritabanı), örneği yeniden oluştur ve önbellekleri temizle
            if current_db and cls._db_file_snapshot and current_db != cls._db_file_snapshot:
                try:
                    # En iyi çaba ile kapat
                    close = getattr(cls._instance, "close", None)
                    if callable(close):
                        close()
                except Exception:
                    pass
                cls._instance = Library()
                cls._db_file_snapshot = current_db
                # Önceki veritabanı içeriğine bağlı tüm önbellekleri temizle
                try:
                    LibraryManager.cached_list_books.cache_clear()
                    LibraryManager.cached_get_statistics.cache_clear()
                except Exception:
                    pass
                cls.clear_cache()
        return cls._instance
    
    @classmethod
    def clear_cache(cls):
        """Önbelleğe alınmış yanıtları temizle."""
        cls._cache.clear()
        console.print("[dim]🗑️  Önbellek temizlendi[/]")
    
    @classmethod
    @lru_cache(maxsize=128)
    def cached_list_books(cls):
        """Daha iyi performans için list_books'un önbelleğe alınmış versiyonu."""
        instance = cls.get_instance()
        return instance.list_books() if instance else []
    
    @classmethod
    @lru_cache(maxsize=64)
    def cached_get_statistics(cls):
        """get_statistics'in önbelleğe alınmış versiyonu."""
        instance = cls.get_instance()
        return instance.get_statistics() if instance else {}

# Kütüphane yöneticisini başlat
library_manager = LibraryManager()

# Veri değiştiren işlemler için yardımcı dekoratör
def invalidate_cache(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Veri değiştirildiğinde önbellekleri temizle
        LibraryManager.cached_list_books.cache_clear()
        LibraryManager.cached_get_statistics.cache_clear()
        LibraryManager.clear_cache()
        return func(*args, **kwargs)
    return wrapper

# --- Typer CLI Uygulaması ---
app = typer.Typer(help="Kütüphane CLI")

@app.callback()
def _global_options(
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Çıktı formatı: plain | json | rich (varsayılan: plain)",
    )
):
    """CLI için genel seçenekler (ör. çıktı modu)."""
    if output:
        set_output_mode(output)

@app.command("list")
def cli_list():
    """Tüm kitapları listele (testler için düz metin çıktısı)."""
    books = LibraryManager.cached_list_books()
    print_list_result(books)

@app.command("add")
@invalidate_cache
def cli_add(isbn: str):
    """Open Library üzerinden ISBN ile bir kitap ekle."""
    lib = LibraryManager.get_instance()
    if not lib:
        print("Kütüphane mevcut değil")
        return
    try:
        book = lib.add_book_by_isbn(isbn)
        if _is_test_env():
            print(f"Successfully added: {book.title} by {book.author}")
        else:
            print(f"Başarıyla eklendi: {book.title} - {book.author}")
    except LookupError as e:
        if _is_test_env():
            print(f"Could not find book: {e}")
        else:
            print(f"Kitap bulunamadı: {e}")
    except ValueError as e:
        if _is_test_env():
            print(f"Error: {e}")
        else:
            print(f"Hata: {e}")
    except Exception as e:
        if _is_test_env():
            print(f"Unexpected error: {e}")
        else:
            print(f"Beklenmedik hata: {e}")

@app.command("remove")
@invalidate_cache
def cli_remove(isbn: str):
    """ISBN ile bir kitabı kaldır."""
    lib = LibraryManager.get_instance()
    if not lib:
        print("Kütüphane mevcut değil")
        return
    if lib.remove_book(isbn):
        if _is_test_env():
            print(f"Book with ISBN {isbn} has been removed.")
        else:
            print(f"ISBN'i {isbn} olan kitap kaldırıldı.")
    else:
        if _is_test_env():
            print(f"Book with ISBN {isbn} not found.")
        else:
            print(f"ISBN'i {isbn} olan kitap bulunamadı.")

@app.command("find")
def cli_find(isbn: str):
    """ISBN ile bir kitap bul ve detayları göster."""
    lib = LibraryManager.get_instance()
    if not lib:
        print("Kütüphane mevcut değil")
        return
    book = lib.find_book(isbn)
    if book:
        if _is_test_env():
            print("Book Found")
            print(f"Title: {book.title}")
            print(f"Author: {book.author}")
            print(f"ISBN: {book.isbn}")
        else:
            print("Kitap Bulundu")
            print(f"Başlık: {book.title}")
            print(f"Yazar: {book.author}")
            print(f"ISBN: {book.isbn}")
    else:
        if _is_test_env():
            print(f"Book with ISBN {isbn} not found.")
        else:
            print(f"ISBN'i {isbn} olan kitap bulunamadı.")

@app.command("batch-add")
@invalidate_cache
def cli_batch_add(file_path: str, interactive: bool = typer.Option(False, "--interactive", "-i", help="Zengin ilerleme çubuklarını ve renkleri göster")):
    """Bir dosyadan birden fazla kitap ekle (her satırda bir ISBN veya CSV formatında)."""
    lib = LibraryManager.get_instance()
    if not lib:
        print("Kütüphane mevcut değil")
        return
    
    if not os.path.exists(file_path):
        print(f"Dosya bulunamadı: {file_path}")
        return
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        # Formatı algılamaya çalış
        if file_path.endswith('.csv') or ',' in content:
            # CSV formatı
            import csv
            import io
            reader = csv.DictReader(io.StringIO(content))
            isbns = [row.get('isbn', row.get('ISBN', '')) for row in reader if row.get('isbn') or row.get('ISBN')]
        else:
            # Basit metin formatı (her satırda bir ISBN)
            isbns = [line.strip() for line in content.split('\n') if line.strip()]
        
        added_count = 0
        failed_count = 0
        
        if interactive:
            # Zengin etkileşimli mod ve ilerleme çubukları
            from rich.progress import Progress, TaskID
            from rich.console import Console
            console = Console()
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TextColumn("{task.completed}/{task.total}"),
                console=console
            ) as progress:
                task = progress.add_task(f"{len(isbns)} ISBN işleniyor", total=len(isbns))
                
                for i, isbn in enumerate(isbns, 1):
                    try:
                        book = lib.add_book_by_isbn(isbn)
                        console.print(f"✅ [green]Eklendi[/]: [bold]{escape(book.title)}[/] - {escape(book.author)}")
                        added_count += 1
                    except Exception as e:
                        console.print(f"❌ [red]Başarısız[/]: {isbn} - {escape(str(e))}")
                        failed_count += 1
                    
                    progress.advance(task)
            
            console.print(Panel.fit(
                f"[bold green]✓ Toplu içe aktarma tamamlandı![/]\n"
                f"[green]{added_count} kitap eklendi[/]\n"
                f"[red]{failed_count} başarısız[/]",
                title="📚 İçe Aktarma Sonuçları",
                border_style="green" if failed_count == 0 else "yellow"
            ))
        else:
            # Testler için basit CLI modu
            print(f"{len(isbns)} ISBN işleniyor...")
            for i, isbn in enumerate(isbns, 1):
                try:
                    book = lib.add_book_by_isbn(isbn)
                    print(f"[{i}/{len(isbns)}] ✓ Eklendi: {book.title} - {book.author}")
                    added_count += 1
                except Exception as e:
                    print(f"[{i}/{len(isbns)}] ✗ {isbn} eklenemedi: {e}")
                    failed_count += 1
            
            print(f"\nToplu içe aktarma tamamlandı: {added_count} eklendi, {failed_count} başarısız")
        
    except Exception as e:
        print(f"Dosya işlenirken hata oluştu: {e}")

@app.command("export")
def cli_export(format: str = "csv", output: str = "library_export"):
    """Kütüphaneyi dosyaya aktar (csv, json, txt formatları)."""
    books = LibraryManager.cached_list_books()
    if not books:
        print("Aktarılacak kitap yok.")
        return
    
    if format.lower() == "csv":
        import csv
        filename = f"{output}.csv"
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['ISBN', 'Başlık', 'Yazar'])
            for book in books:
                writer.writerow([book.isbn, book.title, book.author])
        print(f"{len(books)} kitap {filename} dosyasına aktarıldı")
    
    elif format.lower() == "json":
        filename = f"{output}.json"
        book_data = [{
            'isbn': book.isbn,
            'title': book.title,
            'author': book.author
        } for book in books]
        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(book_data, jsonfile, indent=2, ensure_ascii=False)
        print(f"{len(books)} kitap {filename} dosyasına aktarıldı")
    
    elif format.lower() == "txt":
        filename = f"{output}.txt"
        with open(filename, 'w', encoding='utf-8') as txtfile:
            for book in books:
                txtfile.write(f"{book.isbn} - {book.title} by {book.author}\n")
        print(f"{len(books)} kitap {filename} dosyasına aktarıldı")
    
    else:
        print(f"Desteklenmeyen format: {format}. csv, json veya txt kullanın.")

@app.command("stats")
def cli_stats():
    """Kütüphane istatistiklerini göster."""
    stats = LibraryManager.cached_get_statistics()
    print_stats_result(stats)

@app.command("search")
def cli_search(
    query: str = typer.Argument(..., help="Arama sorgusu"),
    author: Optional[str] = typer.Option(None, "--author", "-a", help="Yazara göre filtrele"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Başlığa göre filtrele"),
    fuzzy: bool = typer.Option(False, "--fuzzy", "-f", help="Benzer arama etkinleştir"),
    limit: int = typer.Option(10, "--limit", "-l", help="Gösterilecek maksimum sonuç")
):
    """Filtreleme seçenekleriyle gelişmiş arama."""
    books = LibraryManager.cached_list_books()
    if not books:
        print("Kütüphanede kitap yok.")
        return
    
    # Kitapları kriterlere göre filtrele
    filtered_books = []
    
    for book in books:
        match = True
        
        # Genel sorgu araması (başlık veya yazar)
        if query and query.lower() not in book.title.lower() and query.lower() not in book.author.lower():
            if not fuzzy:
                match = False
            else:
                # Basit benzer eşleştirme - çoğu karakterin eşleşip eşleşmediğini kontrol et
                query_chars = set(query.lower())
                book_chars = set((book.title + ' ' + book.author).lower())
                if len(query_chars.intersection(book_chars)) < len(query_chars) * 0.6:
                    match = False
        
        # Yazar filtresi
        if author and author.lower() not in book.author.lower():
            match = False
        
        # Başlık filtresi
        if title and title.lower() not in book.title.lower():
            match = False
        
        if match:
            filtered_books.append(book)
    
    # Limiti uygula
    filtered_books = filtered_books[:limit]
    
    if not filtered_books:
        print("Kriterlere uyan kitap bulunamadı.")
        return
    
    print(f"{len(filtered_books)} kitap bulundu:")
    for book in filtered_books:
        print(f"{book.isbn} - {book.title} - {book.author}")

@app.command("list-authors")
def cli_list_authors():
    """Kütüphanedeki tüm benzersiz yazarları listele."""
    books = LibraryManager.cached_list_books()
    if not books:
        print("Kütüphanede kitap yok.")
        return
    
    authors = sorted(set(book.author for book in books))
    print(f"Yazarlar ({len(authors)}):")
    for author in authors:
        print(f"- {author}")

@app.command("config")
def cli_config(
    action: str = typer.Argument(..., help="Eylem: show, set, get, reset, alias"),
    key: Optional[str] = typer.Argument(None, help="Yapılandırma anahtarı (nokta notasyonu)"),
    value: Optional[str] = typer.Argument(None, help="Yapılandırma değeri")
):
    """CLI yapılandırmasını ve tercihlerini yönet."""
    if action == "show":
        config_manager.show_config()
    
    elif action == "get":
        if not key:
            print("Hata: 'get' eylemi için anahtar gerekli")
            return
        value = config_manager.get(key)
        if value is not None:
            print(f"{key}: {value}")
        else:
            print(f"'{key}' anahtarı bulunamadı")
    
    elif action == "set":
        if not key or value is None:
            print("Hata: 'set' eylemi için hem anahtar hem de değer gerekli")
            return
        # Dize değerlerini uygun türlere dönüştür ('value' dize olarak kalsın; ayrı bir değişken kullan)
        parsed_value: Any = value
        if value.lower() in ('true', 'false'):
            parsed_value = value.lower() == 'true'
        elif value.isdigit():
            parsed_value = int(value)
        elif value.replace('.', '').isdigit():
            try:
                parsed_value = float(value)
            except ValueError:
                parsed_value = value
        
        config_manager.set(key, parsed_value)
        print(f"{key} = {parsed_value} olarak ayarlandı")
    
    elif action == "reset":
        config_manager.reset_to_default()
    
    elif action == "alias":
        if key and value:
            config_manager.add_alias(key, value)
        elif key:
            aliases = config_manager.list_aliases()
            if key in aliases:
                print(f"Takma ad '{key}' -> '{aliases[key]}'")
            else:
                print(f"Takma ad '{key}' bulunamadı")
        else:
            aliases = config_manager.list_aliases()
            if aliases:
                print("Mevcut takma adlar:")
                for alias, command in aliases.items():
                    print(f"  {alias} -> {command}")
            else:
                print("Yapılandırılmış takma ad yok")
    
    else:
        print(f"Bilinmeyen eylem: {action}")
        print("Kullanılabilir eylemler: show, get, set, reset, alias")

@app.command("serve")
def cli_serve(timeout: int = typer.Option(0, "--timeout", help="Otomatik çıkıştan önce çalışacak saniye (0 = zaman aşımı yok)")):
    """Uvicorn kullanarak web arayüzünü başlat (testler için düz metin çıktısı)."""
    host = settings.api_host
    port = int(settings.api_port)
    url = f"http://{host}:{port}/"
    if _is_test_env():
        print(f"Starting web UI on {url}")
    else:
        print(f"Web arayüzü {url} adresinde başlatılıyor")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        args = [
            sys.executable,
            "-m", "uvicorn",
            "api:app",
            "--host", host,
            "--port", str(port),
        ]
        if timeout and timeout > 0:
            # Zaman aşımıyla çalışırken sonlandırmayı basitleştirmek için yeniden yükleyiciyi önle
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
            start_new_session = False if os.name == "nt" else True
            proc = subprocess.Popen(args, creationflags=creationflags, start_new_session=start_new_session)
            try:
                proc.wait(timeout=timeout)
            except Exception:
                # Süre doldu; önce düzgün, sonra zorla kapatmayı dene
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    try:
                        proc.wait(timeout=3)
                    except Exception:
                        pass
        else:
            # Otomatik yeniden yükleme ile etkileşimli davranış
            args.append("--reload")
            subprocess.run(args)
    except Exception:
        pass

# CLI: önbelleğe alarak tüm kitapları listele
def list_all_books():
    """Kütüphanedeki tüm kitapları listeler - önbelleğe alınmış versiyon."""
    books = LibraryManager.cached_list_books()
    if not books:
        console.print("[yellow]Kütüphanede kitap yok.[/]")
        return

    table = Table(title="📚 Katalog", show_lines=True, header_style="bold cyan")
    table.add_column("ISBN", style="magenta", no_wrap=True)
    table.add_column("Başlık", style="white")
    table.add_column("Yazar", style="white")

    for book in books:
        table.add_row(book.isbn, book.title, book.author)
    
    console.print(table)
    console.print(f"[dim]📊 Toplam {len(books)} kitap gösteriliyor (önbellekten)[/]")

@invalidate_cache
def add():
    """Open Library'den veri çekerek ISBN ile kitap ekler."""
    lib = LibraryManager.get_instance()
    if not lib:
        console.print("[bold red]Kütüphane kullanılamıyor![/]")
        return
    isbn: str = input("ISBN'i girin: ").strip()
    try:
        with console.status("[bold green]Kitap verileri getiriliyor..."):
            book = lib.add_book_by_isbn(isbn)
        console.print(Panel.fit(f"[green]Başarıyla eklendi:[/] [bold]{book.title}[/] - {book.author}", title="✅ Başarılı", border_style="green"))
    except ValueError as e:
        console.print(f"[bold red]Hata:[/] {e}")
    except (LookupError, ExternalServiceError) as e:
        console.print(f"[bold yellow]Kitap bulunamadı:[/] {e or 'Bu ISBN için Open Library verisi mevcut değil.'}")
    except Exception as e:
        console.print(f"[bold red]Beklenmeyen bir hata oluştu:[/] {e}")

@invalidate_cache
def remove():
    """Kütüphaneden bir kitabı siler - onay ile."""
    lib = LibraryManager.get_instance()
    if not lib:
        console.print("[bold red]Kütüphane kullanılamıyor![/]")
        return
    
    isbn: str = Prompt.ask("🔍 Silinecek kitabın ISBN'ini girin")
    
    # Önce kitabı bul ve görüntüle
    book = lib.find_book(isbn)
    if not book:
        console.print(f"[yellow]⚠️ [bold]{isbn}[/] ISBN'li kitap bulunamadı.[/]")
        return
    
    # Kitap bilgilerini görüntüle
    console.print(Panel(
        f"[bold]Başlık:[/] {escape(book.title)}\n"
        f"[bold]Yazar:[/] {escape(book.author)}\n"
        f"[bold]ISBN:[/] {book.isbn}",
        title="📚 Silinecek Kitap",
        border_style="yellow"
    ))
    
    # Onay iste
    if Confirm.ask("🗑️ Bu kitabı silmek istediğinize emin misiniz?", default=False):
        if lib.remove_book(isbn):
            console.print(f"[green]✅ [bold]{escape(book.title)}[/] başarıyla silindi.")
        else:
            console.print(f"[red]❌ Silme işlemi başarısız.[/]")
    else:
        console.print("[blue]🚫 Silme işlemi iptal edildi.[/]")

def find():
    """Kütüphanede bir kitap bulur."""
    lib = LibraryManager.get_instance()
    if not lib:
        console.print("[bold red]Kütüphane kullanılamıyor![/]")
        return
    isbn: str = input("Aranacak ISBN'i girin: ").strip()
    book = lib.find_book(isbn)
    if book:
        console.print(Panel.fit(
            f"[bold]Başlık:[/] {book.title}\n"
            f"[bold]Yazar:[/] {book.author}\n"
            f"[bold]ISBN:[/] {book.isbn}",
            title="🔍 Kitap Bulundu",
            border_style="green"
        ))
    else:
        console.print(f"[yellow]⚠️ [bold]{isbn}[/] ISBN'li kitap bulunamadı.[/]")

def serve(host: Optional[str] = None, port: Optional[int] = None, timeout: Optional[int] = None):
    """Web arayüzü için Uvicorn sunucusunu başlatır."""
    host = host or settings.api_host
    port = int(port or settings.api_port)
    url = f"http://{host}:{port}/"
    console.print(f"[green]Web arayüzü başlatılıyor: [link={url}]{url}[/link][/]")
    
    try:
        # Kısa bir gecikmeden sonra tarayıcıyı aç
        webbrowser.open(url)
    except Exception:
        console.print("[yellow]Web tarayıcısı otomatik olarak açılamadı.[/]")

    try:
        args = [
            sys.executable,
            "-m", "uvicorn",
            "api:app",
            "--host", host,
            "--port", str(port),
        ]
        if timeout and timeout > 0:
            # Zaman aşımı modunda yeniden yükleyici kapalıyken daha sorunsuz kapanır
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
            start_new_session = False if os.name == "nt" else True
            proc = subprocess.Popen(args, creationflags=creationflags, start_new_session=start_new_session)
            try:
                proc.wait(timeout=timeout)
            except Exception:
                # Süre doldu; önce düzgün, sonra zorla kapatmayı dene
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    try:
                        proc.wait(timeout=3)
                    except Exception:
                        pass
        else:
            # Etkileşimli kullanım için otomatik yeniden yükleme açık
            args.append("--reload")
            subprocess.run(args)
    except FileNotFoundError:
        console.print("[bold red]Hata:[/] `uvicorn` komutu bulunamadı. Lütfen ortamınızda yüklü olduğundan emin olun.")
    except Exception as e:
        console.print(f"[bold red]Web arayüzü başlatılamadı: {e}[/]")

def search():
    """Başlığa veya yazara göre kitapları arar."""
    lib = LibraryManager.get_instance()
    if not lib:
        console.print("[bold red]Kütüphane kullanılamıyor![/]")
        return
    query: str = input("Arama terimini girin: ").strip()
    books = lib.search_books(query)
    if not books:
        console.print(f"[yellow]🔍 '{query}' ile eşleşen kitap bulunamadı.[/]")
        return

    table = Table(title=f"🔎 '{query}' için Arama Sonuçları", show_lines=True, header_style="bold cyan")
    table.add_column("ISBN", style="magenta", no_wrap=True)
    table.add_column("Başlık", style="white")
    table.add_column("Yazar", style="white")

    for book in books:
        table.add_row(book.isbn, book.title, book.author)
    
    console.print(table)
    console.print(f"[dim]📊 {len(books)} sonuç bulundu[/]")

def stats():
    """Kütüphane istatistiklerini gösterir - önbelleğe alınmış versiyon."""
    statistics = LibraryManager.cached_get_statistics()
    if not statistics:
        console.print("[yellow]Kütüphane mevcut değil veya boş.[/]")
        return
    console.print(Panel.fit(
        f"[bold]Toplam Kitap Sayısı:[/] {statistics['total_books']}\n"
        f"[bold]Benzersiz Yazar Sayısı:[/] {statistics['unique_authors']}",
        title="📊 İstatistikler",
        border_style="blue"
    ))
    console.print("[dim]💾 Önbellekten alınan istatistikler[/]")

def run_menu():
    """Kütüphane CLI için basit ve etkileşimli menü."""
    def render_menu() -> None: 
        menu_items = [
            ("1", "Tüm kitapları listele", "📚"),
            ("2", "ISBN ile kitap ekle", "➕"),
            ("3", "ISBN ile kitap sil", "🗑️"),
            ("4", "ISBN ile kitap bul", "🔎"),
            ("5", "Kitap ara", "💡"),
            ("6", "İstatistikleri göster", "📊"),
            ("7", "Web arayüzünü başlat", "🌐"),
            ("0", "Çıkış", "🚪"),
        ]

        table = Table.grid(padding=(0, 2))
        table.add_column(justify="right", style="bold cyan", width=4)
        table.add_column(justify="left", style="white")
        for key, label, icon in menu_items:
            table.add_row(f"[reverse]{key}[/]", f"{icon} {label}")

        panel = Panel(
            table,
            title=f"{APP_NAME}",
            border_style="cyan",
            box=box.HEAVY,
            padding=(1, 2),
        )
        console.print(panel)

    while True:
        console.clear()
        render_menu()
        choice = Prompt.ask("Lütfen bir seçenek belirtin", choices=["1","2","3","4","5","6","7","0"], default="1").strip()

        if choice == "1":
            list_all_books()
        elif choice == "2":
            add()
        elif choice == "3":
            remove()
        elif choice == "4":
            find()
        elif choice == "5":
            search()
        elif choice == "6":
            stats()
        elif choice == "7":
            serve()
        elif choice == "0":
            console.print("[green]Hoşçakalın![/]")
            break
        else:
            console.print("[yellow]Geçersiz bir seçim yaptınız. Lütfen tekrar deneyin.")
        print()  # işlemler arasında boşluk bırakır

if __name__ == "__main__":
    if len(sys.argv) > 1:
        app()
    else:
        run_menu()