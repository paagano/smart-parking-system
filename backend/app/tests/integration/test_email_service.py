"""
Integration test for EmailService.

This test sends a real email through the configured
SMTP server.

Run:

    pytest app/tests/integration/test_email_service.py -v -s
"""

import pytest

from app.config.settings import settings
from app.services.email_service import EmailService


@pytest.mark.asyncio
async def test_email_service_sends_real_email():
    """
    Send a real test email through Gmail SMTP.
    """

    service = EmailService()

    message_id = await service.send_email(
        to_email=settings.SMTP_USERNAME,
        subject="SmartPark AI - SMTP Integration Test",
        body=(
            "Hello,\n\n"
            "This is a real SMTP integration test from "
            "SmartPark AI.\n\n"
            "If you received this email, the Gmail SMTP "
            "integration is working correctly.\n\n"
            "SmartPark AI"
        ),
        html_body="""
        <html>
            <body>
                <h2>SmartPark AI - SMTP Integration Test</h2>

                <p>Hello,</p>

                <p>
                    This is a real SMTP integration test from
                    <strong>SmartPark AI</strong>.
                </p>

                <p>
                    If you received this email, the Gmail SMTP
                    integration is working correctly.
                </p>

                <p>
                    SmartPark AI
                </p>
            </body>
        </html>
        """,
    )

    assert message_id

    print(
        f"\nSMTP email sent successfully."
        f"\nMessage-ID: {message_id}"
    )