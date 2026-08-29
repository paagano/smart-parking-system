# SmartPark AI Frontend - Structural Refactor

This package is a structural refactor of the last-known-stable frontend.

## Preserved functionality

- Authentication and JWT session restoration
- Role-based Driver / Operator / Admin routing
- Driver Dashboard live facility/session/reservation/forecast loading
- Live Find Parking page and facility proximity behaviour
- Live Reservations page and its existing reservation categorisation
- AI Forecast page
- Operator Dashboard
- Operator Facilities page
- Admin Dashboard
- Settings page
- Existing styling and visual design

## What changed

- `App.tsx` is now routing-focused.
- Existing page implementations were moved into their corresponding `src/pages/...` locations.
- `Shell` was moved to `src/components/layout/Shell.tsx`.
- Shared `Page`, `Card`, and `Metric` helpers were moved to `src/components/common/Page.tsx`.
- The existing API layer was separated by domain while retaining `src/api/api.ts` and `src/api/index.ts` compatibility barrels.
- `Parking.tsx` was retained and only its API import path was corrected for the new folder depth.
- Role normalization was centralised in `src/auth/role.ts` and reused by `RoleRoute`.

## Deliberately NOT implemented yet

The following files remain empty scaffolding for future peer-coding:

- Create Reservation
- Upcoming Reservations
- Active Reservations
- Reservation History
- Reservation Details
- Parking Sessions
- Session Details
- Vehicle Management
- Payments / Wallet
- Receipts
- Notifications
- Loyalty
- Settings enhancements
- Operator/Admin future modules

No new business functionality was introduced by this refactor.
