#!/usr/bin/env python3
"""Check database schema."""

import sqlite3
import os

db_path = r'c:\CCBOT\CCbot.db'

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    print("\nSearching for .db files in c:\\CCBOT...")
    for file in os.listdir(r'c:\CCBOT'):
        if file.endswith('.db'):
            print(f"  Found: {file}")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get list of tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    print(f"Database: {db_path}")
    print(f"\nTables found: {len(tables)}")
    for table in tables:
        print(f"  - {table[0]}")
    
    conn.close()
