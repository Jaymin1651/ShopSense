"""SQLAlchemy database session and dependency."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from app.config import settings


class Base(DeclarativeBase):
    pass


connect_args = {'check_same_thread': False} if settings.database_url.startswith('sqlite') else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)

if settings.database_url.startswith('sqlite') and ':memory:' not in settings.database_url:
    @event.listens_for(engine, 'connect')
    def _sqlite_pragmas(dbapi_connection, _record):
        """WAL lets dashboard reads run while orders are written; wait instead of failing on a lock."""
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA busy_timeout=5000')
        cursor.execute('PRAGMA synchronous=NORMAL')
        cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
