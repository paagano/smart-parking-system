from sqlalchemy import text

from app.database.session import engine


def check_database_connection() -> None:
    """
    Verifies that the application can connect to PostgreSQL.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("✅ Database connection successful!")
    except Exception as error:
        print(f"❌ Database connection failed: {error}")
        raise