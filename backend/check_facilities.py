import asyncio

from sqlalchemy import select

from app.database.session import AsyncSessionLocal
from app.models.parking_facility import ParkingFacility


async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                ParkingFacility.id,
                ParkingFacility.code,
                ParkingFacility.name,
                ParkingFacility.facility_type,
            ).order_by(
                ParkingFacility.id
            )
        )

        rows = result.all()

        print()
        print("=" * 80)
        print("SMARTPARK AI - PARKING FACILITY MASTER DATA")
        print("=" * 80)

        print(f"Total facilities: {len(rows)}")
        print()

        for row in rows:
            print(
                f"id={row.id} | "
                f"code={row.code} | "
                f"name={row.name} | "
                f"type={row.facility_type}"
            )


if __name__ == "__main__":
    asyncio.run(main())
