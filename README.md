# 🚗 SmartPark AI

> **An AI-powered Smart Parking Availability & Prediction System - by PHILIP AGANO AULO**
>
> A modern web application that enables drivers to locate available parking spaces in real time, reserve parking slots, and predict future parking occupancy using Machine Learning.

![Project Status](https://img.shields.io/badge/Status-In%20Development-blue)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.139-green)
![React](https://img.shields.io/badge/React-TypeScript-61DAFB)
![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-336791)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

# 📖 Overview

SmartPark AI is a web-based Smart Parking Availability and Prediction System developed as a **Bachelor of Science (Hons) Computing Final Year Project**.

The system combines modern web technologies with Artificial Intelligence to provide real-time parking availability, reservation management, occupancy analytics, and parking demand prediction.

The objective is to reduce the time drivers spend searching for parking while improving parking facility utilization through predictive analytics.

---

# ✨ Key Features

## 🚗 Driver Portal

- User Registration & Login
- Search Nearby Parking Facilities
- View Live Parking Availability
- Reserve Parking Spaces
- Cancel Reservations
- Navigation to Parking Facility
- Parking History
- AI Parking Availability Prediction

---

## 🏢 Parking Operator Portal

- Dashboard
- Manage Parking Facilities
- Manage Parking Slots
- Approve Reservations
- Release Parking Slots
- Occupancy Statistics
- Pricing Management
- Reports

---

## 👨‍💼 Administrator Portal

- User Management
- Operator Management
- Facility Management
- System Configuration
- Audit Logs
- Analytics Dashboard
- AI Model Monitoring

---

## 🤖 AI Prediction Engine

- Predict Occupancy (30 Minutes)
- Predict Occupancy (1 Hour)
- Predict Occupancy (2 Hours)
- Predict Tomorrow Morning Demand
- Confidence Scores
- Heat Maps

---

# 🏗 System Architecture

```
                React Frontend
                       │
             REST API (FastAPI)
                       │
         Business Logic / Services
                       │
        SQLAlchemy + PostgreSQL
                       │
            Machine Learning Engine
```

---

# 🛠 Technology Stack

## Frontend

- React
- TypeScript
- Tailwind CSS
- React Router
- Axios

---

## Backend

- FastAPI
- Python 3.12
- SQLAlchemy
- Alembic
- JWT Authentication
- Pydantic

---

## Database

- PostgreSQL

---

## Machine Learning

- Scikit-learn
- Pandas
- NumPy

---

## DevOps

- Docker
- GitHub
- GitHub Actions
- Nginx

---

# 📂 Project Structure

```text
smart-parking-system/

├── backend/
├── frontend/
├── docs/
├── datasets/
├── docker/
├── scripts/
```

---

# 🚀 Getting Started

## Clone Repository

```bash
git clone https://github.com/paagano/smart-parking-system.git
```

## Backend

```bash
cd backend

python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1

pip install -r requirements.txt

uvicorn app.main:app --reload
```

---

## Frontend

```bash
cd frontend

npm install

npm run dev
```

---

# 📚 API Documentation

After starting the backend:

Swagger UI

```
http://localhost:8000/docs
```

ReDoc

```
http://localhost:8000/redoc
```

---

# 📅 Development Roadmap

- [x] Project Setup
- [x] Git & GitHub Integration
- [x] Backend Structure
- [x] FastAPI Foundation
- [ ] Configuration Management
- [ ] PostgreSQL Integration
- [ ] Authentication & Authorization
- [ ] Parking Management
- [ ] Reservation System
- [ ] AI Prediction Engine
- [ ] Analytics Dashboard
- [ ] React Frontend
- [ ] Docker Deployment
- [ ] CI/CD Pipeline

---

# 📸 Screenshots

Project screenshots will be added as development progresses.

---

# 👨‍💻 Author

**Philip Agano**

Bachelor of Science (Hons) Computing

University of Greenwich

---

# 🙏 Acknowledgements

- University of Greenwich
- FastAPI
- React
- PostgreSQL
- Scikit-learn

---

# 📄 License

This project is licensed under the MIT License.