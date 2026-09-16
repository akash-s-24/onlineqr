import sqlite3
import os

db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'eventmate.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

bb_id = 18 # Tech Quiz

# Create participant
cursor.execute("INSERT INTO participants (user_id, full_name, email, phone, college_name, department, semester) VALUES (NULL, 'Akash', 'levelupgamerz28@gmail.com', '8050774071', 'Test University', 'Gaming', '1st Sem')")
part_id = cursor.lastrowid

# Create registration
r_uid = 'REG-TEST-999'
cursor.execute("INSERT INTO registrations (registration_uid, participant_id, event_id, registered_by, is_group, team_name, team_size, team_members, status, payment_status, amount_paid, payment_method) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (r_uid, part_id, bb_id, None, 0, None, 1, None, 'approved', 'paid', 250, 'Online'))
reg_id = cursor.lastrowid

# Create attendance
cursor.execute("INSERT INTO attendance (registration_id, status, marked_by) VALUES (?, ?, ?)", (reg_id, 'present', 'admin'))

conn.commit()
conn.close()
print("Registered test user successfully!")
