"""JWT authentication with PBKDF2 password hashing and role guards."""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    iterations = 480_000
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iterations)
    return f'pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}'


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, count, salt, expected = password_hash.split('$')
        if algorithm != 'pbkdf2_sha256':
            return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(count))
        return hmac.compare_digest(digest, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def create_token(user: User) -> str:
    expiry = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expires_minutes)
    return jwt.encode({'sub': str(user.id), 'exp': expiry}, settings.jwt_secret, algorithm='HS256')


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials:
        raise HTTPException(401, 'Authentication required', headers={'WWW-Authenticate': 'Bearer'})
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=['HS256'])
        user = db.get(User, int(payload['sub']))
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(401, 'Invalid or expired token') from None
    if not user:
        raise HTTPException(401, 'Account no longer exists')
    return user


def require_roles(*roles):
    def guard(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, 'Insufficient permissions')
        return user
    return guard
