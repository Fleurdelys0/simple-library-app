import os
import json
from typing import List, Any, Dict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Environment variable to control CLI output mode
# İzin verilen değerler: 'plain' (default), 'json', 'rich'
OUTPUT_MODE_ENV = "LIB_CLI_OUTPUT"

_console = Console()

def set_output_mode(mode: str) -> None:
    mode = (mode or "").lower().strip()
    if mode in {"plain", "json", "rich"}:
        os.environ[OUTPUT_MODE_ENV] = mode
    else:
        # Geçersiz değerleri yoksay; mevcut varsayılanı koru
        pass

def get_output_mode() -> str:
    return os.environ.get(OUTPUT_MODE_ENV, "plain").lower()

def print_list_result(books: List[Any]) -> None:
    """Kitap listesini mevcut çıktı moduna göre yazdır.
    - plain: 'ISBN - Title by Author' satırları, veya 'No books in library.'
    - json: JSON dizisi olarak isbn, title, author
    - rich: Rich tablosu
    """
    mode = get_output_mode()

    if not books:
        # Match tests' expected plain message regardless of mode for empty state
        # to keep behavior predictable; can be adjusted if desired.
        print("No books in library.")
        return

    if mode == "json":
        payload = [
            {"isbn": getattr(b, "isbn", ""), "title": getattr(b, "title", ""), "author": getattr(b, "author", "")}
            for b in books
        ]
        print(json.dumps(payload, ensure_ascii=False))
    elif mode == "rich":
        table = Table(title="📚 Books", show_lines=True, header_style="bold cyan")
        table.add_column("ISBN", style="magenta", no_wrap=True)
        table.add_column("Title", style="white")
        table.add_column("Author", style="white")
        for b in books:
            table.add_row(getattr(b, "isbn", ""), getattr(b, "title", ""), getattr(b, "author", ""))
        _console.print(table)
    else:
        for b in books:
            print(f"{getattr(b, 'isbn', '')} - {getattr(b, 'title', '')} by {getattr(b, 'author', '')}")

def print_stats_result(stats: Dict[str, Any]) -> None:
    """Statistikleri mevcut çıktı moduna göre yazdır.
    - plain: iki satır var olan mevcut çıktıyı eşle
    - json: JSON nesnesi
    - rich: Ana metriklerle Panel
    """
    mode = get_output_mode()

    if not stats:
        print("No statistics available.")
        return

    total = stats.get("total_books", 0)
    authors = stats.get("unique_authors", 0)

    if mode == "json":
        print(json.dumps({"total_books": total, "unique_authors": authors}, ensure_ascii=False))
    elif mode == "rich":
        content = f"[bold]Total Books:[/] {total}\n[bold]Unique Authors:[/] {authors}"
        _console.print(Panel.fit(content, title="📊 Stats", border_style="blue"))
    else:
        print(f"Total Books: {total}")
        print(f"Unique Authors: {authors}")
