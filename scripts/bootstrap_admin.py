"""Explicit one-time admin account bootstrap from environment variables."""
import os
from sqlalchemy import select
from app.database import SessionLocal
from app.models import User
from app.security import hash_password


def main():
    email = os.environ.get('ADMIN_EMAIL', '').strip().lower()
    password = os.environ.get('ADMIN_PASSWORD', '')
    if not email or len(password) < 12:
        raise SystemExit('Set ADMIN_EMAIL and ADMIN_PASSWORD (12+ characters)')
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.email == email))
        if existing:
            if existing.role != 'admin':
                raise SystemExit('Configured admin email belongs to a non-admin account')
            print(f'Admin already exists: {email}; no changes made')
            return
        db.add(User(email=email, password_hash=hash_password(password), role='admin'))
        db.commit()
        print(f'Admin created: {email}')


if __name__ == '__main__':
    main()
