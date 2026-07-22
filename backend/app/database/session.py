from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

# Create the SQLAlchemy engine
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,  # Log SQL statements in development
)

# Create a configured session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)