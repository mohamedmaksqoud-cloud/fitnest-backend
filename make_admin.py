"""Promote an existing user to admin:  python make_admin.py user@example.com"""

import sys

from app.database import SessionLocal
from app.models import User

if len(sys.argv) != 2:
    print("Usage: python make_admin.py user@example.com")
    sys.exit(1)

email = sys.argv[1].strip().lower()
db = SessionLocal()
try:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        print(f"No user found with email {email}")
        sys.exit(1)
    user.is_admin = True
    db.commit()
    print(f"{email} is now an admin.")
finally:
    db.close()
