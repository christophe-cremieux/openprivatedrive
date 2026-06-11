import os
import sys
import sqlite3

basedir = os.path.abspath(os.path.dirname(__file__) + "/..")
db_path = os.path.join(basedir, "instance/app.db")
storage_path = os.path.join(basedir, "storage")

def check_orphans():
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT uuid, original_filename, storage_path FROM files WHERE is_deleted = 0")
    files = cursor.fetchall()

    orphans = []
    for uuid, name, rel_path in files:
        full_path = os.path.join(storage_path, rel_path)
        if not os.path.exists(full_path):
            orphans.append((uuid, name, full_path))

    print(f"Found {len(orphans)} orphans out of {len(files)} active files.")
    for uuid, name, path in orphans:
        print(f"Orphan: {uuid} | {name} | Missing: {path}")

    conn.close()

if __name__ == "__main__":
    check_orphans()
