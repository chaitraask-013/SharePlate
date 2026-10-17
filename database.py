import sqlite3

DATABASE = "shareplate.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db_connection()

    # User accounts
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (
                role IN ('donor', 'recipient')
            ),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Food donations
    conn.execute("""
        CREATE TABLE IF NOT EXISTS donations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_name TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity TEXT NOT NULL,
            donor_name TEXT NOT NULL,
            location TEXT NOT NULL,
            deadline TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'Available',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Add columns safely to existing databases
    columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(donations)"
        ).fetchall()
    }

    if "donor_id" not in columns:
        conn.execute("""
            ALTER TABLE donations
            ADD COLUMN donor_id INTEGER REFERENCES users(id)
        """)

    if "image_path" not in columns:
        conn.execute("""
            ALTER TABLE donations
            ADD COLUMN image_path TEXT
        """)

    # Food requests from recipients
    conn.execute("""
        CREATE TABLE IF NOT EXISTS donation_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            donation_id INTEGER NOT NULL
                REFERENCES donations(id) ON DELETE CASCADE,

            recipient_id INTEGER NOT NULL
                REFERENCES users(id) ON DELETE CASCADE,

            status TEXT NOT NULL DEFAULT 'Requested'
                CHECK (
                    status IN (
                        'Requested',
                        'Approved',
                        'Rejected',
                        'Collected'
                    )
                ),

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE (donation_id, recipient_id)
        )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("SharePlate database is ready!")
