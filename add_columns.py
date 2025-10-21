import sqlite3

# Connect to database
conn = sqlite3.connect('attendance.db')
cursor = conn.cursor()

# Add columns to user table
try:
    cursor.execute("ALTER TABLE user ADD COLUMN attendly_id VARCHAR(50)")
    cursor.execute("ALTER TABLE user ADD COLUMN phone VARCHAR(20)")
    cursor.execute("ALTER TABLE user ADD COLUMN avatar VARCHAR(255)")
    cursor.execute("ALTER TABLE user ADD COLUMN location VARCHAR(100)")
    cursor.execute("ALTER TABLE user ADD COLUMN biography TEXT")
    cursor.execute("ALTER TABLE user ADD COLUMN branch VARCHAR(100)")
    cursor.execute("ALTER TABLE user ADD COLUMN designation VARCHAR(100)")
    cursor.execute("ALTER TABLE user ADD COLUMN department VARCHAR(100)")
    cursor.execute("ALTER TABLE user ADD COLUMN experience VARCHAR(50)")
    
    conn.commit()
    print("✅ Successfully added all columns to user table!")
except Exception as e:
    print(f"Error: {e}")
    print("(Some columns may already exist)")
finally:
    conn.close()