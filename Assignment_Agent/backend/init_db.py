"""
Script to initialize the database with a test user
Run this after creating the database tables
"""
from sqlalchemy.orm import Session
from database import SessionLocal
from models import User
from auth import get_password_hash

def init_db():
    db: Session = SessionLocal()
    
    # Check if admin user exists
    admin_user = db.query(User).filter(User.email == "admin@example.com").first()
    
    if not admin_user:
        # Create admin user
        admin_user = User(
            email="admin@example.com",
            hashed_password=get_password_hash("admin123")
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        print("[SUCCESS] Created admin user:")
        print("  Email: admin@example.com")
        print("  Password: admin123")
    else:
        print("Admin user already exists")
    
    db.close()

if __name__ == "__main__":
    init_db()

