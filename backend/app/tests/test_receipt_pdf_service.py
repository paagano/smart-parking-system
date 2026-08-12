"""
ReceiptPDFService tests.

These tests verify that:

- ReceiptPDFService can be constructed.
- A valid Receipt produces non-empty PDF bytes.
- The generated document has a valid PDF signature.
- Required receipt fields are validated.
- Missing required values produce ValueError.

These tests do NOT:

- connect to PostgreSQL
- upload files
- interact with Supabase
- send notifications
- persist anything
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.receipt_pdf_service import ReceiptPDFService


# ==========================================================
# Test Receipt Factory
# ==========================================================


def make_receipt(
    **overrides,
):
    """
    Create a lightweight receipt-like object containing all
    fields required by ReceiptPDFService.

    A SimpleNamespace is intentionally used here because the
    PDF service only needs the receipt attributes required for
    document rendering. No database connection is necessary.
    """

    receipt = SimpleNamespace(
        receipt_number="SP-2026-000001",
        receipt_type="PAYMENT",
        status="COMPLETED",
        payment_transaction_id=1001,

        customer_name="Philip Agano",
        customer_phone="0712345678",
        customer_email="philip@example.com",

        subtotal_amount=Decimal("400.00"),
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("400.00"),
        currency="KES",

        payment_method="M_PESA",
        payment_provider="M-Pesa",
        provider_receipt_number="QK12345678",
        paid_at=datetime(
            2026,
            8,
            12,
            10,
            30,
            0,
            tzinfo=timezone.utc,
        ),

        verification_token="ABCDEF1234567890",

        created_at=datetime(
            2026,
            8,
            12,
            10,
            30,
            0,
            tzinfo=timezone.utc,
        ),

        generated_at=datetime(
            2026,
            8,
            12,
            10,
            31,
            0,
            tzinfo=timezone.utc,
        ),

        available_at=datetime(
            2026,
            8,
            12,
            10,
            31,
            0,
            tzinfo=timezone.utc,
        ),
    )

    for key, value in overrides.items():
        setattr(receipt, key, value)

    return receipt


# ==========================================================
# Construction
# ==========================================================


def test_receipt_pdf_service_construction():
    """
    Verify that ReceiptPDFService can be instantiated.
    """

    service = ReceiptPDFService()

    assert service is not None

    assert service.company_name == "SmartPark AI"

    assert (
        service.company_tagline
        == "Smart Parking Management System"
    )

    assert service.styles is not None

    print(
        "ReceiptPDFService construction: OK"
    )


# ==========================================================
# PDF Generation
# ==========================================================


def test_generate_receipt_pdf_returns_valid_pdf_bytes():
    """
    Verify that a valid receipt produces a non-empty PDF.

    The PDF file signature must begin with %PDF.
    """

    service = ReceiptPDFService()

    receipt = make_receipt()

    pdf_bytes = service.generate_receipt_pdf(
        receipt=receipt,
    )

    assert isinstance(
        pdf_bytes,
        bytes,
    )

    assert len(pdf_bytes) > 0

    assert pdf_bytes.startswith(
        b"%PDF",
    )

    print(
        "Receipt PDF generation: OK"
    )


# ==========================================================
# Required Field Validation
# ==========================================================


@pytest.mark.parametrize(
    "field",
    [
        "receipt_number",
        "total_amount",
        "currency",
        "payment_method",
        "verification_token",
    ],
)
def test_generate_receipt_pdf_requires_required_fields(
    field,
):
    """
    Verify that the PDF service rejects receipts missing
    required generation fields.
    """

    service = ReceiptPDFService()

    receipt = make_receipt(
        **{
            field: None,
        }
    )

    with pytest.raises(ValueError):
        service.generate_receipt_pdf(
            receipt=receipt,
        )


# ==========================================================
# None Receipt
# ==========================================================


def test_generate_receipt_pdf_rejects_none_receipt():
    """
    Verify that None cannot be supplied as the receipt.
    """

    service = ReceiptPDFService()

    with pytest.raises(ValueError):
        service.generate_receipt_pdf(
            receipt=None,
        )


# ==========================================================
# Optional Customer Information
# ==========================================================


def test_generate_receipt_pdf_supports_walk_in_customer():
    """
    Verify that a receipt without customer information can
    still be generated.

    ReceiptPDFService should render the customer as
    "Walk-in Customer".
    """

    service = ReceiptPDFService()

    receipt = make_receipt(
        customer_name=None,
        customer_phone=None,
        customer_email=None,
    )

    pdf_bytes = service.generate_receipt_pdf(
        receipt=receipt,
    )

    assert isinstance(
        pdf_bytes,
        bytes,
    )

    assert pdf_bytes.startswith(
        b"%PDF",
    )

    assert len(pdf_bytes) > 0

    print(
        "Walk-in customer PDF generation: OK"
    )


# ==========================================================
# Optional Payment Information
# ==========================================================


def test_generate_receipt_pdf_supports_missing_optional_payment_details():
    """
    Verify that optional payment/provider fields may be absent.
    """

    service = ReceiptPDFService()

    receipt = make_receipt(
        payment_provider=None,
        provider_receipt_number=None,
        paid_at=None,
    )

    pdf_bytes = service.generate_receipt_pdf(
        receipt=receipt,
    )

    assert isinstance(
        pdf_bytes,
        bytes,
    )

    assert pdf_bytes.startswith(
        b"%PDF",
    )

    assert len(pdf_bytes) > 0

    print(
        "Optional payment details PDF generation: OK"
    )


# ==========================================================
# Formatting Helpers
# ==========================================================


def test_format_money():
    """
    Verify consistent monetary formatting.
    """

    assert (
        ReceiptPDFService._format_money(
            Decimal("400"),
            "KES",
        )
        == "KES 400.00"
    )

    assert (
        ReceiptPDFService._format_money(
            Decimal("1234.5"),
            "KES",
        )
        == "KES 1,234.50"
    )


def test_format_datetime():
    """
    Verify customer-facing datetime formatting.
    """

    value = datetime(
        2026,
        8,
        12,
        10,
        30,
        15,
        tzinfo=timezone.utc,
    )

    assert (
        ReceiptPDFService._format_datetime(
            value,
        )
        == "12 Aug 2026 10:30:15 UTC"
    )

    assert (
        ReceiptPDFService._format_datetime(
            None,
        )
        == "N/A"
    )


def test_format_verification_token():
    """
    Verify verification token grouping.
    """

    assert (
        ReceiptPDFService._format_verification_token(
            "ABCDEF1234567890",
        )
        == "ABCD-EF12-3456-7890"
    )


def test_enum_value_formatting():
    """
    Verify enum/string formatting used by the PDF renderer.
    """

    assert (
        ReceiptPDFService._enum_value(
            "M_PESA",
        )
        == "M Pesa"
    )

    assert (
        ReceiptPDFService._enum_value(
            "PAYMENT_SUCCESSFUL",
        )
        == "Payment Successful"
    )

    assert (
        ReceiptPDFService._enum_value(
            None,
        )
        == "N/A"
    )