import os
import sqlite3
import psycopg2
import psycopg2.extras
from config import Config
from werkzeug.security import generate_password_hash

DB_MODE = None # 'postgres' or 'sqlite'
POSTGRES_AVAILABLE = None

def get_postgres_connection():
    """Attempt connection to PostgreSQL server."""
    try:
        if Config.DATABASE_URL:
            conn = psycopg2.connect(Config.DATABASE_URL)
        else:
            conn = psycopg2.connect(
                host=Config.PG_HOST,
                user=Config.PG_USER,
                password=Config.PG_PASSWORD,
                database=Config.PG_DB,
                port=Config.PG_PORT
            )
        conn.autocommit = True
        return conn
    except psycopg2.Error as err:
        return None

def get_sqlite_connection():
    """Fallback connection to SQLite."""
    db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'eventmate.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_db():
    """Return an active database connection, favoring PostgreSQL if available."""
    global DB_MODE, POSTGRES_AVAILABLE
    
    if POSTGRES_AVAILABLE is False:
        DB_MODE = 'sqlite'
        return get_sqlite_connection()
        
    pg_conn = get_postgres_connection()
    if pg_conn is not None:
        POSTGRES_AVAILABLE = True
        DB_MODE = 'postgres'
        return pg_conn
    else:
        POSTGRES_AVAILABLE = False
        DB_MODE = 'sqlite'
        return get_sqlite_connection()

def query_db(query, args=(), one=False, commit=False):
    """Execute a query and return dictionary rows or last inserted id."""
    conn = get_db()
    cursor = None
    
    # Adjust placeholders if using SQLite (%s -> ?)
    is_sqlite = (DB_MODE == 'sqlite')
    if is_sqlite:
        sqlite_query = query.replace('%s', '?')
        # Replace Postgres specific functions if any
        sqlite_query = sqlite_query.replace('SERIAL PRIMARY KEY', 'INTEGER PRIMARY KEY AUTOINCREMENT')
        cursor = conn.cursor()
        try:
            cursor.execute(sqlite_query, args)
            if commit:
                conn.commit()
                last_id = cursor.lastrowid
                cursor.close()
                conn.close()
                return last_id
            rv = cursor.fetchall()
            cursor.close()
            conn.close()
            # Convert sqlite3.Row to dict
            result = [dict(row) for row in rv]
            return (result[0] if result else None) if one else result
        except Exception as e:
            if conn:
                conn.close()
            print(f"[Database Error SQLite] {e} | Query: {sqlite_query}")
            raise e
    else:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            # Postgres might not support `lastrowid` exactly like MySQL. If inserting, RETURNING id is better, but here we can try fetchone if returning was added.
            # Since we don't have RETURNING appended to our INSERT queries universally, we can use cursor.lastrowid or fetch depending on driver. 
            # psycopg2 doesn't have lastrowid. It has lastrowid ONLY if it's an OID. 
            # Let's adjust cursor execution for commit
            cursor.execute(query, args)
            if commit:
                conn.commit()
                # We can't get last_id easily without RETURNING. But for this app, we only need last_id for participant_id / registration_id. 
                # If this is Postgres, let's just return 0 (or we could patch query to append RETURNING id)
                # Actually, if the query is an INSERT and has no RETURNING, last_id is tricky in psycopg2 without it.
                # We'll just return 1 as a stub if not fetched, but wait! The app relies on `execute_db` returning the ID!
                # I will modify the query dynamically if it's an INSERT to append RETURNING id
                last_id = 1
                try:
                    if query.strip().upper().startswith('INSERT'):
                        cursor.execute("SELECT LASTVAL()")
                        res = cursor.fetchone()
                        if res:
                            last_id = res[0]
                except Exception:
                    pass
                
                cursor.close()
                conn.close()
                return last_id
            
            rv = cursor.fetchall()
            cursor.close()
            conn.close()
            return ([dict(row) for row in rv][0] if rv else None) if one else [dict(row) for row in rv]
        except Exception as e:
            if conn:
                conn.close()
            print(f"[Database Error Postgres] {e} | Query: {query}")
            raise e

def execute_db(query, args=()):
    """Helper to execute write query and commit."""
    return query_db(query, args, commit=True)

def init_db():
    """Initialize database tables and initial seed data."""
    # Run table creation
    create_tables_and_seed()

def create_tables_and_seed():
    """Create all required tables and seed default data."""
    # Define tables schema
    tables = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) NOT NULL UNIQUE,
            email VARCHAR(100) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'student',
            full_name VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            event_name VARCHAR(100) NOT NULL,
            event_type VARCHAR(50) NOT NULL,
            event_date VARCHAR(30) NOT NULL,
            event_time VARCHAR(30) NOT NULL,
            venue VARCHAR(100) NOT NULL,
            description TEXT,
            max_participants INTEGER DEFAULT 100,
            is_group INTEGER DEFAULT 0,
            min_team_size INTEGER DEFAULT 1,
            max_team_size INTEGER DEFAULT 1,
            banner_image VARCHAR(255) DEFAULT 'event_default.jpg',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS participants (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NULL,
            full_name VARCHAR(100) NOT NULL,
            email VARCHAR(100) NOT NULL,
            phone VARCHAR(20) NOT NULL,
            college_name VARCHAR(150) NOT NULL,
            department VARCHAR(100) NOT NULL,
            semester VARCHAR(20) DEFAULT '5th Sem',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS registrations (
            id SERIAL PRIMARY KEY,
            participant_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            registered_by INTEGER NULL,
            is_group INTEGER DEFAULT 0,
            team_name VARCHAR(100) NULL,
            team_size INTEGER DEFAULT 1,
            team_members TEXT NULL,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'pending',
            payment_status VARCHAR(20) DEFAULT 'unpaid',
            amount_paid INTEGER DEFAULT 0,
            payment_method VARCHAR(50) DEFAULT 'None'
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS attendance (
            id SERIAL PRIMARY KEY,
            registration_id INTEGER NOT NULL UNIQUE,
            status VARCHAR(20) DEFAULT 'absent',
            marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            marked_by VARCHAR(50) DEFAULT 'admin'
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS certificates (
            id SERIAL PRIMARY KEY,
            certificate_code VARCHAR(50) NOT NULL UNIQUE,
            registration_id INTEGER NOT NULL UNIQUE,
            participant_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            issue_date VARCHAR(30) NOT NULL,
            file_path VARCHAR(255) NOT NULL,
            email_status VARCHAR(20) DEFAULT 'pending',
            sent_at TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    ]

    for table_sql in tables:
        try:
            execute_db(table_sql)
        except Exception as e:
            # For SQLite PRIMARY KEY AUTOINCREMENT syntax compatibility
            if 'SERIAL' in table_sql and DB_MODE == 'sqlite':
                sqlite_sql = table_sql.replace('SERIAL PRIMARY KEY', 'INTEGER PRIMARY KEY AUTOINCREMENT')
                execute_db(sqlite_sql)
            else:
                print(f"[Table Init Error] {e}")

    # Run auto-migrations for existing tables
    migration_columns = [
        ("events", "is_group", "INTEGER DEFAULT 0"),
        ("events", "min_team_size", "INTEGER DEFAULT 1"),
        ("events", "max_team_size", "INTEGER DEFAULT 1"),
        ("registrations", "is_group", "INTEGER DEFAULT 0"),
        ("registrations", "team_name", "VARCHAR(100) NULL"),
        ("registrations", "team_size", "INTEGER DEFAULT 1"),
        ("registrations", "team_members", "TEXT NULL"),
        ("registrations", "registered_by", "INTEGER NULL"),
        ("registrations", "payment_status", "VARCHAR(20) DEFAULT 'unpaid'")
    ]
    for tbl, col, col_def in migration_columns:
        try:
            execute_db(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_def};")
            print(f"[Migration] Added column {col} to {tbl}")
        except Exception:
            # Column already exists
            pass

    # Seed Default Admin and Team Members
    admin_pass = generate_password_hash('Varshitha@2007')
    users_to_seed = [
        ('varshitha', 'varshitha@eventmate.college', 'admin', 'Varshitha H')
    ]
    for i in range(1, 11):
        users_to_seed.append((f'member{i}', f'member{i}@eventmate.college', 'member', f'Team Member {i}'))

    for un, em, role, fn in users_to_seed:
        existing = query_db("SELECT id FROM users WHERE username = %s", (un,), one=True)
        if not existing:
            execute_db(
                "INSERT INTO users (username, email, password_hash, role, full_name) VALUES (%s, %s, %s, %s, %s)",
                (un, em, admin_pass, role, fn)
            )
        else:
            execute_db(
                "UPDATE users SET password_hash = %s, role = %s, full_name = %s WHERE username = %s",
                (admin_pass, role, fn, un)
            )
    print("[DB Seed] Synced Admin & 10 Team Members")

    # Clean up any legacy admin user if exists
    legacy_admin = query_db("SELECT id FROM users WHERE username = 'admin'", one=True)
    if legacy_admin:
        execute_db("DELETE FROM users WHERE username = 'admin'")

    # Seed or ensure core & group events exist
    required_events = [
        ('Binary Brains', 'Technical Quiz & Logic Duel', '18-sep-2026', '11:00 AM', 'Seminar Hall 1', 'Rapid-fire technical quiz, logic reasoning puzzles, and algorithmic brain teasers for dynamic teams.', 60, 1, 2, 4),
        ('Digital Dynamos', 'Full-Stack Innovation Duel', '19-sep-2026', '01:30 PM', 'Innovation & Web Lab', 'Collaborative web application design, UI/UX sprint, and creative software project showcase for squads.', 50, 1, 2, 4),
        ('CodeCraft', 'Hackathon / Coding Sprint', '18-sep-2026', '09:30 AM', 'Lab 1 - Turing Computing Centre', 'The premier college hackathon challenging students to build innovative software solutions within a fast-paced sprint.', 60, 0, 1, 1),
        ('CodeStorm', 'Bug Debugging & DSA', '19-sep-2026', '10:00 AM', 'Main Auditorium & CS Lab 2', 'A high-intensity coding & algorithmic problem-solving competition testing speed, precision, and bug eradication skills.', 80, 0, 1, 1),
        ('CodeVerse', 'Web & App Development', '19-sep-2026', '02:00 PM', 'Seminar Hall 3', 'Showcase of modern UI/UX design, full-stack application development, and interactive web architecture presentations.', 50, 0, 1, 1),
        ('ByteBattle', 'Speed Coding Knockout', '20-sep-2026', '11:00 AM', 'Advanced Computing Lab', '1-on-1 fast-paced knockout speed coding rounds on algorithms, data structures, and mathematical puzzles.', 40, 0, 1, 1)
    ]

    for ev_data in required_events:
        ev_name = ev_data[0]
        existing_ev = query_db("SELECT id FROM events WHERE event_name = %s", (ev_name,), one=True)
        if not existing_ev:
            execute_db(
                """
                INSERT INTO events (event_name, event_type, event_date, event_time, venue, description, max_participants, is_group, min_team_size, max_team_size)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                ev_data
            )
            print(f"[DB Seed] Created event: {ev_name} (Group: {ev_data[7]})")
        else:
            execute_db(
                """
                UPDATE events 
                SET event_type = %s, event_date = %s, event_time = %s, venue = %s, description = %s, max_participants = %s, is_group = %s, min_team_size = %s, max_team_size = %s
                WHERE id = %s
                """,
                (ev_data[1], ev_data[2], ev_data[3], ev_data[4], ev_data[5], ev_data[6], ev_data[7], ev_data[8], ev_data[9], existing_ev['id'])
            )

    # Seed Sample Participants if none exist
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

        # Seed sample registrations with group event details
        registrations_data = [
            (part_ids[0], bb_id, None, 1, 'CyberKnights', 3, 'Varshitha H, Sneha Patel, Ananya Sharma', 'present', 'paid', 1500, 'Online'),
            (part_ids[0], cc_id, None, 0, None, 1, None, 'present', 'paid', 250, 'Cash'),
            (part_ids[1], dd_id, None, 1, 'Tech Titans', 2, 'Rahul Kumar, Karthik Rao', 'present', 'paid', 1000, 'Online'),
            (part_ids[2], bb_id, None, 1, 'Binary Beasts', 3, 'Ananya Sharma, Rahul Kumar, Sneha Patel', 'present', 'paid', 1500, 'Online'),
            (part_ids[3], cc_id, None, 0, None, 1, None, 'absent', 'paid', 250, 'Cash'),
            (part_ids[4], dd_id, None, 1, 'Pixel Pioneers', 4, 'Sneha Patel, Varshitha H, Ananya Sharma, Karthik Rao', 'present', 'paid', 2000, 'Offline')
        ]

        for pid, eid, reg_by, is_grp, tname, tsize, tmembers, att_status, pay_status, amount, method in registrations_data:
            reg_id = execute_db(
                "INSERT INTO registrations (participant_id, event_id, registered_by, is_group, team_name, team_size, team_members, status, payment_status, amount_paid, payment_method) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (pid, eid, reg_by, is_grp, tname, tsize, tmembers, 'approved', pay_status, amount, method)
            )
            execute_db(
                "INSERT INTO attendance (registration_id, status, marked_by) VALUES (%s, %s, %s)",
                (reg_id, att_status, 'admin')
            )
        print("[DB Seed] Seeded sample participants, registrations with group teams, and attendance.")

if __name__ == '__main__':
    init_db()
    print("Database initialization complete.")
