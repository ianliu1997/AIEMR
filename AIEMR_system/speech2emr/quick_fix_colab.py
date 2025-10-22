# Quick Fix for Google Colab: Add adapter_key column to patient_record table
# Copy and paste this entire code block into a Colab cell and run it

import sqlite3
from pathlib import Path

def quick_fix_database():
    """Add adapter_key column to patient_record table"""
    
    db_path = "patient.db"
    
    print("=" * 70)
    print("🔧 Quick Fix: Adding adapter_key column to patient_record table")
    print("=" * 70)
    
    if not Path(db_path).exists():
        print("✅ Database doesn't exist yet - will be created with correct schema")
        return True
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='patient_record'")
        if not cursor.fetchone():
            print("✅ patient_record table doesn't exist - will be created with correct schema")
            conn.close()
            return True
        
        # Check if column exists
        cursor.execute("PRAGMA table_info(patient_record)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'adapter_key' in columns:
            print("✅ adapter_key column already exists - no fix needed")
            conn.close()
            return True
        
        # Add the column
        print("📝 Adding adapter_key column...")
        cursor.execute("ALTER TABLE patient_record ADD COLUMN adapter_key TEXT")
        conn.commit()
        
        # Verify
        cursor.execute("PRAGMA table_info(patient_record)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'adapter_key' in columns:
            print("✅ Successfully added adapter_key column!")
            
            # Show record count
            cursor.execute("SELECT COUNT(*) FROM patient_record")
            count = cursor.fetchone()[0]
            print(f"📊 Total records: {count}")
            
            if count > 0:
                print("ℹ️  Existing records will have adapter_key=NULL (this is fine)")
        
        conn.close()
        print("\n" + "=" * 70)
        print("✅ FIX COMPLETE! You can now restart your server.")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

# Run the fix
if __name__ == "__main__":
    quick_fix_database()
