[1mdiff --git a/backend/app/api/dependencies/reservations.py b/backend/app/api/dependencies/reservations.py[m
[1mindex e61e4ae..547e4d8 100644[m
[1m--- a/backend/app/api/dependencies/reservations.py[m
[1m+++ b/backend/app/api/dependencies/reservations.py[m
[36m@@ -9,6 +9,8 @@[m [mThis module composes the Reservation subsystem by wiring together:[m
 - ParkingReservationRepository[m
 - ParkingBayRepository[m
 - ParkingSessionService[m
[32m+[m[32m- VehicleRepository[m
[32m+[m[32m- NotificationService[m
 [m
 Business logic belongs in the services.[m
 Persistence belongs in the repositories.[m
[36m@@ -30,13 +32,18 @@[m [mfrom app.api.dependencies.services import ([m
     ParkingSessionServiceDep,[m
 )[m
 [m
[32m+[m[32mfrom app.api.dependencies.pricing import ([m
[32m+[m[32m    PricingServiceDep,[m
[32m+[m[32m)[m
[32m+[m
[32m+[m[32mfrom app.api.dependencies.notifications import ([m
[32m+[m[32m    NotificationServiceDep,[m
[32m+[m[32m)[m
[32m+[m
 from app.services.parking_reservation_service import ([m
     ParkingReservationService,[m
 )[m
 [m
[31m-from app.api.dependencies.pricing import ([m
[31m-    PricingServiceDep,[m
[31m-)[m
 [m
 # ==========================================================[m
 # Parking Reservation Service[m
[36m@@ -49,6 +56,7 @@[m [mdef get_parking_reservation_service([m
     pricing_service: PricingServiceDep,[m
     parking_session_service: ParkingSessionServiceDep,[m
     vehicle_repository: VehicleRepositoryDep,[m
[32m+[m[32m    notification_service: NotificationServiceDep,[m
 ) -> ParkingReservationService:[m
     """[m
     Return a ParkingReservationService instance.[m
[36m@@ -60,6 +68,7 @@[m [mdef get_parking_reservation_service([m
         pricing_service=pricing_service,[m
         parking_session_service=parking_session_service,[m
         vehicle_repository=vehicle_repository,[m
[32m+[m[32m        notification_service=notification_service,[m
     )[m
 [m
 [m
[1mdiff --git a/backend/app/api/dependencies/services.py b/backend/app/api/dependencies/services.py[m
[1mindex 0214572..98c8580 100644[m
[1m--- a/backend/app/api/dependencies/services.py[m
[1m+++ b/backend/app/api/dependencies/services.py[m
[36m@@ -16,6 +16,10 @@[m [mfrom typing import Annotated[m
 [m
 from fastapi import Depends[m
 [m
[32m+[m[32mfrom app.api.dependencies.notifications import ([m
[32m+[m[32m    NotificationServiceDep,[m
[32m+[m[32m)[m
[32m+[m
 from app.api.dependencies.pricing import ([m
     PricingServiceDep,[m
 )[m
[36m@@ -59,6 +63,7 @@[m [mfrom app.services.vehicle_service import ([m
     VehicleService,[m
 )[m
 [m
[32m+[m
 # ==========================================================[m
 # Authentication Service[m
 # ==========================================================[m
[36m@@ -105,9 +110,14 @@[m [mdef get_parking_session_service([m
     parking_bay_repository: ParkingBayRepositoryDep,[m
     pricing_service: PricingServiceDep,[m
     vehicle_repository: VehicleRepositoryDep,[m
[32m+[m[32m    notification_service: NotificationServiceDep,[m
 ) -> ParkingSessionService:[m
     """[m
     Return a ParkingSessionService instance.[m
[32m+[m
[32m+[m[32m    NotificationService is injected so the Parking Session[m
[32m+[m[32m    service can create notifications for relevant session[m
[32m+[m[32m    lifecycle events.[m
     """[m
 [m
     return ParkingSessionService([m
[36m@@ -115,6 +125,7 @@[m [mdef get_parking_session_service([m
         parking_bay_repository=parking_bay_repository,[m
         pricing_service=pricing_service,[m
         vehicle_repository=vehicle_repository,[m
[32m+[m[32m        notification_service=notification_service,[m
     )[m
 [m
 [m
[36m@@ -150,9 +161,14 @@[m [mdef get_payment_service([m
     reservation_repository: ParkingReservationRepositoryDep,[m
     session_repository: ParkingSessionRepositoryDep,[m
     wallet_service: WalletServiceDep,[m
[32m+[m[32m    notification_service: NotificationServiceDep,[m
 ) -> PaymentService:[m
     """[m
     Return a PaymentService instance.[m
[32m+[m
[32m+[m[32m    NotificationService is injected so the Payment Service[m
[32m+[m[32m    can create notifications for relevant payment lifecycle[m
[32m+[m[32m    events.[m
     """[m
 [m
     return PaymentService([m
[36m@@ -161,12 +177,15 @@[m [mdef get_payment_service([m
         reservation_repository=reservation_repository,[m
         session_repository=session_repository,[m
         wallet_service=wallet_service,[m
[32m+[m[32m        notification_service=notification_service,[m
     )[m
 [m
[32m+[m
 # ==========================================================[m
 # Vehicle Service[m
 # ==========================================================[m
 [m
[32m+[m
 def get_vehicle_service([m
     repository: VehicleRepositoryDep,[m
 ) -> VehicleService:[m
[36m@@ -183,6 +202,7 @@[m [mdef get_vehicle_service([m
 # Dependency Aliases[m
 # ==========================================================[m
 [m
[32m+[m
 AuthServiceDep = Annotated[[m
     AuthService,[m
     Depends(get_auth_service),[m
[1mdiff --git a/backend/app/schemas/parking_session.py b/backend/app/schemas/parking_session.py[m
[1mindex ac6c329..f8710e7 100644[m
[1m--- a/backend/app/schemas/parking_session.py[m
[1m+++ b/backend/app/schemas/parking_session.py[m
[36m@@ -18,6 +18,7 @@[m [mfrom pydantic import ([m
 )[m
 [m
 from app.models.enums import ([m
[32m+[m[32m    BillingType,[m
     EntryMethod,[m
     ExitMethod,[m
     PaymentStatus,[m
[36m@@ -84,6 +85,14 @@[m [mclass ParkingSessionBase(BaseModel):[m
         ),[m
     )[m
 [m
[32m+[m[32m    billing_type: BillingType = Field([m
[32m+[m[32m    ...,[m
[32m+[m[32m    description=([m
[32m+[m[32m        "Billing strategy used to calculate parking charges. "[m
[32m+[m[32m        "Supported values: HOURLY, DAILY, FLAT."[m
[32m+[m[32m    ),[m
[32m+[m[32m    )[m
[32m+[m
     session_source: SessionSource[m
 [m
     entry_method: EntryMethod[m
[36m@@ -237,6 +246,8 @@[m [mclass ParkingSessionResponse(BaseModel):[m
 [m
     vehicle_type: VehicleType[m
 [m
[32m+[m[32m    billing_type: BillingType[m
[32m+[m
     session_source: SessionSource[m
 [m
     entry_method: EntryMethod[m
[1mdiff --git a/backend/app/services/parking_reservation_service.py b/backend/app/services/parking_reservation_service.py[m
[1mindex ecbb20f..f2014c0 100644[m
[1m--- a/backend/app/services/parking_reservation_service.py[m
[1m+++ b/backend/app/services/parking_reservation_service.py[m
[36m@@ -6,7 +6,6 @@[m [mmanagement.[m
 [m
 Responsibilities[m
 ----------------[m
[31m-[m
 ✔ Reservation lifecycle[m
 ✔ Reservation validation[m
 ✔ Reservation numbering[m
[36m@@ -14,6 +13,7 @@[m [mResponsibilities[m
 ✔ Reservation conflict detection[m
 ✔ Pricing estimation[m
 ✔ Check-in workflow[m
[32m+[m[32m✔ Reservation notifications[m
 [m
 Persistence belongs in repositories.[m
 """[m
[36m@@ -23,11 +23,24 @@[m [mfrom __future__ import annotations[m
 from datetime import datetime, timedelta[m
 from uuid import uuid4[m
 [m
[31m-from app.models.enums import ReservationStatus[m
[32m+[m[32mfrom app.exceptions.handlers import ([m
[32m+[m[32m    BadRequestException,[m
[32m+[m[32m    NotFoundException,[m
[32m+[m[32m)[m
[32m+[m
[32m+[m[32mfrom app.models.enums import ([m
[32m+[m[32m    BillingType,[m
[32m+[m[32m    NotificationChannel,[m
[32m+[m[32m    NotificationPriority,[m
[32m+[m[32m    NotificationType,[m
[32m+[m[32m    ReservationStatus,[m
[32m+[m[32m)[m
 [m
 from app.models.parking_reservation import ParkingReservation[m
 [m
[31m-from app.repositories.parking_bay_repository import ParkingBayRepository[m
[32m+[m[32mfrom app.repositories.parking_bay_repository import ([m
[32m+[m[32m    ParkingBayRepository,[m
[32m+[m[32m)[m
 [m
 from app.repositories.parking_reservation_repository import ([m
     ParkingReservationRepositor