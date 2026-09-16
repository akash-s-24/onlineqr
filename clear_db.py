import sqlite3
import os

db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'eventmate.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("DELETE FROM attendance")
cursor.execute("DELETE FROM certificates")
cursor.execute("DELETE FROM registrations")
cursor.execute("DELETE FROM participants")
conn.commit()
conn.close()
print("Database cleared.")
