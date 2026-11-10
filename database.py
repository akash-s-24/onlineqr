import os
import re
import secrets
import sqlite3
try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool
except Exception as e:
    psycopg2 = None
    print(f"[Database Warning] psycopg2 could not be loaded: {e}")
from config import Config
from werkzeug.security import generate_password_hash

DB_MODE = None # 'postgres' or 'sqlite'
POSTGRES_AVAILABLE = None
PG_POOL = None
_DB_INITIALIZED = False

def get_postgres_pool():
    global PG_POOL
    if psycopg2 is None:
        return None
    if PG_POOL is not None and not PG_POOL.closed:
        return PG_POOL
    try:
        db_url = Config.DATABASE_URL
        if db_url:
            db_url = db_url.strip()
            if db_url.startswith('postgres://'):
                db_url = 'postgresql://' + db_url[len('postgres://'):]
            if 'sslmode=' not in db_url and any(host in db_url for host in ('supabase', 'neon.tech', 'render.com', 'aws')):
                sep = '&' if '?' in db_url else '?'
                db_url = f"{db_url}{sep}sslmode=require"
            if 'connect_timeout=' not in db_url:
                sep = '&' if '?' in db_url else '?'
                db_url = f"{db_url}{sep}connect_timeout=5"
            PG_POOL = psycopg2.pool.ThreadedConnectionPool(1, 10, db_url)
        else:
            PG_POOL = psycopg2.pool.ThreadedConnectionPool(
                1, 10,
                host=Config.PG_HOST,
                user=Config.PG_USER,
                password=Config.PG_PASSWORD,
                database=Config.PG_DB,
                port=Config.PG_PORT,
                connect_timeout=5,
                sslmode='require' if Config.APP_ENV == 'production' else 'prefer'
            )
        return PG_POOL
    except Exception as err:
        print(f"[PostgreSQL Pool Init Error] {err}")
        PG_POOL = None
        return None

def get_postgres_connection():
    """Attempt connection to PostgreSQL server using the pool or fresh connection."""
    pool = get_postgres_pool()
    if pool:
        try:
            conn = pool.getconn()
            if conn and not conn.closed:
                conn.autocommit = True
                return conn
            elif conn:
                pool.putconn(conn, close=True)
        except Exception:
            pass
    # Fallback to direct connection if pool fails
    try:
        db_url = Config.DATABASE_URL
        if db_url:
            db_url = db_url.strip()
            if db_url.startswith('postgres://'):
                db_url = 'postgresql://' + db_url[len('postgres://'):]
            if 'sslmode=' not in db_url and any(host in db_url for host in ('supabase', 'neon.tech', 'render.com', 'aws')):
                sep = '&' if '?' in db_url else '?'
                db_url = f"{db_url}{sep}sslmode=require"
            if 'connect_timeout=' not in db_url:
                sep = '&' if '?' in db_url else '?'
                db_url = f"{db_url}{sep}connect_timeout=5"
            conn = psycopg2.connect(db_url, connect_timeout=5)
        else:
            conn = psycopg2.connect(
                host=Config.PG_HOST,
                user=Config.PG_USER,
                password=Config.PG_PASSWORD,
                database=Config.PG_DB,
                port=Config.PG_PORT,
                connect_timeout=5,
                sslmode='require' if Config.APP_ENV == 'production' else 'prefer'
            )
        conn.autocommit = True
        return conn
    except Exception as err:
        print(f"[PostgreSQL Connection Error] {err}")
        if 'supabase.co' in str(Config.DATABASE_URL or ''):
            print("[PostgreSQL Supabase Tip] Supabase 'db.xxxx.supabase.co' is IPv6 only. On Render, please use the Supabase Pooler URL ('aws-0-xxxx.pooler.supabase.com:6543') with IPv4 support and ensure your password contains no raw special characters like '@' or '#'.")
        return None

def release_db_connection(conn):
    """Safely return a connection to pool or close it."""
    if conn is None:
        return
    global DB_MODE, PG_POOL
    if DB_MODE == 'sqlite':
        try:
            conn.close()
        except Exception:
            pass
    else:
        if PG_POOL and not PG_POOL.closed:
            try:
                if not conn.closed:
                    conn.autocommit = True
                PG_POOL.putconn(conn)
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
        else:
            try:
                conn.close()
            except Exception:
                pass

def get_sqlite_connection():
    """Fallback connection to SQLite with concurrency optimization."""
    db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'eventmate.db')
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    return conn

def get_db():
    """Return a connection, never silently falling back from configured Postgres."""
    global DB_MODE, POSTGRES_AVAILABLE

    if Config.DATABASE_URL or Config.APP_ENV == 'production':
        if not Config.DATABASE_URL:
            raise RuntimeError('DATABASE_URL is required in production.')
        pg_conn = get_postgres_connection()
        if pg_conn is None:
            raise RuntimeError('DATABASE_URL is configured, but PostgreSQL is unavailable. Check the [PostgreSQL Connection Error] log line above for the exact reason (e.g. invalid password, IPv6 hostname, or missing pooler).')
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
    is_sqlite = (DB_MODE == 'sqlite')
    try:
        if is_sqlite:
            sqlite_query = query.replace('%s', '?')
            sqlite_query = sqlite_query.replace('SERIAL PRIMARY KEY', 'INTEGER PRIMARY KEY AUTOINCREMENT')
            cursor = conn.cursor()
            try:
                cursor.execute(sqlite_query, args)
                if commit:
                    conn.commit()
                    if sqlite_query.lstrip().upper().startswith('INSERT'):
                        last_id = cursor.lastrowid
                    else:
                        last_id = cursor.rowcount
                    cursor.close()
                    return last_id
                rv = cursor.fetchall()
                cursor.close()
                result = [dict(row) for row in rv]
                return (result[0] if result else None) if one else result
            except Exception as e:
                print(f"[Database Error SQLite] {e} | Query: {sqlite_query}")
                raise e
        else:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            try:
                cursor.execute(query, args)
                if commit:
                    conn.commit()
                    last_id = cursor.rowcount
                    try:
                        if query.strip().upper().startswith('INSERT'):
                            last_id = 1
                            cursor.execute("SELECT LASTVAL()")
                            res = cursor.fetchone()
                            if res:
                                last_id = res[0]
                    except Exception:
                        pass
                    cursor.close()
                    return last_id
                rv = cursor.fetchall()
                cursor.close()
                return ([dict(row) for row in rv][0] if rv else None) if one else [dict(row) for row in rv]
            except Exception as e:
                if conn and not conn.closed:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                print(f"[Database Error Postgres] {e} | Query: {query}")
                raise e
    finally:
        release_db_connection(conn)

def execute_db(query, args=()):
    """Helper to execute a write query and return its affected-row count or ID."""
    return query_db(query, args, commit=True)


def create_registration(*, full_name, email, phone, college_name, department,
                        semester, event_id, team_name, team_size,
                        team_members, payment_status, amount_paid,
                        payment_method, utr_number, registered_by,
                        is_group_event, payment_proof=None):
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
                 payment_status, status, amount_paid, payment_method, utr_number, payment_proof)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        if is_sqlite:
            execute(
                registration_query,
                (registration_uid, participant_id, event_id, registered_by,
                 is_group_event, team_name, team_size, team_members,
                 payment_status, 'approved' if registered_by else 'pending',
                 amount_paid, payment_method, utr_number, payment_proof)
            )
            registration_id = cursor.lastrowid
        else:
            execute(
                registration_query + ' RETURNING id',
                (registration_uid, participant_id, event_id, registered_by,
                 is_group_event, team_name, team_size, team_members,
                 payment_status, 'approved' if registered_by else 'pending',
                 amount_paid, payment_method, utr_number, payment_proof)
            )
            registration_id = cursor.fetchone()['id']

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
            try:
                cursor.close()
            except Exception:
                pass
        release_db_connection(conn)

def init_db():
    """Initialize database tables and initial seed data."""
    # Run table creation
    create_tables_and_seed()


def normalize_legacy_banner_filenames(cursor=None, is_sqlite=False):
    """Normalize legacy banner filenames so generated URLs are portable."""
    if cursor is not None:
        cursor.execute("SELECT id, banner_image FROM events WHERE banner_image IS NOT NULL AND banner_image <> ''")
        rows = [dict(r) for r in cursor.fetchall()]
    else:
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
            if cursor is not None:
                q = "UPDATE events SET banner_image = ? WHERE id = ?" if is_sqlite else "UPDATE events SET banner_image = %s WHERE id = %s"
                cursor.execute(q, (normalized, row['id']))
            else:
                execute_db(
                    "UPDATE events SET banner_image = %s WHERE id = %s",
                    (normalized, row['id'])
                )

def create_tables_and_seed():
    """Create all required tables and seed default data using a single database connection."""
    global _DB_INITIALIZED
    if _DB_INITIALIZED:
        return

    conn = get_db()
    is_sqlite = (DB_MODE == 'sqlite')
    cursor = conn.cursor() if is_sqlite else conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    def run_exec(sql, args=()):
        if is_sqlite:
            sql = sql.replace('%s', '?').replace('SERIAL PRIMARY KEY', 'INTEGER PRIMARY KEY AUTOINCREMENT')
        cursor.execute(sql, args)

    def run_query(sql, args=(), one=False):
        if is_sqlite:
            sql = sql.replace('%s', '?')
        cursor.execute(sql, args)
        rows = cursor.fetchall()
        result = [dict(r) for r in rows]
        return (result[0] if result else None) if one else result

    try:
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
            CREATE TABLE IF NOT EXISTS event_showcase_sections (
                id SERIAL PRIMARY KEY,
                section_key VARCHAR(80) NOT NULL UNIQUE,
                eyebrow VARCHAR(120) NOT NULL DEFAULT 'THE LINEUP',
                title VARCHAR(180) NOT NULL DEFAULT 'Pick your frequency.',
                description TEXT NULL,
                background_color VARCHAR(30) NOT NULL DEFAULT '#11131b',
                banner_image VARCHAR(255) NULL,
                is_enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                utr_number VARCHAR(100) NULL,
                payment_proof VARCHAR(255) NULL,
                payment_verified_at TIMESTAMP NULL,
                payment_verified_by INTEGER NULL,
                receipt_sent_at TIMESTAMP NULL,
                receipt_delivery_status VARCHAR(20) DEFAULT 'not_sent'
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
                run_exec(table_sql)
            except Exception as e:
                if not is_sqlite:
                    raise RuntimeError(f'PostgreSQL schema initialization failed: {e}') from e
                if 'SERIAL' in table_sql and is_sqlite:
                    sqlite_sql = table_sql.replace('SERIAL PRIMARY KEY', 'INTEGER PRIMARY KEY AUTOINCREMENT')
                    run_exec(sqlite_sql)
                else:
                    print(f"[Table Init Error] {e}")

        # The public disc-cascade section is a singleton-style editable content
        # block. Keeping it in the database lets administrators change copy and
        # artwork without touching the event records themselves.
        showcase = run_query(
            "SELECT id FROM event_showcase_sections WHERE section_key = %s",
            ('main-events',), one=True
        )
        if not showcase:
            run_exec(
                """
                INSERT INTO event_showcase_sections
                    (section_key, eyebrow, title, description, background_color, is_enabled)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    'main-events',
                    'THE LINEUP',
                    'Pick your frequency.',
                    'A living catalogue of every stage, skill, and squad at Shreedaksha Academy.',
                    '#11131b',
                    1,
                )
            )

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
            ("registrations", "payment_proof", "VARCHAR(255) NULL"),
            ("registrations", "payment_verified_at", "TIMESTAMP NULL"),
            ("registrations", "payment_verified_by", "INTEGER NULL"),
            ("registrations", "receipt_sent_at", "TIMESTAMP NULL"),
            ("registrations", "receipt_delivery_status", "VARCHAR(20) DEFAULT 'not_sent'"),
            ("registrations", "registration_uid", "VARCHAR(20) NULL"),
            # Event contact & rules fields
            ("events", "rules_text", "TEXT NULL"),
            ("events", "faculty_name", "VARCHAR(100) NULL"),
            ("events", "faculty_phone", "VARCHAR(20) NULL"),
            ("events", "student_name", "VARCHAR(100) NULL"),
            ("events", "student_phone", "VARCHAR(20) NULL"),
        ]
        table_columns = {}
        for table_name in {table for table, _, _ in migration_columns}:
            if is_sqlite:
                cursor.execute(f"PRAGMA table_info({table_name})")
                rows = cursor.fetchall()
                table_columns[table_name] = {row['name'] for row in rows}
            else:
                cursor.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
                    (table_name,)
                )
                rows = cursor.fetchall()
                table_columns[table_name] = {row['column_name'] for row in rows}

        for tbl, col, col_def in migration_columns:
            if col in table_columns.get(tbl, set()):
                continue
            run_exec(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_def};")
            table_columns.setdefault(tbl, set()).add(col)

        run_exec(
            "UPDATE registrations SET utr_number = NULL "
            "WHERE utr_number IS NOT NULL AND TRIM(utr_number) = ''"
        )

        run_exec(
            "CREATE UNIQUE INDEX IF NOT EXISTS registrations_participant_event_unique "
            "ON registrations (participant_id, event_id)"
        )
        run_exec(
            "CREATE UNIQUE INDEX IF NOT EXISTS registrations_utr_unique "
            "ON registrations (utr_number)"
        )
        run_exec(
            "CREATE UNIQUE INDEX IF NOT EXISTS registrations_uid_unique "
            "ON registrations (registration_uid)"
        )

        # Backfill event copy
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
            run_exec(
                """
                UPDATE events
                SET description = %s
                WHERE event_name = %s
                  AND (description IS NULL OR TRIM(description) = '' OR LOWER(TRIM(description)) IN ('desc', 'description'))
                """,
                (description, event_name)
            )

        placeholder_events = run_query(
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
            run_exec(
                "UPDATE events SET description = %s WHERE id = %s",
                (f'{event_name} is a curated college competition focused on participation, creativity, and skill.', event['id'])
            )

        normalize_legacy_banner_filenames(cursor=cursor, is_sqlite=is_sqlite)

        # Seed admin and team users only when an administrator explicitly supplies a password.
        if Config.ADMIN_PASSWORD:
            admin_pass = generate_password_hash(Config.ADMIN_PASSWORD)
            users_to_seed = [
                ('admin', 'admin@shreedakshaacademyedu.in', 'admin', 'admin'),
                ('admin1', 'admin1@shreedakshaacademyedu.in', 'admin', 'admin SDA1'),
                ('admin2', 'admin2@shreedakshaacademyedu.in', 'admin', 'admin SDA2')
            ]
            for i in range(1, 11):
                users_to_seed.append((f'member{i}', f'member{i}@shreedakshaacademyedu.in', 'member', f'Team Member {i}'))

            for un, em, role, fn in users_to_seed:
                existing = run_query("SELECT id FROM users WHERE username = %s", (un,), one=True)
                if not existing:
                    run_exec(
                        "INSERT INTO users (username, email, password_hash, role, full_name) VALUES (%s, %s, %s, %s, %s)",
                        (un, em, admin_pass, role, fn)
                    )
                else:
                    run_exec(
                        "UPDATE users SET password_hash = %s, role = %s, full_name = %s, email = %s WHERE username = %s",
                        (admin_pass, role, fn, em, un)
                    )
            print("[DB Seed] Synced configured admin and team member accounts")
        else:
            print("[DB Seed] Account password sync skipped; set ADMIN_PASSWORD in the environment")

        # Migrate any legacy varshitha account to admin
        legacy_varshitha = run_query("SELECT id FROM users WHERE username = 'varshitha'", one=True)
        if legacy_varshitha:
            admin_user = run_query("SELECT id FROM users WHERE username = 'admin'", one=True)
            if not admin_user:
                run_exec("UPDATE users SET username = 'admin', full_name = 'admin', email = 'admin@shreedakshaacademyedu.in' WHERE username = 'varshitha'")
            else:
                run_exec("DELETE FROM users WHERE username = 'varshitha'")

        # Purge legacy symposium placeholder events if present
        legacy_old_names = ('Binary Brains', 'Digital Dynamos', 'CodeCraft', 'CodeStorm', 'CodeVerse', 'ByteBattle')
        run_exec("DELETE FROM events WHERE event_name IN (%s, %s, %s, %s, %s, %s)", legacy_old_names)

        # 14 Official local events
        official_events = [
            {
                'event_name': 'BGMI',
                'event_type': 'Gaming',
                'event_date': '19-sep-2026',
                'event_time': '10:00 AM',
                'venue': 'Computer Lab 3',
                'description': 'Battle Royale championship at Daksha Infinix.',
                'max_participants': 100,
                'is_group': 1,
                'min_team_size': 4,
                'max_team_size': 4,
                'banner_image': '89e73e3fb00545329bed5ddb69478ea6.webp',
                'event_fee': 400,
                'upi_id': 'admin@upi',
                'qr_code_image': 'uploads/qr_codes/c8d1eeb6e2fd420fad37edd0c7bb0baa.jpeg',
                'rules_text': 'Rule 1: Squad format (4 players per team). Mobile only, no emulators.\nRule 2: Fair play mandatory. Room ID and password will be shared 15 minutes before match start.\nRule 3: Any third-party plugins, hacks, cheats, or exploit abuse will lead to immediate disqualification.\nRule 4: The judges and organizers decision will be final and binding.',
                'faculty_name': 'Prof. Rajesh Kumar',
                'faculty_phone': '9876543210',
                'student_name': 'Akash S',
                'student_phone': '8050774071',
            },
            {
                'event_name': 'Free Fire',
                'event_type': 'Gaming',
                'event_date': '18-sep-2026',
                'event_time': '11:00 AM',
                'venue': 'Seminar Hall 1',
                'description': 'A fast-paced battle royale competition where teams compete through precision, strategy, and teamwork.',
                'max_participants': 100,
                'is_group': 1,
                'min_team_size': 4,
                'max_team_size': 4,
                'banner_image': 'freefire.jpeg',
                'event_fee': 400,
                'upi_id': 'admin@upi',
                'qr_code_image': 'uploads/qr_codes/f09529478c554e5d91ed22023082dca2.jpeg',
                'rules_text': 'Rule 1: Squad format (4 players per team). Mobile devices only. No emulators or external triggers allowed.\nRule 2: Players must belong to an affiliated institution and use their registered in-game IDs.\nRule 3: Room ID and password will be shared 15 minutes before match start.\nRule 4: Any third-party mods, hacks, scripts, or exploit abuse results in immediate forfeiture.\nRule 5: Organizers decisions on point calculation and match results are final.',
                'faculty_name': 'a',
                'faculty_phone': '1234567888',
                'student_name': 's',
                'student_phone': '123456890',
            },
            {
                'event_name': 'Pencil Sketch',
                'event_type': 'Art',
                'event_date': '18-sep-2026',
                'event_time': '11:00 AM',
                'venue': 'Seminar Hall 1',
                'description': 'An individual sketching challenge celebrating observation, composition, detail, and artistic expression.',
                'max_participants': 40,
                'is_group': 0,
                'min_team_size': 1,
                'max_team_size': 1,
                'banner_image': 'pencilesketch.jpeg',
                'event_fee': 100,
                'upi_id': 'admin@upi',
                'qr_code_image': 'uploads/qr_codes/5c07f555d6444d5398d7b33273b42147.jpeg',
                'rules_text': 'Theme: Dreams of Tomorrow, A World I Wish to See, Beauty and Beast, Nature and Humanity\r\n\r\nSketch sheets will be provided.\r\n\r\nParticipants must carry all necessary materials (pencils, erasers, shading tools).\r\n\r\nArtwork must be based on the given theme.\r\n\r\nTime limit is strictly 90 minutes.\r\n\r\nCopying, tracing, mobile phones or similar aids will lead to disqualification.\r\n\r\nThe judges decision will be final and binding.',
                'faculty_name': 'cdc',
                'faculty_phone': '4321234567',
                'student_name': 's',
                'student_phone': '1234567891',
            },
            {
                'event_name': 'Get the Shield',
                'event_type': 'Technical & Strategy',
                'event_date': '18-sep-2026',
                'event_time': '11:00 AM',
                'venue': 'Seminar Hall 1',
                'description': 'A spirited general-knowledge and challenge event where participants compete for the championship shield.',
                'max_participants': 40,
                'is_group': 1,
                'min_team_size': 2,
                'max_team_size': 2,
                'banner_image': 'get_the_shield.jpeg',
                'event_fee': 200,
                'upi_id': 'admin@upi',
                'qr_code_image': 'uploads/qr_codes/2c106876e1e14a049e4bda3ab316a82b.jpeg',
                'rules_text': 'Team format: 2 participants per team.\r\n\r\nFollow contest format and multi-stage instructions announced by organizers.\r\n\r\nOutside assistance and disruptive conduct are strictly prohibited.\r\n\r\nThe judges decision will be final and binding.',
                'faculty_name': 'a',
                'faculty_phone': '4321234567',
                'student_name': 's',
                'student_phone': '1234567891',
            },
            {
                'event_name': 'Photography',
                'event_type': 'Art',
                'event_date': '18-sep-2026',
                'event_time': '11:00 AM',
                'venue': 'Seminar Hall 1',
                'description': 'Capture a compelling visual story using composition, lighting, timing, and creative perspective.',
                'max_participants': 40,
                'is_group': 0,
                'min_team_size': 1,
                'max_team_size': 1,
                'banner_image': 'Photography.jpeg',
                'event_fee': 100,
                'upi_id': 'admin@upi',
                'qr_code_image': None,
                'rules_text': 'Solo participation. Bring your own mobile phone or camera and accessories.\r\n\r\nPictures must be clicked during the competition period within the institution campus.\r\n\r\nBasic color adjustments and cropping are allowed; heavy manipulation, editing, or AI generation is strictly prohibited.\r\n\r\nAll submitted work must be original with EXIF data intact.\r\n\r\nJudging considers composition, storytelling, timing, and technical quality.\r\n\r\nThe judges decision will be final and binding.',
                'faculty_name': 'cdc',
                'faculty_phone': '4321234567',
                'student_name': 's',
                'student_phone': '1234567891',
            },
            {
                'event_name': 'Content Creator',
                'event_type': 'Social Media',
                'event_date': '18-sep-2026',
                'event_time': '11:00 AM',
                'venue': 'Seminar Hall 1',
                'description': 'Create an engaging short-form piece that combines originality, storytelling, visual quality, and audience appeal.',
                'max_participants': 40,
                'is_group': 0,
                'min_team_size': 1,
                'max_team_size': 1,
                'banner_image': 'contentcreator.jpeg',
                'event_fee': 100,
                'upi_id': 'admin@upi',
                'qr_code_image': None,
                'rules_text': 'Theme: Create an engaging 30-90 second reel or short video based on the campus fest energy.\r\n\r\nParticipants must carry all required equipment (camera, mobile phone, tripod, laptop, etc.).\r\n\r\nContent must be original and created during the event window.\r\n\r\nRoyalty-free music and assets are permitted; copyright infringement is prohibited.\r\n\r\nContent must be respectful and suitable for a college audience.\r\n\r\nJudging considers originality, clarity, production quality, and audience impact.\r\n\r\nThe judges decision will be final and binding.',
                'faculty_name': 'cdc',
                'faculty_phone': '4321234567',
                'student_name': 's',
                'student_phone': '1234567891',
            },
            {
                'event_name': 'Solo Dance',
                'event_type': 'Dancing',
                'event_date': '18-sep-2026',
                'event_time': '11:00 AM',
                'venue': 'Seminar Hall 1',
                'description': 'Showcase expressive choreography, rhythm, stage presence, and musical interpretation in a solo routine.',
                'max_participants': 40,
                'is_group': 0,
                'min_team_size': 1,
                'max_team_size': 1,
                'banner_image': 'solo_dance.jpeg',
                'event_fee': 100,
                'upi_id': 'admin@upi',
                'qr_code_image': None,
                'rules_text': 'Time Limit: 3 + 1 min\r\n\r\nParticipants must submit audio tracks in advance to the sound desk.\r\n\r\nAny dance style is permitted (Classical, Folk, Contemporary, Western, Bollywood).\r\n\r\nVulgarity in costume, song lyrics, or dance movements is strictly prohibited.\r\n\r\nJudging is based on choreography, rhythm, technique, facial expression, and stage presence.\r\n\r\nThe judges decision will be final and binding.',
                'faculty_name': 'cdc',
                'faculty_phone': '4321234567',
                'student_name': 's',
                'student_phone': '1234567891',
            },
            {
                'event_name': 'Group Dance',
                'event_type': 'Dancing',
                'event_date': '18-sep-2026',
                'event_time': '11:00 AM',
                'venue': 'Seminar Hall 1',
                'description': 'A high-energy team dance showcase judged on synchrony, formation complexity, energy, and style.',
                'max_participants': 40,
                'is_group': 1,
                'min_team_size': 6,
                'max_team_size': 8,
                'banner_image': 'Group_Dance.jpeg',
                'event_fee': 500,
                'upi_id': 'admin@upi',
                'qr_code_image': None,
                'rules_text': 'Time Limit: 4 + 1 min\r\n\r\nTeam size: 6 to 8 members. All group members must belong to an affiliated institution.\r\n\r\nAudio tracks must be submitted in MP3 format before the event.\r\n\r\nProps are allowed with prior notification to organizers.\r\n\r\nVulgarity in costume or choreography is strictly prohibited.\r\n\r\nJudging criteria include synchronisation, choreography, costumes, energy, and overall impact.\r\n\r\nThe judges decision will be final and binding.',
                'faculty_name': 'cdc',
                'faculty_phone': '4321234567',
                'student_name': 's',
                'student_phone': '1234567891',
            },
            {
                'event_name': 'Beat Boxing',
                'event_type': 'Art',
                'event_date': '18-sep-2026',
                'event_time': '11:00 AM',
                'venue': 'Seminar Hall 1',
                'description': 'Vocal percussion battles celebrating musicality, technical precision, groove, and crowd energy.',
                'max_participants': 40,
                'is_group': 0,
                'min_team_size': 1,
                'max_team_size': 1,
                'banner_image': 'beatboxing.jpeg',
                'event_fee': 150,
                'upi_id': 'admin@upi',
                'qr_code_image': None,
                'rules_text': 'Time limit/Format: Round 1: 1 min, Round 2: 1 vs 1 face-off, 2 min each.\r\n\r\nAll sounds must be created live with mouth and microphone. No instruments, backing tracks, or loopers.\r\n\r\nNo profanity, offensive gestures, or personal attacks.\r\n\r\nScoring is based on clarity, complexity, musicality, rhythm, and stage presence.\r\n\r\nThe judges decision will be final and binding.',
                'faculty_name': 'a',
                'faculty_phone': '4321234567',
                'student_name': 's',
                'student_phone': '1234567891',
            },
            {
                'event_name': 'Face Painting',
                'event_type': 'Art',
                'event_date': '18-sep-2026',
                'event_time': '11:00 AM',
                'venue': 'Seminar Hall 1',
                'description': 'Transform a face into an expressive artwork through concept, technique, color, and finishing detail.',
                'max_participants': 30,
                'is_group': 1,
                'min_team_size': 2,
                'max_team_size': 2,
                'banner_image': 'facepanting.jpeg',
                'event_fee': 100,
                'upi_id': 'admin@upi',
                'qr_code_image': None,
                'rules_text': 'Team of 2 (one artist and one model). Time limit: 60 minutes.\r\n\r\nTheme: Indian Folk and Tribal Art, Under the Sea, Wild and Wonderful\r\n\r\nBring all essential materials. Use skin-safe, non-toxic, and hypoallergenic face paints.\r\n\r\nNo permanent markers, industrial paints, chemicals, or harmful substances.\r\n\r\nThe model must remain comfortable throughout.\r\n\r\nThe judges decision will be final and binding.',
                'faculty_name': 'a',
                'faculty_phone': '4321234567',
                'student_name': 's',
                'student_phone': '1234567891',
            },
            {
                'event_name': 'Tech Quiz',
                'event_type': 'Technical Quiz & Logic Duel',
                'event_date': '18-sep-2026',
                'event_time': '11:00 AM',
                'venue': 'Seminar Hall 1',
                'description': 'A rapid-fire technology quiz covering computing fundamentals, innovation, logic, and current digital trends.',
                'max_participants': 40,
                'is_group': 1,
                'min_team_size': 2,
                'max_team_size': 2,
                'banner_image': 'Tech_Quiz.jpeg',
                'event_fee': 200,
                'upi_id': 'admin@upi',
                'qr_code_image': None,
                'rules_text': 'Team of 2 participants.\r\n\r\nQuiz covers computing fundamentals, tech innovation, logic puzzles, and digital trends.\r\n\r\nMobile phones, internet access, and outside assistance are strictly prohibited.\r\n\r\nTies will be resolved through a rapid-fire tie-breaker.\r\n\r\nThe judges decision will be final and binding.',
                'faculty_name': 'a',
                'faculty_phone': '4321234567',
                'student_name': 's',
                'student_phone': '1234567891',
            },
            {
                'event_name': 'Mad Adds',
                'event_type': 'Art',
                'event_date': '18-sep-2026',
                'event_time': '11:00 AM',
                'venue': 'Seminar Hall 1',
                'description': 'Develop and perform a memorable advertisement that combines a clear message, creativity, humor, and teamwork.',
                'max_participants': 30,
                'is_group': 1,
                'min_team_size': 4,
                'max_team_size': 8,
                'banner_image': 'mad_adds.jpeg',
                'event_fee': 500,
                'upi_id': 'admin@upi',
                'qr_code_image': None,
                'rules_text': 'Time Limit/Format: 3 + 1 min\r\n\r\nTeam size: 4 to 8 members.\r\n\r\nTeams may use dialogue, acting, music, dance and comedy.\r\n\r\nAdvertisement should clearly promote the assigned product (real or fictional).\r\n\r\nNo offensive personal comments, brand defamation, vulgar, political, or religious content.\r\n\r\nUnsafe props are prohibited.\r\n\r\nThe judges decision will be final and binding.',
                'faculty_name': 'a',
                'faculty_phone': '4321234567',
                'student_name': 's',
                'student_phone': '1234567891',
            },
            {
                'event_name': 'Mono Acting',
                'event_type': 'Art',
                'event_date': '18-sep-2026',
                'event_time': '11:00 AM',
                'venue': 'Seminar Hall 1',
                'description': 'A solo acting performance focused on character, voice, body language, expression, and storytelling.',
                'max_participants': 30,
                'is_group': 0,
                'min_team_size': 1,
                'max_team_size': 1,
                'banner_image': 'monoacting.jpeg',
                'event_fee': 100,
                'upi_id': 'admin@upi',
                'qr_code_image': None,
                'rules_text': 'Theme: Mythology Characters or Social Themes (acting in Kannada or English language)\r\n\r\nTime limit: 3 + 1 min\r\n\r\nPerformance should be an original act or well-prepared portrayal.\r\n\r\nPerform individually without support of other actors.\r\n\r\nVulgar or inappropriate language/content is prohibited.\r\n\r\nBackground music or sound effects may be used if arranged in advance.\r\n\r\nThe judges decision will be final and binding.',
                'faculty_name': 'cdc',
                'faculty_phone': '4321234567',
                'student_name': 's',
                'student_phone': '1234567891',
            },
            {
                'event_name': 'Ramp Walk',
                'event_type': 'Cultural & Performance',
                'event_date': '18-sep-2026',
                'event_time': '11:00 AM',
                'venue': 'Seminar Hall 1',
                'description': 'A confident fashion showcase judged on presentation, creativity, stage presence, and styling.',
                'max_participants': 40,
                'is_group': 1,
                'min_team_size': 6,
                'max_team_size': 8,
                'banner_image': '47a83de9ff4c4712b65dd41197a65d40.jpeg',
                'event_fee': 500,
                'upi_id': 'test@upi',
                'qr_code_image': None,
                'rules_text': 'Theme: Marine Life, Celestial Dreams, Seasons of Style\r\n\r\nTeam size: 6 to 8 members. Time limit: 6 + 2 minutes.\r\n\r\nCostumes and movements should be decent, creative, and appropriate.\r\n\r\nCoordination and presentation based on creativity and overall performance.\r\n\r\nNo dangerous props; safe props may be used.\r\n\r\nVulgar or inappropriate songs, movements or costumes are strictly prohibited.\r\n\r\nThe judges decision will be final and binding.',
                'faculty_name': 'a',
                'faculty_phone': '4321234567',
                'student_name': 's',
                'student_phone': '1234567891',
            }
        ]

        # Seed or ensure all 14 official local events exist
        existing_rows = run_query("SELECT event_name FROM events")
        existing_names = {r['event_name'] for r in (existing_rows or [])}
        for ev in official_events:
            if ev['event_name'] not in existing_names:
                run_exec(
                    """
                    INSERT INTO events (
                        event_name, event_type, event_date, event_time, venue, description,
                        max_participants, is_group, min_team_size, max_team_size,
                        banner_image, event_fee, upi_id, qr_code_image, rules_text,
                        faculty_name, faculty_phone, student_name, student_phone
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    """,
                    (
                        ev['event_name'], ev['event_type'], ev['event_date'], ev['event_time'], ev['venue'], ev['description'],
                        ev['max_participants'], ev['is_group'], ev['min_team_size'], ev['max_team_size'],
                        ev['banner_image'], ev['event_fee'], ev['upi_id'], ev['qr_code_image'], ev['rules_text'],
                        ev['faculty_name'], ev['faculty_phone'], ev['student_name'], ev['student_phone']
                    )
                )
                print(f"[DB Seed] Created official event: {ev['event_name']} (Group: {ev['is_group']})")
            else:
                run_exec(
                    """
                    UPDATE events SET
                        event_type = %s, is_group = %s, min_team_size = %s, max_team_size = %s,
                        event_fee = %s, description = %s, rules_text = %s
                    WHERE event_name = %s
                    """,
                    (
                        ev['event_type'], ev['is_group'], ev['min_team_size'], ev['max_team_size'],
                        ev['event_fee'], ev['description'], ev['rules_text'], ev['event_name']
                    )
                )

        if not is_sqlite:
            conn.commit()
        _DB_INITIALIZED = True
    finally:
        cursor.close()
        release_db_connection(conn)

    # Seed Sample Participants if none exist
    # (Disabled per user request to start with a completely clean slate)
    pass

if __name__ == '__main__':
    init_db()
    print("Database initialization complete.")
