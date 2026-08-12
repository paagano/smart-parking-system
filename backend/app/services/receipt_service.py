"""
Receipt Service

Business service responsible for the SmartPark receipt lifecycle.

Responsibilities
----------------
- Create receipts from successful PaymentTransactions
- Create the financial/customer snapshot stored on Receipt
- Generate receipt numbers
- Generate verification tokens
- Generate PDF documents
- Store generated PDFs through StorageService
- Update receipt generation lifecycle
- Retrieve receipts
- Verify receipts
- Retrieve customer receipt history
- Provide receipt download/access URLs
- Create receipt-available notifications

Architecture
------------
ReceiptService coordinates:

    PaymentTransaction
            |
            v
      ReceiptService
            |
      +-----+-----+
      |           |
      v           v
ReceiptPDF   StorageService
Service
      |
      v
   PDF bytes

Persistence is delegated to ReceiptRepository.

PDF generation is delegated to ReceiptPDFService.

Storage is delegated to StorageService.

Notifications are delegated to NotificationService.

The service must NOT contain:
    - SQL queries
    - Direct filesystem operations
    - Supabase-specific logic
    - Payment processing logic
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.handlers import (
    NotFoundException,
)

from app.models.enums import (
    NotificationChannel,
    NotificationPriority,
    NotificationType,
    PaymentStatus,
    PaymentType,
    ReceiptStatus,
    ReceiptType,
)

from app.models.payment_transaction import (
    PaymentTransaction,
)

from app.models.receipt import (
    Receipt,
)

from app.repositories.receipt_repository import (
    ReceiptRepository,
)

from app.schemas.receipt import (
    ReceiptCreate,
    ReceiptGenerationResponse,
    ReceiptListResponse,
    ReceiptLookupResponse,
    ReceiptSummary,
    ReceiptVerificationResponse,
)

from app.schemas.notification import (
    NotificationCreate,
)

from app.services.notification_service import (
    NotificationService,
)

from app.services.receipt_pdf_service import (
    ReceiptPDFService,
)

from app.storage import (
    StorageService,
)


class ReceiptService:
    """
    Business service responsible for SmartPark receipts.
    """

    # ==========================================================
    # Configuration
    # ==========================================================

    RECEIPT_PREFIX = "RCP"

    STORAGE_FOLDER = "receipts"

    PDF_CONTENT_TYPE = "application/pdf"

    VERIFICATION_TOKEN_BYTES = 32

    # ==========================================================
    # Construction
    # ==========================================================

    def __init__(
        self,
        *,
        db: AsyncSession,
        repository: ReceiptRepository,
        storage_service: StorageService,
        pdf_service: ReceiptPDFService,
        notification_service: NotificationService | None = None,
    ) -> None:
        """
        Create a ReceiptService.

        Parameters
        ----------
        db:
            Async SQLAlchemy database session.

        repository:
            Receipt persistence repository.

        storage_service:
            Storage abstraction.

            This may resolve to:
                - LocalStorage
                - SupabaseStorage
                - another future provider

        pdf_service:
            PDF generation service.

        notification_service:
            Optional notification service.

            Receipt generation itself must remain successful even
            if notification creation fails.
        """

        self.db = db

        self.repository = repository

        self.storage_service = (
            storage_service
        )

        self.pdf_service = (
            pdf_service
        )

        self.notification_service = (
            notification_service
        )

    # ==========================================================
    # Internal Helpers
    # ==========================================================

    @classmethod
    def _generate_receipt_number(
        cls,
    ) -> str:
        """
        Generate a unique public receipt number.

        Example
        -------
        RCP-20260812-001530-A3F91C
        """

        timestamp = datetime.now(
            timezone.utc,
        ).strftime(
            "%Y%m%d-%H%M%S",
        )

        suffix = uuid.uuid4().hex[
            :6
        ].upper()

        return (
            f"{cls.RECEIPT_PREFIX}-"
            f"{timestamp}-"
            f"{suffix}"
        )

    @staticmethod
    def _generate_verification_token() -> str:
        """
        Generate a cryptographically secure verification token.

        The token is deliberately independent of the receipt
        number so that knowing a receipt number does not expose
        the verification secret.
        """

        return secrets.token_urlsafe(
            ReceiptService.VERIFICATION_TOKEN_BYTES,
        )

    @staticmethod
    def _utc_now() -> datetime:
        """
        Return the current UTC timestamp.
        """

        return datetime.now(
            timezone.utc,
        )

    @staticmethod
    def _payment_type_to_receipt_type(
        payment: PaymentTransaction,
    ) -> ReceiptType:
        """
        Determine the ReceiptType from the payment transaction.

        Normal payments produce PAYMENT receipts.

        Refund transactions produce REFUND receipts.

        The Receipt model currently supports PAYMENT and REFUND
        receipt types.
        """

        if (
            payment.payment_type
            == PaymentType.REFUND
        ):
            return ReceiptType.REFUND

        return ReceiptType.PAYMENT

    @staticmethod
    def _payment_status_allows_receipt(
        payment: PaymentTransaction,
    ) -> bool:
        """
        Determine whether a payment is eligible for receipt
        generation.

        A receipt represents a completed financial event.

        Successful payments and refunds are eligible.

        Pending, processing, failed, cancelled and voided
        transactions are not eligible for normal receipt
        generation.
        """

        return payment.status in {
            PaymentStatus.SUCCESSFUL,
            PaymentStatus.REFUNDED,
        }

    @staticmethod
    def _money_is_valid(
        value: object | None,
    ) -> bool:
        """
        Determine whether a monetary field contains a value.
        """

        return value is not None

    # ==========================================================
    # Notification
    # ==========================================================

    async def _create_receipt_notification(
        self,
        *,
        receipt: Receipt,
    ) -> None:
        """
        Create an in-app notification informing the customer
        that the receipt is available.

        Notification failures are deliberately isolated from
        receipt generation.

        A receipt that has already been successfully generated
        must not become FAILED because notification creation
        failed.
        """

        if (
            self.notification_service is None
        ):
            return

        if receipt.customer_id is None:
            return

        try:
            await self.notification_service.create_notification(
                data=NotificationCreate(
                    user_id=receipt.customer_id,
                    type=NotificationType.RECEIPT_AVAILABLE,
                    channel=NotificationChannel.IN_APP,
                    priority=NotificationPriority.NORMAL,
                    title="Receipt Available",
                    message=(
                        f"Your SmartPark receipt "
                        f"{receipt.receipt_number} "
                        f"for "
                        f"{receipt.currency} "
                        f"{receipt.total_amount} "
                        f"is now available."
                    ),
                    related_entity_type="RECEIPT",
                    related_entity_id=receipt.id,
                ),
            )

        except Exception:
            # Notification failure must never invalidate
            # an already generated receipt.
            pass

    # ==========================================================
    # Receipt Snapshot Creation
    # ==========================================================

    def _build_receipt_from_payment(
        self,
        *,
        payment: PaymentTransaction,
    ) -> Receipt:
        """
        Build a Receipt financial/customer snapshot from a
        PaymentTransaction.

        No database operation is performed here.

        This method deliberately copies the values required for
        the historical customer-facing document.
        """

        if payment.id is None:
            raise ValueError(
                "Payment transaction ID is required."
            )

        if not self._money_is_valid(
            payment.subtotal_amount,
        ):
            raise ValueError(
                "Payment subtotal amount is required."
            )

        if not self._money_is_valid(
            payment.total_amount,
        ):
            raise ValueError(
                "Payment total amount is required."
            )

        if payment.currency is None:
            raise ValueError(
                "Payment currency is required."
            )

        if payment.payment_method is None:
            raise ValueError(
                "Payment method is required."
            )

        receipt_type = (
            self._payment_type_to_receipt_type(
                payment,
            )
        )

        return Receipt(
            receipt_number=(
                self._generate_receipt_number()
            ),
            receipt_type=receipt_type,
            status=ReceiptStatus.PENDING,

            payment_transaction_id=payment.id,

            customer_id=payment.customer_id,

            subtotal_amount=payment.subtotal_amount,
            discount_amount=(
                payment.discount_amount
                or 0
            ),
            tax_amount=(
                payment.tax_amount
                or 0
            ),
            total_amount=payment.total_amount,

            currency=(
                getattr(
                    payment.currency,
                    "value",
                    payment.currency,
                )
            ),

            payment_method=(
                getattr(
                    payment.payment_method,
                    "value",
                    payment.payment_method,
                )
            ),

            payment_provider=(
                getattr(
                    payment.payment_provider,
                    "value",
                    payment.payment_provider,
                )
                if payment.payment_provider is not None
                else None
            ),

            provider_receipt_number=(
                payment.receipt_number
                or payment.external_reference
            ),

            paid_at=payment.paid_at,

            customer_name=payment.payer_name,
            customer_phone=payment.payer_phone,
            customer_email=payment.payer_email,

            pdf_storage_path=None,
            pdf_url=None,

            verification_token=(
                self._generate_verification_token()
            ),

            generated_at=None,
            available_at=None,
            failure_reason=None,
        )

    # ==========================================================
    # Create Receipt
    # ==========================================================

    async def create_receipt(
        self,
        *,
        payment: PaymentTransaction,
    ) -> Receipt:
        """
        Create a Receipt from a PaymentTransaction.

        This method creates the receipt record in PENDING state.

        It does NOT generate the PDF.

        The PDF generation step is deliberately separate so that
        the receipt record can be created independently from the
        document-generation process.

        Workflow
        --------
        Validate Payment
              ↓
        Prevent Duplicate Receipt
              ↓
        Create Snapshot
              ↓
        Persist Receipt
              ↓
        Commit
              ↓
        Return Receipt
        """

        if payment is None:
            raise ValueError(
                "Payment transaction is required."
            )

        if payment.id is None:
            raise ValueError(
                "Payment transaction ID is required."
            )

        if not self._payment_status_allows_receipt(
            payment,
        ):
            raise ValueError(
                "A receipt can only be generated for a "
                "successful or refunded payment transaction."
            )

        # ------------------------------------------------------
        # Prevent duplicate receipt
        # ------------------------------------------------------

        existing = (
            await self.repository.get_by_payment_transaction_id(
                payment.id,
            )
        )

        if existing is not None:
            return existing

        try:
            receipt = (
                self._build_receipt_from_payment(
                    payment=payment,
                )
            )

            receipt = await self.repository.save(
                receipt,
            )

            await self.repository.commit()

            await self.repository.refresh(
                receipt,
            )

            if receipt.id is None:
                raise RuntimeError(
                    "Failed to generate Receipt primary key."
                )

            return receipt

        except Exception:
            await self.repository.rollback()
            raise

    # ==========================================================
    # Create Receipt From Schema
    # ==========================================================

    async def create_receipt_from_data(
        self,
        *,
        data: ReceiptCreate,
    ) -> Receipt:
        """
        Create a Receipt from ReceiptCreate data.

        This method is intended for controlled internal/admin
        workflows where the receipt data has already been
        validated by the caller.

        Normal payment-generated receipts should preferably use
        create_receipt(payment=...).
        """

        if data is None:
            raise ValueError(
                "Receipt creation data is required."
            )

        existing = (
            await self.repository.get_by_payment_transaction_id(
                data.payment_transaction_id,
            )
        )

        if existing is not None:
            return existing

        try:
            receipt = Receipt(
                receipt_number=(
                    self._generate_receipt_number()
                ),

                receipt_type=data.receipt_type,

                status=ReceiptStatus.PENDING,

                payment_transaction_id=(
                    data.payment_transaction_id
                ),

                customer_id=data.customer_id,

                subtotal_amount=data.subtotal_amount,
                discount_amount=data.discount_amount,
                tax_amount=data.tax_amount,
                total_amount=data.total_amount,

                currency=data.currency,

                payment_method=data.payment_method,
                payment_provider=data.payment_provider,
                provider_receipt_number=(
                    data.provider_receipt_number
                ),

                paid_at=data.paid_at,

                customer_name=data.customer_name,
                customer_phone=data.customer_phone,
                customer_email=data.customer_email,

                verification_token=(
                    self._generate_verification_token()
                ),
            )

            receipt = await self.repository.save(
                receipt,
            )

            await self.repository.commit()

            await self.repository.refresh(
                receipt,
            )

            return receipt

        except Exception:
            await self.repository.rollback()
            raise

    # ==========================================================
    # Generate Receipt
    # ==========================================================

    async def generate_receipt(
        self,
        *,
        receipt_id: int,
        overwrite: bool = False,
    ) -> Receipt:
        """
        Generate and store a receipt PDF.

        Workflow
        --------
        Retrieve Receipt
              ↓
        Validate Receipt
              ↓
        Generate PDF bytes
              ↓
        Upload PDF
              ↓
        Generate Access URL
              ↓
        Mark GENERATED
              ↓
        Mark AVAILABLE
              ↓
        Commit
              ↓
        Notification

        If generation or storage fails, the Receipt is marked
        FAILED and the failure reason is retained.
        """

        receipt = (
            await self.repository.get_by_id(
                receipt_id,
            )
        )

        if receipt is None:
            raise NotFoundException(
                "Receipt not found."
            )

        # ------------------------------------------------------
        # Idempotency
        # ------------------------------------------------------

        if (
            receipt.status
            == ReceiptStatus.AVAILABLE
            and receipt.pdf_storage_path
            and not overwrite
        ):
            return receipt

        # ------------------------------------------------------
        # Validate receipt
        # ------------------------------------------------------

        self._validate_receipt_for_generation(
            receipt=receipt,
        )

        storage_path = (
            self._build_storage_path(
                receipt=receipt,
            )
        )

        try:
            # --------------------------------------------------
            # Generate PDF
            # --------------------------------------------------

            pdf_bytes = (
                self.pdf_service.generate_receipt_pdf(
                    receipt=receipt,
                )
            )

            if not pdf_bytes:
                raise RuntimeError(
                    "Receipt PDF generation returned empty content."
                )

            # --------------------------------------------------
            # Upload PDF
            # --------------------------------------------------

            stored_path = (
                await self.storage_service.upload(
                    path=storage_path,
                    content=pdf_bytes,
                    content_type=self.PDF_CONTENT_TYPE,
                    overwrite=overwrite,
                )
            )

            if not stored_path:
                raise RuntimeError(
                    "Storage provider returned an empty storage path."
                )

            # --------------------------------------------------
            # Generate access URL
            # --------------------------------------------------

            pdf_url = (
                await self.storage_service.get_url(
                    path=stored_path,
                )
            )

            # --------------------------------------------------
            # Update Receipt
            # --------------------------------------------------

            now = self._utc_now()

            receipt.pdf_storage_path = (
                stored_path
            )

            receipt.pdf_url = (
                pdf_url
            )

            receipt.generated_at = (
                now
            )

            receipt.available_at = (
                now
            )

            receipt.failure_reason = None

            receipt.status = (
                ReceiptStatus.AVAILABLE
            )

            await self.repository.save(
                receipt,
            )

            await self.repository.commit()

            await self.repository.refresh(
                receipt,
            )

            # --------------------------------------------------
            # Notification
            # --------------------------------------------------

            await self._create_receipt_notification(
                receipt=receipt,
            )

            return receipt

        except Exception as exc:

            # --------------------------------------------------
            # Persist failure state
            # --------------------------------------------------

            try:
                receipt.status = (
                    ReceiptStatus.FAILED
                )

                receipt.failure_reason = (
                    self._format_failure_reason(
                        exc,
                    )
                )

                await self.repository.save(
                    receipt,
                )

                await self.repository.commit()

                await self.repository.refresh(
                    receipt,
                )

            except Exception:
                await self.repository.rollback()

            raise

    # ==========================================================
    # Storage Path
    # ==========================================================

    def _build_storage_path(
        self,
        *,
        receipt: Receipt,
    ) -> str:
        """
        Build the provider-independent storage path for a receipt.

        Example
        -------
        receipts/2026/08/RCP-20260812-001530-A3F91C.pdf

        The path contains no provider-specific information.
        """

        created_at = (
            receipt.created_at
            or self._utc_now()
        )

        return (
            f"{self.STORAGE_FOLDER}/"
            f"{created_at.year:04d}/"
            f"{created_at.month:02d}/"
            f"{receipt.receipt_number}.pdf"
        )

    # ==========================================================
    # Receipt Validation
    # ==========================================================

    @staticmethod
    def _validate_receipt_for_generation(
        *,
        receipt: Receipt,
    ) -> None:
        """
        Validate that the Receipt contains the minimum data
        required by ReceiptPDFService.
        """

        if not receipt.receipt_number:
            raise ValueError(
                "Receipt number is required."
            )

        if not receipt.payment_transaction_id:
            raise ValueError(
                "Payment transaction ID is required."
            )

        if receipt.subtotal_amount is None:
            raise ValueError(
                "Receipt subtotal amount is required."
            )

        if receipt.total_amount is None:
            raise ValueError(
                "Receipt total amount is required."
            )

        if not receipt.currency:
            raise ValueError(
                "Receipt currency is required."
            )

        if not receipt.payment_method:
            raise ValueError(
                "Receipt payment method is required."
            )

        if not receipt.verification_token:
            raise ValueError(
                "Receipt verification token is required."
            )

    @staticmethod
    def _format_failure_reason(
        exception: Exception,
    ) -> str:
        """
        Convert an exception into a safe persisted failure reason.

        The original exception is deliberately not swallowed;
        this value is only retained for operational diagnostics.
        """

        message = str(
            exception,
        ).strip()

        if not message:
            message = exception.__class__.__name__

        return message[:4000]

    # ==========================================================
    # Regenerate Receipt
    # ==========================================================

    async def regenerate_receipt(
        self,
        *,
        receipt_id: int,
    ) -> Receipt:
        """
        Regenerate an existing receipt PDF.

        The Receipt identity, financial snapshot and verification
        token remain unchanged.

        Only the stored PDF representation is replaced.
        """

        return await self.generate_receipt(
            receipt_id=receipt_id,
            overwrite=True,
        )

    # ==========================================================
    # Get Receipt
    # ==========================================================

    async def get_receipt(
        self,
        receipt_id: int,
    ) -> Receipt:
        """
        Retrieve a Receipt by ID.

        Raises
        ------
        NotFoundException
            If the receipt does not exist.
        """

        receipt = (
            await self.repository.get_by_id(
                receipt_id,
            )
        )

        if receipt is None:
            raise NotFoundException(
                "Receipt not found."
            )

        return receipt

    # ==========================================================
    # Receipt Number Lookup
    # ==========================================================

    async def get_by_receipt_number(
        self,
        receipt_number: str,
    ) -> Receipt:
        """
        Retrieve a receipt by its public receipt number.
        """

        if not receipt_number:
            raise ValueError(
                "Receipt number is required."
            )

        receipt = (
            await self.repository.get_by_receipt_number(
                receipt_number,
            )
        )

        if receipt is None:
            raise NotFoundException(
                "Receipt not found."
            )

        return receipt

    # ==========================================================
    # Payment Transaction Lookup
    # ==========================================================

    async def get_by_payment_transaction(
        self,
        payment_transaction_id: int,
    ) -> Receipt | None:
        """
        Retrieve the receipt associated with a payment
        transaction.
        """

        return (
            await self.repository.get_by_payment_transaction_id(
                payment_transaction_id,
            )
        )

    # ==========================================================
    # Verification Token Lookup
    # ==========================================================

    async def get_by_verification_token(
        self,
        verification_token: str,
    ) -> Receipt:
        """
        Retrieve a receipt using its verification token.

        This method is intended for internal verification
        workflows.
        """

        if not verification_token:
            raise ValueError(
                "Verification token is required."
            )

        receipt = (
            await self.repository.get_by_verification_token(
                verification_token,
            )
        )

        if receipt is None:
            raise NotFoundException(
                "Receipt not found."
            )

        return receipt

    # ==========================================================
    # Verify Receipt
    # ==========================================================

    async def verify_receipt(
        self,
        *,
        receipt_number: str,
        verification_token: str,
    ) -> ReceiptVerificationResponse:
        """
        Verify a receipt using its receipt number and
        verification token.

        The verification token is never returned.

        Verification succeeds only when:

            - The receipt exists
            - The supplied token matches
            - The receipt is AVAILABLE

        A FAILED/PENDING receipt is not considered a valid
        customer-facing receipt.
        """

        if not receipt_number:
            raise ValueError(
                "Receipt number is required."
            )

        if not verification_token:
            raise ValueError(
                "Verification token is required."
            )

        receipt = (
            await self.repository.get_by_receipt_number(
                receipt_number,
            )
        )

        verified_at = self._utc_now()

        if receipt is None:
            raise NotFoundException(
                "Receipt not found."
            )

        valid = (
            secrets.compare_digest(
                receipt.verification_token,
                verification_token,
            )
            and receipt.status
            == ReceiptStatus.AVAILABLE
        )

        return ReceiptVerificationResponse(
            valid=valid,
            receipt_number=receipt.receipt_number,
            status=receipt.status,
            receipt_type=receipt.receipt_type,
            total_amount=receipt.total_amount,
            currency=receipt.currency,
            payment_transaction_id=(
                receipt.payment_transaction_id
            ),
            paid_at=receipt.paid_at,
            verified_at=verified_at,
        )

    # ==========================================================
    # Public Receipt Lookup
    # ==========================================================

    async def lookup_receipt(
        self,
        *,
        receipt_number: str,
    ) -> ReceiptLookupResponse:
        """
        Return the public-facing receipt lookup information.

        The verification token and internal storage details are
        deliberately excluded.
        """

        receipt = (
            await self.get_by_receipt_number(
                receipt_number,
            )
        )

        return ReceiptLookupResponse(
            receipt_number=receipt.receipt_number,
            receipt_type=receipt.receipt_type,
            status=receipt.status,
            total_amount=receipt.total_amount,
            currency=receipt.currency,
            payment_method=receipt.payment_method,
            payment_provider=receipt.payment_provider,
            provider_receipt_number=(
                receipt.provider_receipt_number
            ),
            customer_name=receipt.customer_name,
            paid_at=receipt.paid_at,
            payment_transaction_id=(
                receipt.payment_transaction_id
            ),
            created_at=receipt.created_at,
        )

    # ==========================================================
    # Customer Receipts
    # ==========================================================

    async def get_customer_receipts(
        self,
        *,
        customer_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> ReceiptListResponse:
        """
        Retrieve receipts belonging to a customer.

        Returns a paginated ReceiptListResponse.
        """

        if customer_id <= 0:
            raise ValueError(
                "Customer ID must be greater than zero."
            )

        if limit <= 0:
            raise ValueError(
                "Limit must be greater than zero."
            )

        if offset < 0:
            raise ValueError(
                "Offset cannot be negative."
            )

        receipts = (
            await self.repository.get_customer_receipts(
                customer_id=customer_id,
                limit=limit,
                offset=offset,
            )
        )

        total = (
            await self.repository.count_customer_receipts(
                customer_id,
            )
        )

        items = [
            ReceiptSummary.model_validate(
                receipt,
            )
            for receipt in receipts
        ]

        return ReceiptListResponse(
            total=total,
            items=items,
        )

    # ==========================================================
    # All Receipts
    # ==========================================================

    async def get_all_receipts(
        self,
    ) -> list[Receipt]:
        """
        Retrieve all receipts.

        Intended primarily for administrative operations.
        """

        return await self.repository.get_all()

    # ==========================================================
    # Pending Receipts
    # ==========================================================

    async def get_pending_receipts(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Receipt]:
        """
        Retrieve receipts awaiting PDF generation.
        """

        return (
            await self.repository.get_pending_receipts(
                limit=limit,
                offset=offset,
            )
        )

    # ==========================================================
    # Failed Receipts
    # ==========================================================

    async def get_failed_receipts(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Receipt]:
        """
        Retrieve receipts whose PDF generation failed.
        """

        return (
            await self.repository.get_failed_receipts(
                limit=limit,
                offset=offset,
            )
        )

    # ==========================================================
    # Receipt URL
    # ==========================================================

    async def get_receipt_url(
        self,
        *,
        receipt_id: int,
        expires_in: int = 3600,
    ) -> str:
        """
        Return an access URL for a generated receipt PDF.

        For private Supabase storage this will normally be a
        signed URL.

        For local storage this may be an application URL.
        """

        receipt = await self.get_receipt(
            receipt_id,
        )

        if not receipt.pdf_storage_path:
            raise ValueError(
                "Receipt PDF is not available."
            )

        if (
            receipt.status
            != ReceiptStatus.AVAILABLE
        ):
            raise ValueError(
                "Receipt PDF is not available."
            )

        return (
            await self.storage_service.get_signed_url(
                path=receipt.pdf_storage_path,
                expires_in=expires_in,
            )
        )

    # ==========================================================
    # Receipt PDF Download
    # ==========================================================

    async def download_receipt_pdf(
        self,
        *,
        receipt_id: int,
    ) -> bytes:
        """
        Download the generated receipt PDF through the
        storage abstraction.
        """

        receipt = await self.get_receipt(
            receipt_id,
        )

        if not receipt.pdf_storage_path:
            raise ValueError(
                "Receipt PDF is not available."
            )

        if (
            receipt.status
            != ReceiptStatus.AVAILABLE
        ):
            raise ValueError(
                "Receipt PDF is not available."
            )

        return (
            await self.storage_service.download(
                path=receipt.pdf_storage_path,
            )
        )

    # ==========================================================
    # Delete Stored PDF
    # ==========================================================

    async def delete_receipt_pdf(
        self,
        *,
        receipt_id: int,
    ) -> Receipt:
        """
        Delete the stored PDF representation of a receipt.

        The financial receipt record itself is NOT deleted.

        This is intentionally separate from receipt deletion
        because the Receipt is a financial document.
        """

        receipt = await self.get_receipt(
            receipt_id,
        )

        if not receipt.pdf_storage_path:
            return receipt

        try:
            await self.storage_service.delete(
                path=receipt.pdf_storage_path,
            )

            receipt.pdf_storage_path = None
            receipt.pdf_url = None
            receipt.available_at = None

            receipt.status = (
                ReceiptStatus.PENDING
            )

            receipt.failure_reason = None

            await self.repository.save(
                receipt,
            )

            await self.repository.commit()

            await self.repository.refresh(
                receipt,
            )

            return receipt

        except Exception:
            await self.repository.rollback()
            raise

    # ==========================================================
    # Existence
    # ==========================================================

    async def receipt_exists(
        self,
        receipt_id: int,
    ) -> bool:
        """
        Determine whether a receipt exists.
        """

        return await self.repository.exists(
            receipt_id,
        )

    # ==========================================================
    # Statistics
    # ==========================================================

    async def total_receipts(
        self,
    ) -> int:
        """
        Return total receipt count.
        """

        return await self.repository.count_all()

    async def total_pending_receipts(
        self,
    ) -> int:
        """
        Return the number of pending receipts.
        """

        return await self.repository.count_by_status(
            ReceiptStatus.PENDING,
        )

    async def total_generated_receipts(
        self,
    ) -> int:
        """
        Return the number of generated receipts.

        GENERATED represents a receipt whose PDF has been
        generated but is not necessarily yet marked AVAILABLE.
        """

        return await self.repository.count_by_status(
            ReceiptStatus.GENERATED,
        )

    async def total_available_receipts(
        self,
    ) -> int:
        """
        Return the number of receipts currently available
        to customers.
        """

        return await self.repository.count_by_status(
            ReceiptStatus.AVAILABLE,
        )

    async def total_failed_receipts(
        self,
    ) -> int:
        """
        Return the number of receipts whose generation failed.
        """

        return await self.repository.count_by_status(
            ReceiptStatus.FAILED,
        )