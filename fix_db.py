import sqlite3
import os

# Path to your database
db_path = 'attendance.db'

# Check if database exists
if not os.path.exists(db_path):
    print(f"Database {db_path} not found!")
    exit(1)

try:
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("Connected to database successfully!")
    
    # Check if columns already exist
    cursor.execute("PRAGMA table_info(student)")
    student_columns = [column[1] for column in cursor.fetchall()]
    
    cursor.execute("PRAGMA table_info(attendance)")
    attendance_columns = [column[1] for column in cursor.fetchall()]
    
    print("Current student columns:", student_columns)
    print("Current attendance columns:", attendance_columns)
    
    # Add subject column to student table if it doesn't exist
    if 'subject' not in student_columns:
        cursor.execute("ALTER TABLE student ADD COLUMN subject VARCHAR(100) DEFAULT 'Computer Science'")
        print("Added 'subject' column to student table")
    else:
        print("'subject' column already exists in student table")
    
    # Add subject column to attendance table if it doesn't exist
    if 'subject' not in attendance_columns:
        cursor.execute("ALTER TABLE attendance ADD COLUMN subject VARCHAR(100) DEFAULT 'Computer Science'")
        print("Added 'subject' column to attendance table")
    else:
        print("'subject' column already exists in attendance table")
    
    # Commit changes
    conn.commit()
    print("Database updated successfully!")
    
    # Verify the changes
    cursor.execute("PRAGMA table_info(student)")
    student_columns = [column[1] for column in cursor.fetchall()]
    
    cursor.execute("PRAGMA table_info(attendance)")
    attendance_columns = [column[1] for column in cursor.fetchall()]
    
    print("Updated student columns:", student_columns)
    print("Updated attendance columns:", attendance_columns)
    
except sqlite3.Error as e:
    print(f"Database error: {e}")
except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()
        print("Database connection closed.")