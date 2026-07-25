from __future__ import annotations

import asyncio
from datetime import time
from decimal import Decimal

from sqlalchemy import select

from app.database.session import AsyncSessionLocal
from app.models.enums import FacilityType
from app.models.parking_facility import ParkingFacility


PARKING_FACILITIES = [
    {
        "name": "Two Rivers Mall",
        "code": "TWOR001",
        "facility_type": FacilityType.SHOPPING_MALL,
        "description": "Main shopping mall parking.",
        "country": "Kenya",
        "county": "Nairobi",
        "city": "Nairobi",
        "address": "Limuru Road",
        "postal_code": "00100",
        "latitude": Decimal("-1.210490"),
        "longitude": Decimal("36.802871"),
    },
    {
        "name": "Sarit Centre",
        "code": "SAR001",
        "facility_type": FacilityType.SHOPPING_MALL,
        "description": "Shopping mall parking.",
        "country": "Kenya",
        "county": "Nairobi",
        "city": "Nairobi",
        "address": "Westlands",
        "postal_code": "00100",
        "latitude": Decimal("-1.268037"),
        "longitude": Decimal("36.804532"),
    },
    {
        "name": "Global Trade Centre",
        "code": "GTC001",
        "facility_type": FacilityType.OFFICE,
        "description": "Office tower parking.",
        "country": "Kenya",
        "county": "Nairobi",
        "city": "Nairobi",
        "address": "Westlands",
        "postal_code": "00100",
        "latitude": Decimal("-1.261443"),
        "longitude": Decimal("36.804887"),
    },
    {
        "name": "Family Bank Headquarters",
        "code": "FBL001",
        "facility_type": FacilityType.OFFICE,
        "description": "Head office staff parking.",
        "country": "Kenya",
        "county": "Nairobi",
        "city": "Nairobi",
        "address": "Muindi Mbingu Street",
        "postal_code": "00100",
        "latitude": Decimal("-1.284102"),
        "longitude": Decimal("36.821935"),
    },
    {
        "name": "University of Nairobi",
        "code": "UON001",
        "facility_type": FacilityType.UNIVERSITY,
        "description": "Main campus parking.",
        "country": "Kenya",
        "county": "Nairobi",
        "city": "Nairobi",
        "address": "University Way",
        "postal_code": "00100",
        "latitude": Decimal("-1.279452"),
        "longitude": Decimal("36.816128"),
    },
    {
        "name": "JKIA Terminal 1A",
        "code": "JKIA01",
        "facility_type": FacilityType.AIRPORT,
        "description": "Passenger parking.",
        "country": "Kenya",
        "county": "Nairobi",
        "city": "Nairobi",
        "address": "Jomo Kenyatta International Airport",
        "postal_code": "00501",
        "latitude": Decimal("-1.319167"),
        "longitude": Decimal("36.927500"),
    },
    {
        "name": "Wilson Airport",
        "code": "WIL001",
        "facility_type": FacilityType.AIRPORT,
        "description": "Domestic airport parking.",
        "country": "Kenya",
        "county": "Nairobi",
        "city": "Nairobi",
        "address": "Langata Road",
        "postal_code": "00100",
        "latitude": Decimal("-1.321722"),
        "longitude": Decimal("36.814833"),
    },
    {
        "name": "Kenyatta National Hospital",
        "code": "KNH001",
        "facility_type": FacilityType.HOSPITAL,
        "description": "Hospital visitor parking.",
        "country": "Kenya",
        "county": "Nairobi",
        "city": "Nairobi",
        "address": "Hospital Road",
        "postal_code": "00202",
        "latitude": Decimal("-1.301683"),
        "longitude": Decimal("36.807346"),
    },
    {
        "name": "Villa Rosa Kempinski",
        "code": "KEM001",
        "facility_type": FacilityType.HOTEL,
        "description": "Hotel guest parking.",
        "country": "Kenya",
        "county": "Nairobi",
        "city": "Nairobi",
        "address": "Chiromo Road",
        "postal_code": "00100",
        "latitude": Decimal("-1.268843"),
        "longitude": Decimal("36.811576"),
    },
    {
        "name": "KICC Parking",
        "code": "KICC01",
        "facility_type": FacilityType.PUBLIC,
        "description": "Public event parking.",
        "country": "Kenya",
        "county": "Nairobi",
        "city": "Nairobi",
        "address": "Harambee Avenue",
        "postal_code": "00100",
        "latitude": Decimal("-1.288743"),
        "longitude": Decimal("36.821946"),
    },
    {
        "name": "Nakuru CBD Parking",
        "code": "NKR001",
        "facility_type": FacilityType.PUBLIC,
        "description": "Municipal parking.",
        "country": "Kenya",
        "county": "Nakuru",
        "city": "Nakuru",
        "address": "Kenyatta Avenue",
        "postal_code": "20100",
        "latitude": Decimal("-0.303099"),
        "longitude": Decimal("36.080025"),
    },
    {
        "name": "Nyali Centre",
        "code": "MSA001",
        "facility_type": FacilityType.SHOPPING_MALL,
        "description": "Shopping mall parking.",
        "country": "Kenya",
        "county": "Mombasa",
        "city": "Mombasa",
        "address": "Links Road",
        "postal_code": "80100",
        "latitude": Decimal("-4.043477"),
        "longitude": Decimal("39.668206"),
    },
    {
        "name": "Mega City Mall",
        "code": "KSM001",
        "facility_type": FacilityType.SHOPPING_MALL,
        "description": "Shopping mall parking.",
        "country": "Kenya",
        "county": "Kisumu",
        "city": "Kisumu",
        "address": "Kisumu-Kakamega Road",
        "postal_code": "40100",
        "latitude": Decimal("-0.074065"),
        "longitude": Decimal("34.768018"),
    },
    {
        "name": "Eldoret CBD Parking",
        "code": "ELD001",
        "facility_type": FacilityType.PUBLIC,
        "description": "Municipal parking.",
        "country": "Kenya",
        "county": "Uasin Gishu",
        "city": "Eldoret",
        "address": "Uganda Road",
        "postal_code": "30100",
        "latitude": Decimal("0.520360"),
        "longitude": Decimal("35.269779"),
    },
    {
        "name": "Garden City Mall",
        "code": "GCM001",
        "facility_type": FacilityType.SHOPPING_MALL,
        "description": "Shopping mall parking.",
        "country": "Kenya",
        "county": "Nairobi",
        "city": "Nairobi",
        "address": "Thika Road",
        "postal_code": "00100",
        "latitude": Decimal("-1.232164"),
        "longitude": Decimal("36.878560"),
    },
]


async def seed_parking_facilities() -> None:
    """
    Seed development parking facilities.

    The script is idempotent:
    facilities with an existing code are skipped.
    """

    async with AsyncSessionLocal() as session:

        inserted = 0
        skipped = 0

        for facility_data in PARKING_FACILITIES:

            result = await session.execute(
                select(ParkingFacility).where(
                    ParkingFacility.code == facility_data["code"]
                )
            )

            existing = result.scalar_one_or_none()

            if existing:
                skipped += 1
                print(f"✓ Skipped: {facility_data['name']}")
                continue

            facility = ParkingFacility(
                **facility_data,
                timezone="Africa/Nairobi",
                opening_time=time(6, 0),
                closing_time=time(23, 0),
                is_active=True,
            )

            session.add(facility)

            inserted += 1
            print(f"+ Added: {facility.name}")

        await session.commit()

        print("\n====================================")
        print("Parking Facility Seeding Complete")
        print("====================================")
        print(f"Inserted : {inserted}")
        print(f"Skipped  : {skipped}")
        print("====================================")


if __name__ == "__main__":
    asyncio.run(seed_parking_facilities())