#!/usr/bin/env python3
"""
Database Setup & Verification Script
Run this to fix "no such table" errors
"""

import os
import sys
import sqlite3
from pathlib import Path

def check_database():
    """Check if database exists and has tables"""
    
    # Check multiple possible paths
    possible_paths = [
        "app/labor_market.db",
        "./app/labor_market.db",
        "../app/labor_market.db",
        "labor_market.db",
    ]
    
    db_path = None
    for path in possible_paths:
        if os.path.exists(path):
            db_path = path
            print(f"✅ Found database at: {path}")
            break
    
    if not db_path:
        print("❌ Database not found!")
        print(f"\nSearching in: {os.getcwd()}")
        print(f"Files here: {os.listdir('.')}")
        return False
    
    # Check file size
    size_mb = os.path.getsize(db_path) / 1024 / 1024
    print(f"   Size: {size_mb:.1f} MB")
    
    # Check if it's a valid SQLite file
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get list of tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        if not tables:
            print("⚠️  Database is empty (no tables)")
            conn.close()
            return False
        
        print(f"✅ Database has {len(tables)} tables:")
        for table in tables:
            print(f"   - {table[0]}")
        
        # Check row counts
        try:
            cursor.execute("SELECT COUNT(*) FROM job_postings;")
            count = cursor.fetchone()[0]
            print(f"\n✅ job_postings table has {count:,} rows")
        except Exception as e:
            print(f"⚠️  Could not count rows: {e}")
        
        conn.close()
        return True
        
    except sqlite3.DatabaseError as e:
        print(f"❌ Database error: {e}")
        return False

def verify_config():
    """Verify Flask config"""
    print("\n" + "="*50)
    print("CONFIGURATION CHECK")
    print("="*50)
    
    try:
        from app.config import Config, DevelopmentConfig
        print(f"✅ Flask config loaded")
        print(f"   Database path: {Config.DATABASE_PATH}")
        
        # Verify path exists
        if os.path.exists(Config.DATABASE_PATH):
            print(f"✅ Database file exists at: {Config.DATABASE_PATH}")
            return True
        else:
            print(f"❌ Database file NOT found at: {Config.DATABASE_PATH}")
            return False
            
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return False

def fix_database_path():
    """Fix the database path"""
    print("\n" + "="*50)
    print("FIXING DATABASE PATH")
    print("="*50)
    
    # Find database
    possible_paths = [
        "app/labor_market.db",
        "./app/labor_market.db",
    ]
    
    db_path = None
    for path in possible_paths:
        if os.path.exists(path):
            db_path = os.path.abspath(path)
            break
    
    if not db_path:
        print("❌ Could not find database")
        return False
    
    print(f"✅ Found database at: {db_path}")
    
    # Update .env file
    env_path = ".env"
    env_example = ".env.example"
    
    if not os.path.exists(env_path):
        if os.path.exists(env_example):
            print(f"Creating .env from .env.example...")
            with open(env_example, 'r') as f:
                content = f.read()
            with open(env_path, 'w') as f:
                f.write(content)
            print(f"✅ Created .env")
        else:
            print("Creating new .env file...")
            content = f"""FLASK_ENV=development
DATABASE_PATH={db_path}
PORT=5001
CORS_ORIGINS=*
DEBUG=True
"""
            with open(env_path, 'w') as f:
                f.write(content)
            print(f"✅ Created .env")
    
    # Update DATABASE_PATH in .env
    with open(env_path, 'r') as f:
        lines = f.readlines()
    
    updated = False
    for i, line in enumerate(lines):
        if line.startswith('DATABASE_PATH'):
            lines[i] = f"DATABASE_PATH={db_path}\n"
            updated = True
            break
    
    if not updated:
        lines.append(f"DATABASE_PATH={db_path}\n")
    
    with open(env_path, 'w') as f:
        f.writelines(lines)
    
    print(f"✅ Updated .env with: DATABASE_PATH={db_path}")
    return True

def main():
    print("="*50)
    print("LABO DATABASE SETUP & VERIFICATION")
    print("="*50)
    
    # Check current directory
    print(f"\nCurrent directory: {os.getcwd()}")
    print(f"Files: {', '.join(os.listdir('.')[:5])}...")
    
    # Check database
    print("\n" + "="*50)
    print("DATABASE CHECK")
    print("="*50)
    db_ok = check_database()
    
    # Check config
    print("\n" + "="*50)
    print("CONFIG CHECK")
    print("="*50)
    config_ok = verify_config()
    
    # Fix if needed
    if not (db_ok and config_ok):
        print("\n⚠️  Issues detected, attempting to fix...")
        fix_database_path()
    
    # Final verification
    print("\n" + "="*50)
    print("FINAL VERIFICATION")
    print("="*50)
    
    try:
        from app.config import Config
        conn = sqlite3.connect(Config.DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM job_postings;")
        count = cursor.fetchone()[0]
        conn.close()
        
        print(f"✅ SUCCESS! Database is ready")
        print(f"✅ Found {count:,} job postings")
        print(f"\n🚀 You can now run: python main.py")
        return True
        
    except Exception as e:
        print(f"❌ Still having issues: {e}")
        print(f"\nTroubleshooting:")
        print(f"1. Make sure you're in the vakansiograph directory")
        print(f"2. Check that app/labor_market.db exists")
        print(f"3. Try: rm .env && python fix_database.py")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
