from database import execute_db, query_db

execute_db(
    """
    UPDATE events 
    SET event_name = %s
    WHERE id = %s
    """,
    ('Python Test Update String', '1')
)

print(query_db("SELECT * FROM events WHERE id=1"))
