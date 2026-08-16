"""
Receipt PDF Service

Responsible for generating customer-facing PDF receipts.

Architecture
------------
ReceiptPDFService is responsible ONLY for PDF document generation.

It does NOT:
    - Persist Receipt records
    - Update Receipt status
    - Upload files to storage
    - Decide which storage provider is active
    - Perform payment processing
    - Send notifications

Those responsibilities belong to:
    - ReceiptRepository
    - ReceiptService
    - StorageService
    - PaymentService
    - NotificationService

The service returns PDF content as bytes so the caller can pass
the generated document to the application's storage abstraction.

This keeps PDF generation completely independent from whether
SmartPark is using local filesystem storage, Supabase Storage,
or another provider in the future.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.receipt import Receipt


class ReceiptPDFService:
    """
    Service responsible for generating SmartPark receipt PDFs.

    The service is deliberately stateless.

    Example
    -------
    pdf_service = ReceiptPDFService()

    pdf_bytes = pdf_service.generate_receipt_pdf(
        receipt=receipt,
    )

    The returned bytes can then be passed directly to the
    application's StorageService.
    """

    # ==========================================================
    # Document Configuration
    # ==========================================================

    PAGE_SIZE = A4

    LEFT_MARGIN = 18 * mm
    RIGHT_MARGIN = 18 * mm
    TOP_MARGIN = 18 * mm
    BOTTOM_MARGIN = 18 * mm

    # ==========================================================
    # Branding
    # ==========================================================

    COMPANY_NAME = "SmartPark AI"
    COMPANY_TAGLINE = "Smart Parking Management System"

    RECEIPT_TITLE = "PAYMENT RECEIPT"

    FOOTER_TEXT = (
        "Thank you for using SmartPark AI. "
        "This is a computer-generated receipt and does not require a signature."
    )

    VERIFICATION_TEXT = (
        "This receipt can be verified using the receipt number "
        "and verification code."
    )

    # ==========================================================
    # Constructor
    # ==========================================================

    def __init__(
        self,
        *,
        company_name: str | None = None,
        company_tagline: str | None = None,
    ) -> None:
        """
        Initialize the PDF service.

        Optional branding values can be supplied later from
        application configuration without changing the PDF
        generation contract.
        """

        self.company_name = (
            company_name
            or self.COMPANY_NAME
        )

        self.company_tagline = (
            company_tagline
            or self.COMPANY_TAGLINE
        )

        self.styles = self._build_styles()

    # ==========================================================
    # Public API
    # ==========================================================

    def generate_receipt_pdf(
        self,
        *,
        receipt: Receipt,
    ) -> bytes:
        """
        Generate a complete PDF receipt.

        Parameters
        ----------
        receipt:
            Receipt ORM entity containing the financial and
            customer snapshot used to render the document.

        Returns
        -------
        bytes
            Complete PDF document as binary data.

        Raises
        ------
        ValueError
            If the supplied receipt is invalid for PDF generation.
        """

        self._validate_receipt(
            receipt=receipt,
        )

        buffer = BytesIO()

        document = SimpleDocTemplate(
            buffer,
            pagesize=self.PAGE_SIZE,
            rightMargin=self.RIGHT_MARGIN,
            leftMargin=self.LEFT_MARGIN,
            topMargin=self.TOP_MARGIN,
            bottomMargin=self.BOTTOM_MARGIN,
            title=f"SmartPark Receipt - {receipt.receipt_number}",
            author=self.company_name,
            subject="SmartPark Payment Receipt",
        )

        story = []

        # ======================================================
        # Header
        # ======================================================

        story.extend(
            self._build_header(
                receipt=receipt,
            )
        )

        story.append(
            Spacer(
                1,
                8 * mm,
            )
        )

        # ======================================================
        # Receipt Information
        # ======================================================

        story.extend(
            self._build_receipt_information(
                receipt=receipt,
            )
        )

        story.append(
            Spacer(
                1,
                7 * mm,
            )
        )

        # ======================================================
        # Customer Information
        # ==========================================================

        story.extend(
            self._build_customer_information(
                receipt=receipt,
            )
        )

        story.append(
            Spacer(
                1,
                7 * mm,
            )
        )

        # ======================================================
        # Payment Information
        # ==========================================================

        story.extend(
            self._build_payment_information(
                receipt=receipt,
            )
        )

        story.append(
            Spacer(
                1,
                8 * mm,
            )
        )

        # ======================================================
        # Financial Summary
        # ==========================================================

        story.extend(
            self._build_financial_summary(
                receipt=receipt,
            )
        )

        story.append(
            Spacer(
                1,
                8 * mm,
            )
        )

        # ======================================================
        # Verification
        # ==========================================================

        story.extend(
            self._build_verification_section(
                receipt=receipt,
            )
        )

        story.append(
            Spacer(
                1,
                8 * mm,
            )
        )

        # ======================================================
        # Footer
        # ==========================================================

        story.extend(
            self._build_footer(
                receipt=receipt,
            )
        )

        # ======================================================
        # Build PDF
        # ======================================================

        document.build(
            story,
        )

        pdf_bytes = buffer.getvalue()

        buffer.close()

        if not pdf_bytes:
            raise RuntimeError(
                "Receipt PDF generation produced an empty document."
            )

        return pdf_bytes

    # ==========================================================
    # Validation
    # ==========================================================

    @staticmethod
    def _validate_receipt(
        *,
        receipt: Receipt,
    ) -> None:
        """
        Validate the minimum data required to generate a receipt.
        """

        if receipt is None:
            raise ValueError(
                "Receipt is required."
            )

        if not receipt.receipt_number:
            raise ValueError(
                "Receipt number is required for PDF generation."
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

    # ==========================================================
    # Styles
    # ==========================================================

    @staticmethod
    def _build_styles() -> dict[str, ParagraphStyle]:
        """
        Build reusable ReportLab paragraph styles.
        """

        base_styles = getSampleStyleSheet()

        return {
            "company": ParagraphStyle(
                "ReceiptCompany",
                parent=base_styles["Heading1"],
                fontName="Helvetica-Bold",
                fontSize=18,
                leading=22,
                alignment=TA_CENTER,
                spaceAfter=2 * mm,
            ),
            "tagline": ParagraphStyle(
                "ReceiptTagline",
                parent=base_styles["Normal"],
                fontName="Helvetica",
                fontSize=9,
                leading=12,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#666666"),
            ),
            "title": ParagraphStyle(
                "ReceiptTitle",
                parent=base_styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=14,
                leading=18,
                alignment=TA_CENTER,
                spaceBefore=2 * mm,
                spaceAfter=2 * mm,
            ),
            "section": ParagraphStyle(
                "ReceiptSection",
                parent=base_styles["Heading3"],
                fontName="Helvetica-Bold",
                fontSize=10,
                leading=13,
                alignment=TA_LEFT,
                spaceAfter=3 * mm,
            ),
            "label": ParagraphStyle(
                "ReceiptLabel",
                parent=base_styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=8.5,
                leading=11,
                textColor=colors.HexColor("#555555"),
            ),
            "value": ParagraphStyle(
                "ReceiptValue",
                parent=base_styles["Normal"],
                fontName="Helvetica",
                fontSize=9,
                leading=12,
            ),
            "value_right": ParagraphStyle(
                "ReceiptValueRight",
                parent=base_styles["Normal"],
                fontName="Helvetica",
                fontSize=9,
                leading=12,
                alignment=TA_RIGHT,
            ),
            "total_label": ParagraphStyle(
                "ReceiptTotalLabel",
                parent=base_styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=11,
                leading=14,
            ),
            "total_value": ParagraphStyle(
                "ReceiptTotalValue",
                parent=base_styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=13,
                leading=16,
                alignment=TA_RIGHT,
            ),
            "small": ParagraphStyle(
                "ReceiptSmall",
                parent=base_styles["Normal"],
                fontName="Helvetica",
                fontSize=7.5,
                leading=10,
                textColor=colors.HexColor("#666666"),
            ),
            "verification": ParagraphStyle(
                "ReceiptVerification",
                parent=base_styles["Normal"],
                fontName="Helvetica",
                fontSize=8,
                leading=11,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#555555"),
            ),
            "verification_code": ParagraphStyle(
                "ReceiptVerificationCode",
                parent=base_styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=10,
                leading=13,
                alignment=TA_CENTER,
            ),
            "footer": ParagraphStyle(
                "ReceiptFooter",
                parent=base_styles["Normal"],
                fontName="Helvetica",
                fontSize=7.5,
                leading=10,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#666666"),
            ),
        }

    # ==========================================================
    # Header
    # ==========================================================

    def _build_header(
        self,
        *,
        receipt: Receipt,
    ) -> list:
        """
        Build the receipt document header.
        """

        elements = [
            Paragraph(
                self.company_name,
                self.styles["company"],
            ),
            Paragraph(
                self.company_tagline,
                self.styles["tagline"],
            ),
            Spacer(
                1,
                4 * mm,
            ),
            HRFlowable(
                width="100%",
                thickness=1,
                color=colors.HexColor("#333333"),
            ),
            Spacer(
                1,
                4 * mm,
            ),
            Paragraph(
                self.RECEIPT_TITLE,
                self.styles["title"],
            ),
        ]

        return elements

    # ==========================================================
    # Receipt Information
    # ==========================================================

    def _build_receipt_information(
        self,
        *,
        receipt: Receipt,
    ) -> list:
        """
        Build receipt identity and document information.
        """

        data = [
            [
                Paragraph(
                    "Receipt Number",
                    self.styles["label"],
                ),
                Paragraph(
                    self._safe_text(
                        receipt.receipt_number,
                    ),
                    self.styles["value"],
                ),
                Paragraph(
                    "Status",
                    self.styles["label"],
                ),
                Paragraph(
                    self._enum_value(
                        receipt.status,
                    ),
                    self.styles["value"],
                ),
            ],
            [
                Paragraph(
                    "Receipt Type",
                    self.styles["label"],
                ),
                Paragraph(
                    self._enum_value(
                        receipt.receipt_type,
                    ),
                    self.styles["value"],
                ),
                Paragraph(
                    "Created",
                    self.styles["label"],
                ),
                Paragraph(
                    self._format_datetime(
                        receipt.created_at,
                    ),
                    self.styles["value"],
                ),
            ],
            [
                Paragraph(
                    "Generated",
                    self.styles["label"],
                ),
                Paragraph(
                    self._format_datetime(
                        receipt.generated_at,
                    ),
                    self.styles["value"],
                ),
                Paragraph(
                    "Available",
                    self.styles["label"],
                ),
                Paragraph(
                    self._format_datetime(
                        receipt.available_at,
                    ),
                    self.styles["value"],
                ),
            ],
        ]

        table = Table(
            data,
            colWidths=[
                32 * mm,
                58 * mm,
                32 * mm,
                58 * mm,
            ],
        )

        table.setStyle(
            TableStyle(
                [
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP",
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, -1),
                        colors.HexColor("#F7F7F7"),
                    ),
                    (
                        "BOX",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.HexColor("#DDDDDD"),
                    ),
                    (
                        "INNERGRID",
                        (0, 0),
                        (-1, -1),
                        0.25,
                        colors.HexColor("#E5E5E5"),
                    ),
                    (
                        "LEFTPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                    (
                        "RIGHTPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                ]
            )
        )

        return [
            Paragraph(
                "Receipt Information",
                self.styles["section"],
            ),
            table,
        ]

    # ==========================================================
    # Customer Information
    # ==========================================================

    def _build_customer_information(
        self,
        *,
        receipt: Receipt,
    ) -> list:
        """
        Build customer snapshot section.
        """

        customer_name = (
            receipt.customer_name
            or "Walk-in Customer"
        )

        data = [
            [
                Paragraph(
                    "Customer Name",
                    self.styles["label"],
                ),
                Paragraph(
                    self._safe_text(
                        customer_name,
                    ),
                    self.styles["value"],
                ),
            ],
            [
                Paragraph(
                    "Phone",
                    self.styles["label"],
                ),
                Paragraph(
                    self._safe_text(
                        receipt.customer_phone,
                    ),
                    self.styles["value"],
                ),
            ],
            [
                Paragraph(
                    "Email",
                    self.styles["label"],
                ),
                Paragraph(
                    self._safe_text(
                        receipt.customer_email,
                    ),
                    self.styles["value"],
                ),
            ],
        ]

        table = Table(
            data,
            colWidths=[
                40 * mm,
                140 * mm,
            ],
        )

        table.setStyle(
            TableStyle(
                [
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP",
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (0, -1),
                        colors.HexColor("#F7F7F7"),
                    ),
                    (
                        "BOX",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.HexColor("#DDDDDD"),
                    ),
                    (
                        "INNERGRID",
                        (0, 0),
                        (-1, -1),
                        0.25,
                        colors.HexColor("#E5E5E5"),
                    ),
                    (
                        "LEFTPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                    (
                        "RIGHTPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                ]
            )
        )

        return [
            Paragraph(
                "Customer Information",
                self.styles["section"],
            ),
            table,
        ]

    # ==========================================================
    # Payment Information
    # ==========================================================

    def _build_payment_information(
        self,
        *,
        receipt: Receipt,
    ) -> list:
        """
        Build payment information section.
        """

        data = [
            [
                Paragraph(
                    "Payment Method",
                    self.styles["label"],
                ),
                Paragraph(
                    self._enum_value(
                        receipt.payment_method,
                    ),
                    self.styles["value"],
                ),
            ],
            [
                Paragraph(
                    "Payment Purpose",
                    self.styles["label"],
                ),
                Paragraph(
                    self._enum_value(
                        receipt.payment_purpose,
                    ),
                    self.styles["value"],
                ),
            ],
            [
                Paragraph(
                    "Payment Provider",
                    self.styles["label"],
                ),
                Paragraph(
                    self._enum_value(
                        receipt.payment_provider,
                    ),
                    self.styles["value"],
                ),
            ],
            [
                Paragraph(
                    "Provider Receipt",
                    self.styles["label"],
                ),
                Paragraph(
                    self._safe_text(
                        receipt.provider_receipt_number,
                    ),
                    self.styles["value"],
                ),
            ],
            [
                Paragraph(
                    "Paid At",
                    self.styles["label"],
                ),
                Paragraph(
                    self._format_datetime(
                        receipt.paid_at,
                    ),
                    self.styles["value"],
                ),
            ],
            [
                Paragraph(
                    "Payment Transaction",
                    self.styles["label"],
                ),
                Paragraph(
                    str(
                        receipt.payment_transaction_id,
                    ),
                    self.styles["value"],
                ),
            ],
        ]

        table = Table(
            data,
            colWidths=[
                45 * mm,
                135 * mm,
            ],
        )

        table.setStyle(
            TableStyle(
                [
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP",
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (0, -1),
                        colors.HexColor("#F7F7F7"),
                    ),
                    (
                        "BOX",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.HexColor("#DDDDDD"),
                    ),
                    (
                        "INNERGRID",
                        (0, 0),
                        (-1, -1),
                        0.25,
                        colors.HexColor("#E5E5E5"),
                    ),
                    (
                        "LEFTPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                    (
                        "RIGHTPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                ]
            )
        )

        return [
            Paragraph(
                "Payment Information",
                self.styles["section"],
            ),
            table,
        ]

    # ==========================================================
    # Financial Summary
    # ==========================================================

    def _build_financial_summary(
        self,
        *,
        receipt: Receipt,
    ) -> list:
        """
        Build the financial breakdown shown on the receipt.
        """

        currency = self._safe_text(
            receipt.currency,
        )

        data = [
            [
                Paragraph(
                    "Subtotal",
                    self.styles["value"],
                ),
                Paragraph(
                    self._format_money(
                        receipt.subtotal_amount,
                        currency,
                    ),
                    self.styles["value_right"],
                ),
            ],
            [
                Paragraph(
                    "Discount",
                    self.styles["value"],
                ),
                Paragraph(
                    self._format_money(
                        receipt.discount_amount,
                        currency,
                    ),
                    self.styles["value_right"],
                ),
            ],
            [
                Paragraph(
                    "Tax",
                    self.styles["value"],
                ),
                Paragraph(
                    self._format_money(
                        receipt.tax_amount,
                        currency,
                    ),
                    self.styles["value_right"],
                ),
            ],
            [
                Paragraph(
                    "TOTAL PAID",
                    self.styles["total_label"],
                ),
                Paragraph(
                    self._format_money(
                        receipt.total_amount,
                        currency,
                    ),
                    self.styles["total_value"],
                ),
            ],
        ]

        table = Table(
            data,
            colWidths=[
                100 * mm,
                80 * mm,
            ],
        )

        table.setStyle(
            TableStyle(
                [
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "MIDDLE",
                    ),
                    (
                        "ALIGN",
                        (1, 0),
                        (1, -1),
                        "RIGHT",
                    ),
                    (
                        "LINEBELOW",
                        (0, 0),
                        (-1, 2),
                        0.25,
                        colors.HexColor("#DDDDDD"),
                    ),
                    (
                        "LINEABOVE",
                        (0, 3),
                        (-1, 3),
                        1,
                        colors.HexColor("#333333"),
                    ),
                    (
                        "BACKGROUND",
                        (0, 3),
                        (-1, 3),
                        colors.HexColor("#F2F2F2"),
                    ),
                    (
                        "LEFTPADDING",
                        (0, 0),
                        (-1, -1),
                        6,
                    ),
                    (
                        "RIGHTPADDING",
                        (0, 0),
                        (-1, -1),
                        6,
                    ),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        6,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        6,
                    ),
                ]
            )
        )

        return [
            Paragraph(
                "Amount Summary",
                self.styles["section"],
            ),
            table,
        ]

    # ==========================================================
    # Verification
    # ==========================================================

    def _build_verification_section(
        self,
        *,
        receipt: Receipt,
    ) -> list:
        """
        Build receipt verification information.

        The verification token is intentionally displayed as a
        verification code rather than exposing it as a URL.
        """

        verification_code = self._format_verification_token(
            receipt.verification_token,
        )

        data = [
            [
                Paragraph(
                    self.VERIFICATION_TEXT,
                    self.styles["verification"],
                ),
            ],
            [
                Paragraph(
                    verification_code,
                    self.styles["verification_code"],
                ),
            ],
            [
                Paragraph(
                    f"Receipt No: {self._safe_text(receipt.receipt_number)}",
                    self.styles["verification"],
                ),
            ],
        ]

        table = Table(
            data,
            colWidths=[
                180 * mm,
            ],
        )

        table.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, -1),
                        colors.HexColor("#F7F7F7"),
                    ),
                    (
                        "BOX",
                        (0, 0),
                        (-1, -1),
                        0.75,
                        colors.HexColor("#CCCCCC"),
                    ),
                    (
                        "LEFTPADDING",
                        (0, 0),
                        (-1, -1),
                        10,
                    ),
                    (
                        "RIGHTPADDING",
                        (0, 0),
                        (-1, -1),
                        10,
                    ),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        7,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        7,
                    ),
                ]
            )
        )

        return [
            Paragraph(
                "Receipt Verification",
                self.styles["section"],
            ),
            table,
        ]

    # ==========================================================
    # Footer
    # ==========================================================

    def _build_footer(
        self,
        *,
        receipt: Receipt,
    ) -> list:
        """
        Build receipt footer.
        """

        return [
            HRFlowable(
                width="100%",
                thickness=0.5,
                color=colors.HexColor("#CCCCCC"),
            ),
            Spacer(
                1,
                3 * mm,
            ),
            Paragraph(
                self.FOOTER_TEXT,
                self.styles["footer"],
            ),
            Spacer(
                1,
                2 * mm,
            ),
            Paragraph(
                (
                    f"Receipt: "
                    f"{self._safe_text(receipt.receipt_number)}"
                ),
                self.styles["footer"],
            ),
        ]

    # ==========================================================
    # Formatting Helpers
    # ==========================================================

    @staticmethod
    def _format_money(
        amount: Decimal | None,
        currency: str,
    ) -> str:
        """
        Format a monetary value consistently.
        """

        if amount is None:
            amount = Decimal("0.00")

        amount = Decimal(amount).quantize(
            Decimal("0.01"),
        )

        return f"{currency} {amount:,.2f}"

    @staticmethod
    def _format_datetime(
        value: datetime | None,
    ) -> str:
        """
        Format datetime values for customer-facing documents.
        """

        if value is None:
            return "N/A"

        return value.strftime(
            "%d %b %Y %H:%M:%S UTC",
        )

    @staticmethod
    def _safe_text(
        value: object | None,
    ) -> str:
        """
        Convert values to safe display text.
        """

        if value is None:
            return "N/A"

        text = str(value).strip()

        if not text:
            return "N/A"

        return text

    @staticmethod
    def _enum_value(
        value: object | None,
    ) -> str:
        """
        Convert Enum or ordinary values into readable text.

        Examples
        --------
        PAYMENT_SUCCESSFUL
            -> Payment Successful

        M_PESA
            -> M Pesa
        """

        if value is None:
            return "N/A"

        raw_value = getattr(
            value,
            "value",
            value,
        )

        text = str(raw_value)

        text = text.replace(
            "_",
            " ",
        )

        return text.title()

    @staticmethod
    def _format_verification_token(
        token: str,
    ) -> str:
        """
        Format a verification token for readability.

        Long tokens are grouped into blocks.

        Example
        -------
        ABCD1234567890
            -> ABCD-1234-5678-90
        """

        token = str(token).strip()

        if not token:
            return "N/A"

        groups = [
            token[index:index + 4]
            for index in range(
                0,
                len(token),
                4,
            )
        ]

        return "-".join(groups)