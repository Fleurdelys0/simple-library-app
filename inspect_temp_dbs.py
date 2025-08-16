import os
import sqlite3
from glob import glob

temp = os.environ.get('TEMP') or os.environ.get('TMP')
if not temp:
    temp = '/tmp'

for path in glob(os.path.join(temp, 'library*.db')):
    print('---', path)
    try:
        conn = sqlite3.connect(path)
        for row in conn.execute('SELECT isbn, title FROM books'):
            print(row)
        conn.close()
    except Exception as e:
        print('error reading', path, e)
