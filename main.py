import subprocess
import sys
import webbrowser
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from library import Library, ExternalServiceError
from config import settings

# Typer removed — using a simple menu-based CLI
APP_NAME = "Kütüphane CLI"

console = Console()

# Initialize the library instance once
try:
    library = Library()
except Exception as e:
    console.print(f"[bold red]Kütüphane başlatılırken hata: {e}[/]")
    # Kütüphane başlatılamasa bile serve komutu çalışabilsin
    library = None

# CLI: list all books
def list_all_books():
    """Kütüphanedeki tüm kitapları listeler."""
    if not library:
        return
    books = library.list_books()
    if not books:
        console.print("[yellow]Kütüphanede kitap yok.[/]")
        return

    table = Table(title="Katalog", show_lines=True, header_style="bold cyan")
    table.add_column("ISBN", style="magenta", no_wrap=True)
    table.add_column("Başlık", style="white")
    table.add_column("Yazar", style="white")

    for book in books:
        table.add_row(book.isbn, book.title, book.author)
    
    console.print(table)

def add():
    """Open Library'den verileri çekip ISBN ile kitap ekler."""
    if not library:
        return
    isbn: str = input("ISBN'i girin: ").strip()
    try:
        with console.status("[bold green]Kitap verisi getiriliyor..."):
            book = library.add_book_by_isbn(isbn)
        console.print(Panel.fit(f"[green]Başarıyla eklendi:[/] [bold]{book.title}[/] - {book.author}", title="Başarılı", border_style="green"))
    except ValueError as e:
        console.print(f"[bold red]Hata:[/] {e}")
    except (LookupError, ExternalServiceError) as e:
        console.print(f"[bold yellow]Kitap bulunamadı:[/] {e or 'Bu ISBN için Open Library verisi bulunamadı.'}")
    except Exception as e:
        console.print(f"[bold red]Beklenmeyen bir hata oluştu:[/] {e}")

def remove():
    """Kütüphaneden bir kitabı siler."""
    if not library:
        return
    isbn: str = input("Silinecek ISBN'i girin: ").strip()
    if library.remove_book(isbn):
        console.print(f"[green][bold]{isbn}[/] ISBN'li kitap silindi.[/]")
    else:
        console.print(f"[yellow][bold]{isbn}[/] ISBN'li kitap bulunamadı.[/]")

def find():
    """Kütüphanede bir kitabı bulur."""
    if not library:
        return
    isbn: str = input("Bulunacak ISBN'i girin: ").strip()
    book = library.find_book(isbn)
    if book:
        console.print(Panel.fit(
            f"[bold]Başlık:[/] {book.title}\n"
            f"[bold]Yazar:[/] {book.author}\n"
            f"[bold]ISBN:[/] {book.isbn}",
            title="Kitap Bulundu",
            border_style="green"
        ))
    else:
        console.print(f"[yellow][bold]{isbn}[/] ISBN'li kitap bulunamadı.[/]")

def serve(host: Optional[str] = None, port: Optional[int] = None):
    """Web arayüzü için Uvicorn sunucusunu başlatır."""
    host = host or settings.api_host
    port = int(port or settings.api_port)
    url = f"http://{host}:{port}/"
    console.print(f"[green]Web arayüzü başlatılıyor: [link={url}]{url}[/link][/]")
    
    try:
        # Open browser after a short delay
        webbrowser.open(url)
    except Exception:
        console.print("[yellow]Web tarayıcısı otomatik açılamadı.[/]")

    try:
        subprocess.run([
            sys.executable,
            "-m", "uvicorn",
            "api:app",
            "--host", host,
            "--port", str(port),
            "--reload"
        ])
    except FileNotFoundError:
        console.print("[bold red]Hata:[/] `uvicorn` komutu bulunamadı. Lütfen ortamınızda kurulu olduğundan emin olun.[/]")
    except Exception as e:
        console.print(f"[bold red]Web arayüzü başlatılamadı: {e}[/]")

def search():
    """Başlığa veya yazara göre kitap arar."""
    if not library:
        return
    query: str = input("Arama terimini girin: ").strip()
    books = library.search_books(query)
    if not books:
        console.print(f"[yellow]'{query}' ile eşleşen kitap bulunamadı.[/]")
        return

    table = Table(title=f"'{query}' için Arama Sonuçları", show_lines=True, header_style="bold cyan")
    table.add_column("ISBN", style="magenta", no_wrap=True)
    table.add_column("Başlık", style="white")
    table.add_column("Yazar", style="white")

    for book in books:
        table.add_row(book.isbn, book.title, book.author)
    
    console.print(table)

def stats():
    """Kütüphane istatistiklerini gösterir."""
    if not library:
        return
    statistics = library.get_statistics()
    console.print(Panel.fit(
        f"[bold]Toplam Kitap:[/] {statistics['total_books']}\n"
        f"[bold]Farklı Yazarlar:[/] {statistics['unique_authors']}",
        title="İstatistikler",
        border_style="blue"
    ))

def run_menu():
    """Kütüphane CLI için basit etkileşimli menü."""
    while True:
        console.print(Panel.fit(
            "\n".join([
                "1) Tüm kitapları listele",
                "2) ISBN ile kitap ekle",
                "3) ISBN ile kitap sil",
                "4) ISBN ile kitap bul",
                "5) Kitap ara",
                "6) İstatistikleri göster",
                "7) Web arayüzünü başlat",
                "0) Çıkış",
            ]),
            title=f"{APP_NAME}", border_style="cyan"
        ))
        choice = input("Bir seçenek seçin: ").strip()

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
            console.print("[green]Güle güle![/]")
            break
        else:
            console.print("[yellow]Geçersiz seçim. Lütfen tekrar deneyin.[/]")
        print()  # blank line between operations

if __name__ == "__main__":
    run_menu()

