import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    create_async_engine,
)

from app.config import settings


async def main() -> None:
    engine = create_async_engine(
        settings.TEST_DATABASE_URL,
    )

    async with engine.connect() as connection:
        database = (
            await connection.execute(
                text("SELECT current_database()")
            )
        ).scalar()

        print(
            f"TEST DATABASE: {database}"
        )

        alembic = (
            await connection.execute(
                text(
                    "SELECT version_num "
                    "FROM alembic_version"
                )
            )
        ).scalar()

        print(
            f"ALEMBIC VERSION: {alembic}"
        )

        loyalty_accounts = (
            await connection.execute(
                text(
                    "SELECT to_regclass("
                    "'public.loyalty_accounts'"
                    ")"
                )
            )
        ).scalar()

        print(
            f"LOYALTY ACCOUNTS TABLE: "
            f"{loyalty_accounts}"
        )

        loyalty_transactions = (
            await connection.execute(
                text(
                    "SELECT to_regclass("
                    "'public.loyalty_point_transactions'"
                    ")"
                )
            )
        ).scalar()

        print(
            f"LOYALTY POINT TRANSACTIONS TABLE: "
            f"{loyalty_transactions}"
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())