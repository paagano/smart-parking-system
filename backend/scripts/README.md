# Development Scripts

This directory contains utility scripts used during the development of the **SmartPark AI** project.

These scripts are **not part of the application runtime** and should **never be executed automatically** when the application starts.

Their purpose is to simplify local development, testing, demonstrations, and database initialization.

---

# Available Scripts

| Script | Purpose |
|---------|---------|
| `seed_parking_facilities.py` | Inserts sample parking facilities into the database. |

---

# Running a Script

From the project root (backend):

```bash
python -m scripts.seed_parking_facilities
```

Alternatively:

```bash
python scripts/seed_parking_facilities.py
```

---

# Idempotent Seeding

Seed scripts are designed to be **idempotent** whenever possible.

This means:

- Existing records are detected.
- Duplicate records are not inserted.
- Scripts can be executed multiple times safely.

Example:

```
✓ Skipped: Two Rivers Mall
✓ Skipped: Sarit Centre
+ Added: Garden City Mall
```

---

# Development Only

These scripts are intended for:

- Local development
- Testing
- Demonstrations
- QA environments

They should **not** be used to populate production databases unless specifically adapted for production deployment.

---

# Future Scripts

As the SmartPark AI project grows, additional scripts will be added.

```
scripts/
│
├── README.md
├── __init__.py
├── seed_users.py
├── seed_parking_facilities.py
├── seed_parking_levels.py
├── seed_parking_bays.py
├── seed_sensors.py
├── seed_vehicles.py
├── seed_sessions.py
├── seed_reservations.py
├── seed_payments.py
└── seed_all.py
```

---

# Guidelines

When creating new scripts:

- Keep scripts independent of the API layer.
- Avoid hard-coded secrets or credentials.
- Make scripts idempotent whenever practical.
- Include clear console output indicating progress and results.
- Keep business logic inside the application where possible; scripts should primarily orchestrate data creation.

---

# SmartPark AI

Web-based Smart Parking Availability & Prediction System

Final Year Project by Philip Agano

University of Greenwich (BSc Hons Computing)