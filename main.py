import subprocess
import sys
import webbrowser
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from library import Library, ExternalServiceError
from config import settings

# Create a Typer app
app = typer.Typer(
    name="library-cli",
    help="A CLI for managing your book library.",
    add_completion=False,
)

console = Console()

# Initialize the library instance once
try:
    library = Library()
except Exception as e:
    console.print(f"[bold red]Error initializing library: {e}[/]")
    # Allow serve command to run even if library fails to initialize
    library = None

@app.command(
    name="list",
    help="List all books in the library."
)
def list_all_books():
    """Lists all books currently in the library."""
    if not library:
        return
    books = library.list_books()
    if not books:
        console.print("[yellow]No books in library.[/]")
        return

    table = Table(title="Library Catalog", show_lines=True, header_style="bold cyan")
    table.add_column("ISBN", style="magenta", no_wrap=True)
    table.add_column("Title", style="white")
    table.add_column("Author", style="white")

    for book in books:
        table.add_row(book.isbn, book.title, book.author)
    
    console.print(table)

@app.command(help="Add a new book to the library using its ISBN.")
def add(isbn: str = typer.Argument(..., help="The 10 or 13-digit ISBN of the book.")):
    """Adds a book by its ISBN after fetching data from Open Library."""
    if not library:
        return
    try:
        with console.status("[bold green]Fetching book data..."):
            book = library.add_book_by_isbn(isbn)
        console.print(Panel.fit(f"[green]Successfully added:[/] [bold]{book.title}[/] by {book.author}", title="Success", border_style="green"))
    except ValueError as e:
        console.print(f"[bold red]Error:[/] {e}")
    except (LookupError, ExternalServiceError) as e:
        console.print(f"[bold yellow]Could not find book:[/] {e or 'No data from Open Library for this ISBN.'}")
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred:[/] {e}")

@app.command(help="Remove a book from the library by its ISBN.")
def remove(isbn: str = typer.Argument(..., help="The ISBN of the book to remove.")):
    """Removes a book from the library.
    """
    if not library:
        return
    if library.remove_book(isbn):
        console.print(f"[green]Book with ISBN [bold]{isbn}[/] has been removed.[/]")
    else:
        console.print(f"[yellow]Book with ISBN [bold]{isbn}[/] not found.[/]")

@app.command(help="Find and display details for a single book by its ISBN.")
def find(isbn: str = typer.Argument(..., help="The ISBN of the book to find.")):
    """Finds a book in the library.
    """
    if not library:
        return
    book = library.find_book(isbn)
    if book:
        console.print(Panel.fit(
            f"[bold]Title:[/] {book.title}\n"
            f"[bold]Author:[/] {book.author}\n"
            f"[bold]ISBN:[/] {book.isbn}",
            title="Book Found",
            border_style="green"
        ))
    else:
        console.print(f"[yellow]Book with ISBN [bold]{isbn}[/] not found.[/]")

@app.command(help="Start the web user interface.")
def serve(host: str = typer.Option(settings.api_host, "--host", "-h", help="Host to bind the server to."), 
          port: int = typer.Option(settings.api_port, "--port", "-p", help="Port to bind the server to.")):
    """Starts the Uvicorn server for the web UI.
    """
    url = f"http://{host}:{port}/"
    console.print(f"[green]Starting web UI on [link={url}]{url}[/link][/]")
    
    try:
        # Open browser after a short delay
        webbrowser.open(url)
    except Exception:
        console.print("[yellow]Could not automatically open web browser.[/]")

    try:
        subprocess.run([sys.executable, "-m", "uvicorn", "api:app", "--host", host, "--port", str(port)])
    except FileNotFoundError:
        console.print("[bold red]Error:[/] `uvicorn` command not found. Please ensure it is installed in your environment.[/]")
    except Exception as e:
        console.print(f"[bold red]Failed to start web UI: {e}[/]")

@app.command(help="Search for books by title or author.")
def search(query: str = typer.Argument(..., help="The search query.")):
    """Searches for books by title or author."""
    if not library:
        return
    books = library.search_books(query)
    if not books:
        console.print(f"[yellow]No books found matching '{query}'.[/]")
        return

    table = Table(title=f"Search Results for '{query}'", show_lines=True, header_style="bold cyan")
    table.add_column("ISBN", style="magenta", no_wrap=True)
    table.add_column("Title", style="white")
    table.add_column("Author", style="white")

    for book in books:
        table.add_row(book.isbn, book.title, book.author)
    
    console.print(table)

@app.command(help="Display library statistics.")
def stats():
    """Displays library statistics."""
    if not library:
        return
    statistics = library.get_statistics()
    console.print(Panel.fit(
        f"[bold]Total Books:[/] {statistics['total_books']}\n"
        f"[bold]Unique Authors:[/] {statistics['unique_authors']}",
        title="Library Statistics",
        border_style="blue"
    ))

if __name__ == "__main__":
    app()
