"""
Initialize database with default admin user
"""
from database import SessionLocal, engine, Base
from models import User, UserRole
from auth import get_password_hash

def init_db():
    """Create tables and default admin user"""
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # Check if admin user exists
        admin = db.query(User).filter(User.email == "admin@pharmacy.com").first()
        
        if not admin:
            # Create default admin user
            admin = User(
                email="admin@pharmacy.com",
                full_name="Admin User",
                role=UserRole.ADMIN,
                hashed_password=get_password_hash("admin123"),
                is_active=True
            )
            db.add(admin)
            db.commit()
            print("Default admin user created:")
            print("  Email: admin@pharmacy.com")
            print("  Password: admin123")
        else:
            print("Admin user already exists")
        
        # Create sample pharmacy manager
        manager = db.query(User).filter(User.email == "manager@pharmacy.com").first()
        if not manager:
            manager = User(
                email="manager@pharmacy.com",
                full_name="Pharmacy Manager",
                role=UserRole.PHARMACY_MANAGER,
                hashed_password=get_password_hash("manager123"),
                is_active=True
            )
            db.add(manager)
            db.commit()
            print("Default manager user created:")
            print("  Email: manager@pharmacy.com")
            print("  Password: manager123")
        
    except Exception as e:
        print(f"Error initializing database: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    print("Done!")


