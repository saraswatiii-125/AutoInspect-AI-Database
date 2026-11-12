import os
import sys
from pathlib import Path

# Ensure vendor packages are in path
vendor_path = Path(__file__).resolve().parent.parent / "vendor"
if vendor_path.exists() and str(vendor_path) not in sys.path:
    sys.path.insert(0, str(vendor_path))

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

db_url = settings.DATABASE_URL
parsed_url = make_url(db_url)

# Supabase Transaction Pooler (Supavisor port 6543) does not preserve connection-level
# server-side prepared statements across pooled transactions in psycopg 3.
disable_prepared_env = os.getenv("DB_DISABLE_PREPARED_STATEMENTS", "").strip().lower()
use_transaction_pooler_mode = (
    parsed_url.drivername.startswith("postgresql+psycopg")
    and not parsed_url.drivername.startswith("postgresql+psycopg2")
    and (
        parsed_url.port == 6543
        or disable_prepared_env in ("true", "1", "yes")
    )
)

connect_args = {"prepare_threshold": None} if use_transaction_pooler_mode else {}

# Configure PostgreSQL engine with connection pooling optimized for Supabase poolers
engine = create_engine(
    db_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=300,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Dependency yielding database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
