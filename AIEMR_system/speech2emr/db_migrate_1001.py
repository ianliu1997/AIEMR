#!/usr/bin/env python3
"""
Database Migration Script: Add adapter_key column to patient_record table
Run this script to update your existing database with the new adapter_key field.
"""

import sqlite3
from pathlib import Path
import sys

def migrate_database(db_path: str = "patient.db"):
    """Add adapter_key column to patient_record table if it doesn't exist"""
    
    print(f"🔍 Checking database: {db_path}")
    
    if not Path(db_path).exists():
        print(f"✅ Database doesn't exist yet - will be created with correct schema on first run")
        return True
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if patient_record table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='patient_record'
        """)
        
        if not cursor.fetchone():
            print("✅ patient_record table doesn't exist - will be created with correct schema")
            conn.close()
            return True
        
        # Check if adapter_key column exists
        cursor.execute("PRAGMA table_info(patient_record)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'adapter_key' in columns:
            print("✅ adapter_key column already exists - no migration needed")
            conn.close()
            return True
        
        print("📝 Adding adapter_key column to patient_record table...")
        
        # SQLite doesn't support ALTER TABLE ADD COLUMN with all constraints
        # So we add it as a simple nullable column
        cursor.execute("""
            ALTER TABLE patient_record 
            ADD COLUMN adapter_key TEXT
        """)
        
        conn.commit()
        print("✅ Successfully added adapter_key column")
        
        # Verify the change
        cursor.execute("PRAGMA table_info(patient_record)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'adapter_key' in columns:
            print("✅ Verification passed - adapter_key column exists")
            
            # Show column list
            print("\n📊 Current patient_record columns:")
            for col in columns:
                print(f"   - {col}")
            
            # Show record count
            cursor.execute("SELECT COUNT(*) FROM patient_record")
            count = cursor.fetchone()[0]
            print(f"\n📈 Total records in table: {count}")
            
            if count > 0:
                print("ℹ️  Note: Existing records will have adapter_key=NULL")
                print("   You can manually update them if needed:")
                print("   UPDATE patient_record SET adapter_key='model_outputs_seg_MedicalHistory' WHERE adapter_key IS NULL;")
        else:
            print("❌ Verification failed - adapter_key column not found")
            conn.close()
            return False
        
        conn.close()
        print("\n✅ Migration completed successfully!")
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    # Check for custom database path
    db_path = sys.argv[1] if len(sys.argv) > 1 else "patient.db"
    
    print("=" * 60)
    print("Database Migration: Add adapter_key Column")
    print("=" * 60)
    print()
    
    success = migrate_database(db_path)
    
    print()
    print("=" * 60)
    
    if success:
        print("✅ Migration completed successfully!")
        print("\nYou can now restart your server and upload audio files.")
        sys.exit(0)
    else:
        print("❌ Migration failed!")
        print("\nPlease check the errors above and try again.")
        sys.exit(1)
