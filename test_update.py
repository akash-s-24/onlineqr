from database import execute_db, query_db

execute_db(
    """
    UPDATE events 
    SET event_name = %s, event_type = %s, event_date = %s, event_time = %s, 
        venue = %s, description = %s, max_participants = %s,
        is_group = %s, min_team_size = %s, max_team_size = %s, event_fee = %s, upi_id = %s
    WHERE id = %s
    """,
    ('Python Test Update', 'Test', '2026-10-10', '10:00', 'Room', 'Desc', 100, 0, 1, 1, 100, 'test@upi', 1)
)

print(query_db("SELECT * FROM events WHERE id=1"))
