import os
from database import DATABASE_FILE, initialize_database
from library import Library
from book import Book
import sqlite3

print('DATABASE_FILE=', DATABASE_FILE)
if os.path.exists(DATABASE_FILE):
    os.remove(DATABASE_FILE)
initialize_database()
lib = Library()
print('lib initial count', len(lib.list_books()))
lib.add_book(Book('Sapiens','Yuval Noah Harari','9780099590088'))
print('after add, lib count', len(lib.list_books()))
lib2 = Library()
print('lib2 count', len(lib2.list_books()))
# Print DB rows
conn = sqlite3.connect(DATABASE_FILE)
for row in conn.execute('SELECT isbn, title FROM books'):
    print('row', row)
conn.close()
