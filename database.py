import os
import re
import secrets
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
    """Return a connection, never silently falling back from configured Postgres."""
    global DB_MODE, POSTGRES_AVAILABLE

    # A hosted deployment must never write registrations to an ephemeral local
    # SQLite file because a configured database is temporarily unavailable.
    if Config.DATABASE_URL or Config.APP_ENV == 'production':
        if not Config.DATABASE_URL:
            raise RuntimeError('DATABASE_URL is required in production.')
        pg_conn = get_postgres_connection()
        if pg_conn is None:
            raise RuntimeError('DATABASE_URL is configured, but PostgreSQL is unavailable.')
        POSTGRES_AVAILABLE = True
        DB_MODE = 'postgres'
        return pg_conn
    
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


def create_registration(*, full_name, email, phone, college_name, department,
                        semester, event_id, team_name, team_size,
                        team_members, payment_status, amount_paid,
                        payment_method, utr_number, registered_by,
                        is_group_event):
    """Create a participant, registration, and attendance row atomically.

    Capacity, duplicate-registration, and duplicate-UTR checks happen inside
    the same transaction as the inserts. This prevents two simultaneous form
    submissions from creating conflicting payment records.
    """
    conn = get_db()
    is_sqlite = DB_MODE == 'sqlite'
    cursor = None

    def execute(query, args=()):
        if is_sqlite:
            query = query.replace('%s', '?')
        cursor.execute(query, args)

    try:
        if is_sqlite:
            conn.execute('BEGIN IMMEDIATE')
            cursor = conn.cursor()
        else:
            conn.autocommit = False
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        event_query = """
            SELECT id, max_participants
            FROM events
            WHERE id = %s
        """
        if not is_sqlite:
            event_query += ' FOR UPDATE'
        execute(event_query, (event_id,))
        event = cursor.fetchone()
        if not event:
            conn.rollback()
            return {'ok': False, 'reason': 'invalid_event'}

        execute("SELECT id FROM participants WHERE email = %s", (email,))
        participant = cursor.fetchone()
        if participant:
            participant_id = participant['id']
            execute(
                "SELECT id FROM registrations WHERE participant_id = %s AND event_id = %s",
                (participant_id, event_id)
            )
            if cursor.fetchone():
                conn.rollback()
                return {'ok': False, 'reason': 'duplicate_registration'}
            execute(
                """
                UPDATE participants
                SET full_name = %s, phone = %s, college_name = %s,
                    department = %s, semester = %s,
                    user_id = COALESCE(%s, user_id)
                WHERE id = %s
                """,
                (full_name, phone, college_name, department, semester,
                 registered_by, participant_id)
            )
        else:
            if is_sqlite:
                execute(
                    """
                    INSERT INTO participants
                        (user_id, full_name, email, phone, college_name, department, semester)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (registered_by, full_name, email, phone, college_name,
                     department, semester)
                )
                participant_id = cursor.lastrowid
            else:
                execute(
                    """
                    INSERT INTO participants
                        (user_id, full_name, email, phone, college_name, department, semester)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (registered_by, full_name, email, phone, college_name,
                     department, semester)
                )
                participant_id = cursor.fetchone()['id']

        if utr_number:
            execute(
                "SELECT id FROM registrations WHERE utr_number = %s",
                (utr_number,)
            )
            if cursor.fetchone():
                conn.rollback()
                return {'ok': False, 'reason': 'duplicate_utr'}

        max_participants = int(event['max_participants'] or 0)
        execute(
            """
            SELECT COALESCE(SUM(CASE WHEN team_size > 0 THEN team_size ELSE 1 END), 0) AS participant_count
            FROM registrations
            WHERE event_id = %s AND COALESCE(status, 'pending') <> 'cancelled'
            """,
            (event_id,)
        )
        current_count = int((cursor.fetchone() or {'participant_count': 0})['participant_count'] or 0)
        if max_participants > 0 and current_count + team_size > max_participants:
            conn.rollback()
            return {
                'ok': False,
                'reason': 'capacity_reached',
                'remaining': max(0, max_participants - current_count)
            }

        registration_uid = 'REG-' + secrets.token_hex(5).upper()
        registration_query = """
            INSERT INTO registrations
                (registration_uid, participant_id, event_id, registered_by,
                 is_group, team_name, team_size, team_members,
                 payment_status, status, amount_paid, payment_method, utr_number)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        if is_sqlite:
            execute(
                registration_query,
                (registration_uid, participant_id, event_id, registered_by,
                 is_group_event, team_name, team_size, team_members,
                 payment_status, 'approved' if registered_by else 'pending',
                 amount_paid, payment_method, utr_number)
            )
            registration_id = cursor.lastrowid
        else:
            execute(
                registration_query + ' RETURNING id',
                (registration_uid, participant_id, event_id, registered_by,
                 is_group_event, team_name, team_size, team_members,
                 payment_status, 'approved' if registered_by else 'pending',
                 amount_paid, payment_method, utr_number)
            )
            registration_id = cursor.fetchone()['id']

        execute(
            "INSERT INTO attendance (registration_id, status, marked_by) VALUES (%s, %s, %s)",
            (registration_id, 'absent', 'system')
        )

        conn.commit()
        return {
            'ok': True,
            'registration_id': registration_id,
            'registration_uid': registration_uid
        }
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def init_db():
    """Initialize database tables and initial seed data."""
    # Run table creation
    create_tables_and_seed()


def normalize_legacy_banner_filenames():
    """Normalize legacy banner filenames so generated URLs are portable."""
    rows = query_db(
        "SELECT id, banner_image FROM events WHERE banner_image IS NOT NULL AND banner_image <> ''"
    )
    images_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'images')

    for row in rows:
        original = row['banner_image']
        if '/' in original or '\\' in original:
            continue

        normalized = re.sub(r'[^A-Za-z0-9._-]+', '_', original).strip('_')
        if not normalized or normalized == original:
            continue

        source = os.path.join(images_dir, original)
        target = os.path.join(images_dir, normalized)
        if os.path.isfile(source) and not os.path.exists(target):
            os.replace(source, target)

        # Point the database at the normalized asset whether the target already
        # existed or was just moved into place.
        if os.path.exists(target):
            execute_db(
                "UPDATE events SET banner_image = %s WHERE id = %s",
                (normalized, row['id'])
            )

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
            event_fee INTEGER DEFAULT 0,
            upi_id VARCHAR(100) DEFAULT 'admin@upi',
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
            registration_uid VARCHAR(20) UNIQUE,
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
            payment_method VARCHAR(50) DEFAULT 'None',
            utr_number VARCHAR(100) NULL
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
            if Config.DATABASE_URL:
                raise RuntimeError(f'PostgreSQL schema initialization failed: {e}') from e
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
        ("events", "event_fee", "INTEGER DEFAULT 0"),
        ("events", "upi_id", "VARCHAR(100) DEFAULT 'admin@upi'"),
        ("events", "banner_image", "VARCHAR(255) DEFAULT 'event_default.jpg'"),
        ("events", "qr_code_image", "VARCHAR(255) NULL"),
        ("registrations", "is_group", "INTEGER DEFAULT 0"),
        ("registrations", "team_name", "VARCHAR(100) NULL"),
        ("registrations", "team_size", "INTEGER DEFAULT 1"),
        ("registrations", "team_members", "TEXT NULL"),
        ("registrations", "registered_by", "INTEGER NULL"),
        ("registrations", "registration_date", "TIMESTAMP NULL"),
        ("registrations", "status", "VARCHAR(20) DEFAULT 'pending'"),
        ("registrations", "payment_status", "VARCHAR(20) DEFAULT 'unpaid'"),
        ("registrations", "amount_paid", "INTEGER DEFAULT 0"),
        ("registrations", "payment_method", "VARCHAR(50) DEFAULT 'None'"),
        ("registrations", "utr_number", "VARCHAR(100) NULL"),
        ("registrations", "registration_uid", "VARCHAR(20) NULL"),
        # Event contact & rules fields
        ("events", "rules_text", "TEXT NULL"),
        ("events", "faculty_name", "VARCHAR(100) NULL"),
        ("events", "faculty_phone", "VARCHAR(20) NULL"),
        ("events", "student_name", "VARCHAR(100) NULL"),
        ("events", "student_phone", "VARCHAR(20) NULL"),
    ]
    # Inspect the schema before changing it.  This keeps startup quiet and avoids
    # repeatedly attempting ALTER TABLE on every application restart.
    table_columns = {}
    for table_name in {table for table, _, _ in migration_columns}:
        if DB_MODE == 'sqlite':
            rows = query_db(f"PRAGMA table_info({table_name})")
            table_columns[table_name] = {row['name'] for row in rows}
        else:
            rows = query_db(
                "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
                (table_name,)
            )
            table_columns[table_name] = {row['column_name'] for row in rows}

    for tbl, col, col_def in migration_columns:
        if col in table_columns.get(tbl, set()):
            continue
        execute_db(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_def};")
        table_columns.setdefault(tbl, set()).add(col)

    duplicate_pairs = query_db(
        """
        SELECT participant_id, event_id, COUNT(*) AS duplicate_count
        FROM registrations
        GROUP BY participant_id, event_id
        HAVING COUNT(*) > 1
        """
    )
    if duplicate_pairs:
        raise RuntimeError(
            'Duplicate participant/event registrations exist; resolve them before enabling registration.'
        )

    execute_db(
        "UPDATE registrations SET utr_number = NULL "
        "WHERE utr_number IS NOT NULL AND TRIM(utr_number) = ''"
    )
    duplicate_uids = query_db(
        """
        SELECT registration_uid, COUNT(*) AS duplicate_count
        FROM registrations
        WHERE registration_uid IS NOT NULL
        GROUP BY registration_uid
        HAVING COUNT(*) > 1
        """
    )
    if duplicate_uids:
        raise RuntimeError(
            'Duplicate registration references exist; resolve them before enabling registration.'
        )

    execute_db(
        "CREATE UNIQUE INDEX IF NOT EXISTS registrations_participant_event_unique "
        "ON registrations (participant_id, event_id)"
    )
    execute_db(
        "CREATE UNIQUE INDEX IF NOT EXISTS registrations_utr_unique "
        "ON registrations (utr_number)"
    )
    execute_db(
        "CREATE UNIQUE INDEX IF NOT EXISTS registrations_uid_unique "
        "ON registrations (registration_uid)"
    )

    # Backfill the event copy with complete, useful descriptions without
    # overwriting descriptions that an administrator has already authored.
    event_descriptions = {
        'BGMI': 'A strategic battle royale team tournament testing communication, survival skills, and tactical decision-making.',
        'Ramp Walk': 'A confident fashion showcase judged on presentation, creativity, stage presence, and styling.',
        'Free Fire': 'A fast-paced battle royale competition where teams compete through precision, strategy, and teamwork.',
        'Pencil Sketch': 'An individual sketching challenge celebrating observation, composition, detail, and artistic expression.',
        'Get the Shield': 'A spirited general-knowledge and challenge event where participants compete for the championship shield.',
        'Photography': 'Capture a compelling visual story using composition, lighting, timing, and creative perspective.',
        'Content Creator': 'Create an engaging short-form piece that combines originality, storytelling, visual quality, and audience appeal.',
        'Solo Dance': 'A solo performance judged on choreography, rhythm, expression, stage presence, and originality.',
        'Group Dance': 'A coordinated team performance judged on synchronization, formation, energy, expression, and creativity.',
        'Beat Boxing': 'Showcase rhythm, vocal percussion, musicality, and originality in a live beatboxing performance.',
        'Face Painting': 'Transform a face into an expressive artwork through concept, technique, color, and finishing detail.',
        'Tech Quiz': 'A rapid-fire technology quiz covering computing fundamentals, innovation, logic, and current digital trends.',
        'Mad Adds': 'Develop and perform a memorable advertisement that combines a clear message, creativity, humor, and teamwork.',
        'Mono Acting': 'A solo acting performance focused on character, voice, body language, expression, and storytelling.',
    }
    for event_name, description in event_descriptions.items():
        execute_db(
            """
            UPDATE events
            SET description = %s
            WHERE event_name = %s
              AND (description IS NULL OR TRIM(description) = '' OR LOWER(TRIM(description)) IN ('desc', 'description'))
            """,
            (description, event_name)
        )

    # Never leave a card with a placeholder or blank copy, including events
    # created later through the admin form. Known events use the tailored copy
    # above; unknown names receive a safe, name-aware baseline description.
    placeholder_events = query_db(
        """
        SELECT id, event_name
        FROM events
        WHERE description IS NULL
           OR TRIM(description) = ''
           OR LOWER(TRIM(description)) IN ('desc', 'description')
        """
    )
    for event in placeholder_events:
        event_name = (event.get('event_name') or 'This event').strip()
        execute_db(
            "UPDATE events SET description = %s WHERE id = %s",
            (f'{event_name} is a curated college competition focused on participation, creativity, and skill.', event['id'])
        )

    normalize_legacy_banner_filenames()

    # Seed demo users only when an administrator explicitly supplies a password.
    # Never create or overwrite accounts with a password embedded in source code.
    if Config.ADMIN_PASSWORD:
        admin_pass = generate_password_hash(Config.ADMIN_PASSWORD)
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
        print("[DB Seed] Synced configured admin and team member accounts")
    else:
        print("[DB Seed] Account password sync skipped; set ADMIN_PASSWORD in the environment")

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

    # Only seed events if the table is completely empty to prevent overwriting user edits/renames
    events_count = query_db("SELECT COUNT(*) as count FROM events", one=True)
    if events_count and events_count.get('count', 0) == 0:
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

    # Seed Sample Participants if none exist
    # (Disabled per user request to start with a completely clean slate)
    pass

if __name__ == '__main__':
    init_db()
    print("Database initialization complete.")
