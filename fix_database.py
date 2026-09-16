import re

with open('/Users/akash/Documents/manager/database.py', 'r') as f:
    content = f.read()

# I want to disable the sample participant seeding.
old_block = """    # Seed Sample Participants if none exist
    parts_count = query_db("SELECT COUNT(*) as count FROM participants", one=True)
    if parts_count and parts_count.get('count', 0) == 0:
        sample_parts = [
            (2, 'Varshitha H', 'varshitha@college.edu', '9876543210', 'Shree Daksha Academy', 'BCA', '5th Sem'),
            (None, 'Rahul Kumar', 'rahul.k@univ.ac.in', '9845123456', 'City College of Technology', 'BSc Computer Science', '3rd Sem'),
            (None, 'Ananya Sharma', 'ananya.s@tech.edu', '9123456780', 'Shree Daksha Academy', 'BCA', '5th Sem'),
            (None, 'Karthik Rao', 'karthik.rao@gmail.com', '9880011223', 'National Institute of Engineering', 'B.Tech IT', '7th Sem'),
            (None, 'Sneha Patel', 'sneha.patel@college.edu', '9771122334', 'Shree Daksha Academy', 'MCA', '1st Sem')
        ]
        part_ids = []
        for p in sample_parts:
            pid = execute_db(
                "INSERT INTO participants (user_id, full_name, email, phone, college_name, department, semester) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                p
            )
            part_ids.append(pid)

        # Binary Brains is event_id for 'Binary Brains'
        bb_ev = query_db("SELECT id FROM events WHERE event_name = 'Binary Brains'", one=True)
        bb_id = bb_ev['id'] if bb_ev else 1
        dd_ev = query_db("SELECT id FROM events WHERE event_name = 'Digital Dynamos'", one=True)
        dd_id = dd_ev['id'] if dd_ev else 2
        cc_ev = query_db("SELECT id FROM events WHERE event_name = 'CodeCraft'", one=True)
        cc_id = cc_ev['id'] if cc_ev else 3

        # Seed sample registrations with group team details
        registrations_data = [
            ('REG-1001', part_ids[0], bb_id, None, 1, 'CyberKnights', 3, 'Varshitha H, Sneha Patel, Ananya Sharma', 'present', 'paid', 1500, 'Online'),
            ('REG-1002', part_ids[0], cc_id, None, 0, None, 1, None, 'present', 'paid', 250, 'Cash'),
            ('REG-1003', part_ids[1], dd_id, None, 1, 'Tech Titans', 2, 'Rahul Kumar, Karthik Rao', 'present', 'paid', 1000, 'Online'),
            ('REG-1004', part_ids[2], bb_id, None, 1, 'Binary Beasts', 3, 'Ananya Sharma, Rahul Kumar, Sneha Patel', 'present', 'paid', 1500, 'Online'),
            ('REG-1005', part_ids[3], cc_id, None, 0, None, 1, None, 'absent', 'paid', 250, 'Cash'),
            ('REG-1006', part_ids[4], dd_id, None, 1, 'Pixel Pioneers', 4, 'Sneha Patel, Varshitha H, Ananya Sharma, Karthik Rao', 'present', 'paid', 2000, 'Offline')
        ]

        for r_uid, pid, eid, reg_by, is_grp, tname, tsize, tmembers, att_status, pay_status, amount, method in registrations_data:
            reg_id = execute_db(
                "INSERT INTO registrations (registration_uid, participant_id, event_id, registered_by, is_group, team_name, team_size, team_members, status, payment_status, amount_paid, payment_method) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (r_uid, pid, eid, reg_by, is_grp, tname, tsize, tmembers, 'approved', pay_status, amount, method)
            )
            execute_db(
                "INSERT INTO attendance (registration_id, status, marked_by) VALUES (%s, %s, %s)",
                (reg_id, att_status, 'admin')
            )
        print("[DB Seed] Seeded sample participants, registrations with group teams, and attendance.")"""

new_block = """    # Seed Sample Participants if none exist
    # (Disabled per user request to start with a completely clean slate)
    pass"""

content = content.replace(old_block, new_block)

with open('/Users/akash/Documents/manager/database.py', 'w') as f:
    f.write(content)

print("Removed demo seeding")
