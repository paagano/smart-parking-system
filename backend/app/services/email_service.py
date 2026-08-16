"""
Email Service.

Provides a small, isolated SMTP-based email delivery service.

Responsibilities:
- Connect to the configured SMTP server.
- Authenticate using configured credentials.
- Send plain-text and/or HTML emails.
- Support file attachments.
- Return the SMTP Message-ID for tracking.

Business logic does NOT belong here.
Notification orchestration belongs in NotificationService.
"""

from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass

from email.message import EmailMessage
from email.utils import make_msgid

from app.config.settings import settings


# ==========================================================
# Email Attachment
# ==========================================================


@dataclass(frozen=True)
class EmailAttachment:
    """
    Represents a transient email attachment.

    The attachment is intentionally kept outside the database
    notification model. It exists only for the duration of
    email delivery.
    """

    filename: str
    content: bytes
    maintype: str = "application"
    subtype: str = "octet-stream"


# ==========================================================
# Email Service
# ==========================================================


class EmailService:
    """
    SMTP email delivery service.

    The service is intentionally independent of the Notification
    module so it can be reused by any application component that
    needs email delivery.

    Current implementation:
        Gmail SMTP
        smtp.gmail.com:587
        STARTTLS
    """

    # ==========================================================
    # Public API
    # ==========================================================

    async def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        attachments: list[EmailAttachment] | None = None,
    ) -> str:
        """
        Send an email through the configured SMTP server.

        Args:
            to_email:
                Recipient email address.

            subject:
                Email subject.

            body:
                Plain-text email body.

            html_body:
                Optional HTML version of the email body.

            attachments:
                Optional list of transient email attachments.

        Returns:
            SMTP Message-ID assigned to the email.

        Raises:
            ValueError:
                If the recipient email is empty.

            smtplib.SMTPException:
                If SMTP communication or authentication fails.

            OSError:
                If a network-level error occurs.
        """

        if not to_email or not to_email.strip():
            raise ValueError(
                "Recipient email address is required."
            )

        message = EmailMessage()

        message["From"] = self._from_address()
        message["To"] = to_email.strip()
        message["Subject"] = subject
        message["Message-ID"] = make_msgid()

        # ------------------------------------------------------
        # Plain-text body
        # ------------------------------------------------------

        message.set_content(
            body,
        )

        # ------------------------------------------------------
        # Optional HTML body
        # ------------------------------------------------------

        if html_body:
            message.add_alternative(
                html_body,
                subtype="html",
            )

        # ------------------------------------------------------
        # Optional Attachments
        # ------------------------------------------------------

        if attachments:
            for attachment in attachments:

                if not attachment.filename:
                    raise ValueError(
                        "Email attachment filename is required."
                    )

                if not attachment.content:
                    raise ValueError(
                        f"Email attachment '{attachment.filename}' "
                        "contains no content."
                    )

                message.add_attachment(
                    attachment.content,
                    maintype=attachment.maintype,
                    subtype=attachment.subtype,
                    filename=attachment.filename,
                )

        # ------------------------------------------------------
        # SMTP delivery
        # ------------------------------------------------------

        message_id = await asyncio.to_thread(
            self._send_smtp,
            message,
        )

        return message_id

    # ==========================================================
    # SMTP Delivery
    # ==========================================================

    def _send_smtp(
        self,
        message: EmailMessage,
    ) -> str:
        """
        Perform synchronous SMTP delivery.

        SMTP is blocking I/O, therefore this method is executed
        through asyncio.to_thread() by send_email().
        """

        with smtplib.SMTP(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            timeout=30,
        ) as smtp:

            smtp.ehlo()

            if settings.SMTP_USE_TLS:
                smtp.starttls()
                smtp.ehlo()

            smtp.login(
                settings.SMTP_USERNAME,
                settings.SMTP_PASSWORD,
            )

            smtp.send_message(
                message,
            )

        return message["Message-ID"] or ""

    # ==========================================================
    # Sender
    # ==========================================================

    @staticmethod
    def _from_address() -> str:
        """
        Build the sender address.

        Example:

            SmartPark AI <agano.dev.test@gmail.com>
        """

        return (
            f"{settings.SMTP_FROM_NAME} "
            f"<{settings.SMTP_FROM_EMAIL}>"
        )