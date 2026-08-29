# SmartPark AI Frontend — Tuesday Showcase Build

React + TypeScript + Tailwind CSS + React Router + Axios.

This is a showcase-first frontend. It uses realistic demo data so the presentation is not blocked by unfinished backend/ML endpoints. The Axios client is already prepared for the FastAPI backend at `VITE_API_BASE_URL`.

## Run

```powershell
npm install
npm run dev
```

Open `http://localhost:5173`.

## Demo portals

- Driver: dashboard, nearby parking, reservations, AI prediction, Google Maps navigation
- Operator: operations dashboard, facility management, occupancy, alerts
- Administrator: command centre, user/platform metrics, AI model monitoring

## Important

The UI deliberately does **not** hard-code Birmingham/XGBoost as a product concept. Forecast screens talk about horizons and confidence. The backend/model-registry redesign can therefore happen after the presentation without redesigning the frontend.
