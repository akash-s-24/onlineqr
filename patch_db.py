import database

def patch():
    try:
        # Since it's Postgres/SQLite compatible syntax
        database.execute_db("ALTER TABLE events ADD COLUMN event_fee INTEGER DEFAULT 0;")
        print("Successfully added event_fee column.")
    except Exception as e:
        print(f"Error adding column (it might already exist): {e}")

if __name__ == '__main__':
    patch()
