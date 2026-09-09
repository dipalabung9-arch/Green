import sqlite3

DB_FILE = "tea_factory_unified.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Enable foreign keys support
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS growers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            route TEXT NOT NULL,
            phone TEXT,
            advance_balance REAL DEFAULT 0.0,
            cf_balance REAL DEFAULT 0.0,
            extra_info TEXT DEFAULT '',
            created_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grower_id TEXT,
            driver_id TEXT,
            gross_weight REAL,
            category TEXT,
            water_deduction_pct REAL,
            net_payable_weight REAL,
            category_rate REAL,
            total_amount REAL,
            advance_recovery REAL DEFAULT 0.0,
            net_final_payable REAL,
            collection_date TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS field_advances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grower_id TEXT,
            driver_id TEXT,
            advance_type TEXT,
            item_name TEXT,
            quantity REAL DEFAULT 1.0,
            amount REAL,
            advance_date TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            name TEXT PRIMARY KEY,
            rate REAL DEFAULT 0.0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Safe column migration check for collections table[cite: 3]
    cursor.execute("PRAGMA table_info(collections)")
    col_names = [col[1] for col in cursor.fetchall()]
    if "timestamp" in col_names and "collection_date" not in col_names:
        cursor.execute("ALTER TABLE collections RENAME COLUMN timestamp TO collection_date")
    elif "collection_date" not in col_names:
        cursor.execute("ALTER TABLE collections ADD COLUMN collection_date TEXT")

    # Safe column migration check for field_advances table[cite: 3]
    cursor.execute("PRAGMA table_info(field_advances)")
    adv_col_names = [col[1] for col in cursor.fetchall()]
    if "timestamp" in adv_col_names and "advance_date" not in adv_col_names:
        cursor.execute("ALTER TABLE field_advances RENAME COLUMN timestamp TO advance_date")
    elif "advance_date" not in adv_col_names:
        cursor.execute("ALTER TABLE field_advances ADD COLUMN advance_date TEXT")

    # Default categories and settings[cite: 3]
    cursor.execute("INSERT OR IGNORE INTO categories (name, rate) VALUES ('A', 0.0)")
    cursor.execute("INSERT OR IGNORE INTO categories (name, rate) VALUES ('B', 0.0)")
    cursor.execute("INSERT OR IGNORE INTO categories (name, rate) VALUES ('C', 0.0)")
    
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('default_water_deduction', '0.0')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('agency_name', 'NUMA GREENLEAF ENTERPRISE')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sunday_override', 'OFF')")
    
    conn.commit()
    conn.close()

def get_setting(key, default):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else default
    except Exception:
        return default

def update_setting(key, val):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(val)))
    conn.commit()
    conn.close()