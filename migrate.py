import secrets
import database


def migrate():
    # Make sure column exists
    try:
        database.execute_db("ALTER TABLE registrations ADD COLUMN registration_uid VARCHAR(20) NULL;")
    except Exception:
        pass

    rows = database.query_db("SELECT id FROM registrations WHERE registration_uid IS NULL")
    for r in rows:
        uid = "REG-" + secrets.token_hex(5).upper()
        database.execute_db("UPDATE registrations SET registration_uid = %s WHERE id = %s", (uid, r['id']))
    print(f"Migrated {len(rows)} rows.")


if __name__ == "__main__":
    migrate()
