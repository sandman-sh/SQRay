"""
Test fixture generator for SQRay.
Creates sample SQLite databases to test:
- Single-page simple databases
- Deep multi-level B-Tree databases with thousands of rows (forcing page splits into interior/leaf nodes)
- Indexed databases with multiple tables and secondary indexes
- WAL-mode databases with uncheckpointed write-ahead log frames
"""
import os
import sqlite3
import random
import struct

def create_sample_simple(filename="demo.db"):
    if os.path.exists(filename):
        os.remove(filename)
    conn = sqlite3.connect(filename)
    cursor = conn.cursor()
    cursor.execute("PRAGMA page_size = 4096;")
    cursor.execute("PRAGMA user_version = 42;")
    cursor.execute("PRAGMA application_id = 0x53515259;") # 'SQRY'
    cursor.execute("""
        CREATE TABLE items (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL,
            in_stock INTEGER
        );
    """)
    items = [
        (1, "Vintage Camera", 149.99, 1),
        (2, "Mechanical Keyboard", 89.50, 1),
        (3, "Noise Cancelling Headphones", 249.00, 0),
        (4, "Desk Mat (Midnight Blue)", 29.95, 1),
        (5, "USB-C Hub Multiport", 45.00, 1),
    ]
    cursor.executemany("INSERT INTO items VALUES (?, ?, ?, ?)", items)
    conn.commit()
    conn.close()
    print(f"[+] Created {filename} ({os.path.getsize(filename)} bytes)")

def create_sample_btree_deep(filename="btree.db"):
    """Creates a database with enough rows and text payload to create multi-level interior and leaf B-Tree pages."""
    if os.path.exists(filename):
        os.remove(filename)
    conn = sqlite3.connect(filename)
    cursor = conn.cursor()
    cursor.execute("PRAGMA page_size = 1024;") # Smaller page size forces more pages & interior splits
    cursor.execute("""
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            email TEXT NOT NULL,
            bio TEXT,
            score INTEGER
        );
    """)
    cursor.execute("CREATE INDEX idx_customers_email ON customers(email);")
    cursor.execute("CREATE INDEX idx_customers_score ON customers(score);")

    # Insert 1,500 records with medium bio payload
    rows = []
    for i in range(1, 1501):
        username = f"user_{i:04d}"
        email = f"user_{i:04d}@example.com"
        bio = f"Developer profile #{i}: specializing in distributed systems, SQLite internals, and high performance binary decoders. Key reference: {i*37}."
        score = random.randint(100, 9999)
        rows.append((i, username, email, bio, score))
    
    cursor.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()
    print(f"[+] Created {filename} ({os.path.getsize(filename)} bytes)")

def create_sample_wal(filename="wal.db"):
    """Creates a database in WAL mode and leaves uncheckpointed frames in wal.db-wal."""
    wal_file = f"{filename}-wal"
    shm_file = f"{filename}-shm"
    for f in (filename, wal_file, shm_file):
        if os.path.exists(f):
            os.remove(f)

    conn = sqlite3.connect(filename)
    cursor = conn.cursor()
    cursor.execute("PRAGMA page_size = 4096;")
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA wal_autocheckpoint = 0;")
    cursor.execute("""
        CREATE TABLE logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            level TEXT,
            message TEXT
        );
    """)
    
    # Commit first batch
    for i in range(10):
        cursor.execute("INSERT INTO logs (level, message) VALUES (?, ?)", ("INFO", f"System boot sequence step {i}"))
    conn.commit()

    # Commit second batch
    for i in range(10):
        cursor.execute("INSERT INTO logs (level, message) VALUES (?, ?)", ("WARN", f"Memory warning checkpoint {i}"))
    conn.commit()

    # Commit third batch
    for i in range(10):
        cursor.execute("INSERT INTO logs (level, message) VALUES (?, ?)", ("ERROR", f"Failed network handshake attempt {i}"))
    conn.commit()

    conn.close()

    # Build realistic WAL file with 32-byte header + multiple transaction frames
    wal_hdr = struct.pack(
        ">IIIIIIII",
        0x377f0682, # magic
        3007000,    # version
        4096,       # page_size
        1,          # checkpoint sequence
        0x1A2B3C4D, # salt1
        0x5E6F7A8B, # salt2
        0x9C8B7A65, # checksum1
        0x4321FEDC  # checksum2
    )
    
    # Read database page 1 and page 2 to use as realistic frame payloads
    with open(filename, "rb") as db_f:
        p1 = db_f.read(4096)
        p2 = db_f.read(4096)
        if len(p2) < 4096:
            p2 = p2 + b"\x00" * (4096 - len(p2))

    # Frame 1: Update to Page 2 (Append / In-progress)
    f1_hdr = struct.pack(">IIIIII", 2, 0, 0x1A2B3C4D, 0x5E6F7A8B, 0x11112222, 0x33334444)
    # Frame 2: Update to Page 1 (Commit marker, DB size = 2 pages)
    f2_hdr = struct.pack(">IIIIII", 1, 2, 0x1A2B3C4D, 0x5E6F7A8B, 0x55556666, 0x77778888)
    # Frame 3: Another update to Page 2 (In-progress)
    f3_hdr = struct.pack(">IIIIII", 2, 0, 0x1A2B3C4D, 0x5E6F7A8B, 0x9999AAAA, 0xBBBBCCCC)
    # Frame 4: Update to Page 1 (Commit marker, DB size = 2 pages)
    f4_hdr = struct.pack(">IIIIII", 1, 2, 0x1A2B3C4D, 0x5E6F7A8B, 0xDDDDEEEE, 0xFFFF0000)

    wal_data = wal_hdr + (f1_hdr + p2) + (f2_hdr + p1) + (f3_hdr + p2) + (f4_hdr + p1)
    with open(wal_file, "wb") as f:
        f.write(wal_data)

    if os.path.exists(shm_file):
        try:
            os.remove(shm_file)
        except Exception:
            pass
    print(f"[+] Created {filename} & {wal_file} ({len(wal_data)} bytes WAL log with 4 frames)")

if __name__ == "__main__":
    create_sample_simple()
    create_sample_btree_deep()
    create_sample_wal()
