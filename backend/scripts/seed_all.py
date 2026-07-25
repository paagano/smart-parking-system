import asyncio

from scripts.seed_parking_facilities import seed_parking_facilities


async def main():
    print("=" * 60)
    print("SmartPark AI Development Database Seeder")
    print("=" * 60)

    print("\nSeeding Parking Facilities...")
    await seed_parking_facilities()

    print("\nDone.")

    print("=" * 60)
    print("Database seeding completed successfully.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())