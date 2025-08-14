import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
import os

from main import app
from library import Library, Book
from database import DATABASE_FILE

runner = CliRunner()

# Fixture to ensure a clean database for each test
@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(DATABASE_FILE):
        os.remove(DATABASE_FILE)
    # Re-initialize the library to ensure it uses a clean DB for each test
    # This also triggers initialize_database() internally
    Library()
    yield
    if os.path.exists(DATABASE_FILE):
        os.remove(DATABASE_FILE)

def test_list_no_books():
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No books in library." in result.stdout

def test_add_book_success(monkeypatch):
    # Mock the external API call for add_book_by_isbn
    mock_book = Book(title="Test Book", author="Test Author", isbn="1234567890")
    monkeypatch.setattr(Library, "add_book_by_isbn", MagicMock(return_value=mock_book))

    result = runner.invoke(app, ["add", "1234567890"])
    assert result.exit_code == 0
    assert "Successfully added: Test Book by Test Author" in result.stdout
    Library.add_book_by_isbn.assert_called_once_with("1234567890")

def test_add_book_not_found(monkeypatch):
    monkeypatch.setattr(Library, "add_book_by_isbn", MagicMock(side_effect=LookupError("Book not found.")))

    result = runner.invoke(app, ["add", "0000000000"])
    assert result.exit_code == 0
    assert "Could not find book: Book not found." in result.stdout

def test_remove_book_success(monkeypatch):
    # Add a book first to ensure there's something to remove
    lib = Library()
    lib.add_book(Book("To Be Removed", "Remover", "999"))

    monkeypatch.setattr(Library, "remove_book", MagicMock(return_value=True))

    result = runner.invoke(app, ["remove", "999"])
    assert result.exit_code == 0
    assert "Book with ISBN 999 has been removed." in result.stdout
    Library.remove_book.assert_called_once_with("999")

def test_remove_book_not_found(monkeypatch):
    monkeypatch.setattr(Library, "remove_book", MagicMock(return_value=False))

    result = runner.invoke(app, ["remove", "nonexistent"])
    assert result.exit_code == 0
    assert "Book with ISBN nonexistent not found." in result.stdout

def test_find_book_success(monkeypatch):
    mock_book = Book(title="Found Book", author="Finder", isbn="111")
    monkeypatch.setattr(Library, "find_book", MagicMock(return_value=mock_book))

    result = runner.invoke(app, ["find", "111"])
    assert result.exit_code == 0
    assert "Book Found" in result.stdout
    assert "Title: Found Book" in result.stdout
    assert "Author: Finder" in result.stdout
    assert "ISBN: 111" in result.stdout
    Library.find_book.assert_called_once_with("111")

def test_find_book_not_found(monkeypatch):
    monkeypatch.setattr(Library, "find_book", MagicMock(return_value=None))

    result = runner.invoke(app, ["find", "nonexistent"])
    assert result.exit_code == 0
    assert "Book with ISBN nonexistent not found." in result.stdout

@patch('subprocess.run')
@patch('webbrowser.open')
def test_serve_command(mock_webbrowser_open, mock_subprocess_run):
    result = runner.invoke(app, ["serve"])
    assert result.exit_code == 0
    assert "Starting web UI on" in result.stdout
    mock_webbrowser_open.assert_called_once()
    mock_subprocess_run.assert_called_once()
    # Check if uvicorn is called with correct arguments
    args = mock_subprocess_run.call_args[0][0]
    assert "uvicorn" in args
    assert "api:app" in args
    assert "--host" in args
    assert "--port" in args
