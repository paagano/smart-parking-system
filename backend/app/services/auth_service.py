from __future__ import annotations

import os
from datetime import datetime
from io import BytesIO
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.core.security import (
    create_email_verification_token,
    decode_email_verification_token,
    create_password_reset_token,
    decode_password_reset_token,
    hash_password,
    verify_password,
)
from app.exceptions.auth import (
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    InvalidCurrentPasswordException,
    PhoneAlreadyExistsException,
)
from app.models.user import User
from app.repositories.revoked_token_repository import (
    RevokedTokenRepository,
)
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    ChangePasswordRequest,
    UserCreate,
    UserUpdate,
)
from app.services.wallet_service import WalletService
from app.services.email_service import EmailService
from app.storage.base import StorageService


class AuthService:
    """
    Handles authentication-related business logic.
    """

    def __init__(
        self,
        user_repository: UserRepository,
        wallet_service: WalletService,
        revoked_token_repository: RevokedTokenRepository,
        storage_service: StorageService,
        email_service: EmailService,
    ) -> None:
        self.user_repository = user_repository
        self.wallet_service = wallet_service
        self.revoked_token_repository = revoked_token_repository
        self.storage_service = storage_service
        self.email_service = email_service

    # ==========================================================
    # User Registration
    # ==========================================================

    def build_user(
        self,
        user_data: UserCreate,
    ) -> User:
        """
        Build a User entity.
        """

        return User(
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            email=user_data.email,
            phone_number=user_data.phone_number,
            password_hash=hash_password(
                user_data.password,
            ),
        )

    async def register_user(
        self,
        user_data: UserCreate,
    ) -> User:
        """
        Register a new user and automatically provision
        a wallet for the customer.
        """

        #
        # Ensure email is unique.
        #
        if await self.user_repository.get_by_email(
            user_data.email,
        ):
            raise EmailAlreadyExistsException()

        #
        # Ensure phone number is unique.
        #
        if await self.user_repository.get_by_phone(
            user_data.phone_number,
        ):
            raise PhoneAlreadyExistsException()

        #
        # Build the User entity.
        #
        user = self.build_user(
            user_data,
        )

        #
        # Persist the user.
        #
        await self.user_repository.save(
            user,
        )

        #
        # Commit the user so the database generates
        # the primary key.
        #
        await self.user_repository.commit()

        #
        # Refresh to populate generated fields.
        #
        await self.user_repository.refresh(
            user,
        )

        #
        # Automatically create a wallet for every
        # newly registered customer.
        #
        await self.wallet_service.create_wallet(
            customer_id=user.id,
        )

        # Send the email-verification message after the user has
        # been committed and assigned a database ID. Email delivery
        # failure must not undo an otherwise successful registration;
        # the verification message can be requested again later.
        try:
            await self.send_email_verification(user)
        except Exception:
            pass

        return user

    # ==========================================================
    # Email Verification
    # ==========================================================

    async def send_email_verification(
        self,
        user: User,
    ) -> None:
        """
        Send an email-verification message to the user's current
        email address.

        The verification token is a purpose-specific signed JWT and
        is valid for 24 hours.
        """

        if not user.email:
            raise ValueError(
                "User does not have an email address."
            )

        token = create_email_verification_token(
            user_id=user.id,
            email=user.email,
        )

        frontend_url = os.getenv(
            "FRONTEND_URL",
            "http://localhost:5173",
        ).rstrip("/")

        verification_url = (
            f"{frontend_url}/verify-email?token={token}"
        )

        subject = "Verify your SmartPark AI email address"

        body = (
            f"Hello {user.first_name},\n\n"
            "Welcome to SmartPark AI. Your account has been created "
            "successfully, and we just need to confirm that this email "
            "address belongs to you.\n\n"
            "Verify your email address by opening the link below:\n\n"
            f"{verification_url}\n\n"
            "This secure verification link expires in 24 hours.\n\n"
            "If you did not create a SmartPark AI account, you can safely "
            "ignore this message.\n\n"
            "Regards,\n"
            "SmartPark AI\n"
            "Smart parking. Smarter journeys."
        )

        html_body = f"""
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta name="color-scheme" content="light">
            <meta name="supported-color-schemes" content="light">
            <title>Verify your SmartPark AI email</title>
          </head>

          <body style="margin:0;padding:0;width:100%;background:#f4f7fa;font-family:Arial,Helvetica,sans-serif;color:#10243a;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">

            <!-- Preheader -->
            <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
              Confirm your email address to complete your SmartPark AI account setup.
            </div>

            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                   style="width:100%;margin:0;padding:0;background:#f4f7fa;">
              <tr>
                <td align="center" style="padding:24px 12px;">

                  <!-- Responsive email card -->
                  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                         style="width:100%;max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;overflow:hidden;">

                    <!-- Navy brand header -->
                    <tr>
                      <td style="background:#071b2f;padding:28px 24px;text-align:center;">
                        <div style="font-size:25px;line-height:32px;font-weight:700;color:#ffffff;">
                          SmartPark <span style="color:#16c784;">AI</span>
                        </div>
                        <div style="margin-top:5px;font-size:11px;line-height:17px;letter-spacing:1.3px;text-transform:uppercase;color:#b9c8d8;">
                          SMART PARKING. SMARTER JOURNEYS.
                        </div>
                      </td>
                    </tr>

                    <!-- Main content -->
                    <tr>
                      <td style="padding:34px 28px 30px;">

                        <!-- Verification icon -->
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center"
                               style="margin:0 auto 20px;">
                          <tr>
                            <td align="center" valign="middle"
                                style="width:60px;height:60px;border-radius:50%;background:#e9f9f3;color:#087a55;font-size:28px;font-weight:700;line-height:60px;">
                              &#10003;
                            </td>
                          </tr>
                        </table>

                        <h1 style="margin:0;text-align:center;font-size:26px;line-height:34px;font-weight:700;color:#071b2f;">
                          Verify your email address
                        </h1>

                        <p style="margin:12px auto 0;max-width:460px;text-align:center;font-size:15px;line-height:24px;color:#5f7185;">
                          Hello {user.first_name}, welcome to <strong style="color:#071b2f;">SmartPark AI</strong>.
                          Please confirm your email address to complete your account setup.
                        </p>

                        <!-- CTA -->
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center"
                               style="margin:28px auto 24px;">
                          <tr>
                            <td align="center" style="border-radius:8px;background:#075985;">
                              <a href="{verification_url}"
                                 style="display:inline-block;padding:13px 27px;border-radius:8px;background:#075985;color:#ffffff;text-decoration:none;font-size:15px;line-height:20px;font-weight:700;">
                                Verify My Email
                              </a>
                            </td>
                          </tr>
                        </table>

                        <!-- Expiry/security notice -->
                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                               style="width:100%;background:#f3f7fb;border:1px solid #d9e4ee;border-radius:9px;">
                          <tr>
                            <td style="padding:14px 15px;">
                              <div style="font-size:13px;line-height:20px;color:#43566b;">
                                <strong style="color:#071b2f;">Verification link expires in 24 hours.</strong><br>
                                For your security, please complete verification before the link expires.
                              </div>
                            </td>
                          </tr>
                        </table>

                        <!-- Fallback link -->
                        <p style="margin:24px 0 7px;font-size:12px;line-height:19px;color:#718398;">
                          If the button does not work, copy and paste this link into your browser:
                        </p>

                        <div style="max-width:100%;overflow-wrap:anywhere;word-break:break-word;font-size:11px;line-height:18px;color:#075985;">
                          {verification_url}
                        </div>

                        <!-- Security note -->
                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                               style="width:100%;margin-top:25px;border-top:1px solid #e5ebf1;">
                          <tr>
                            <td style="padding-top:20px;">
                              <p style="margin:0;font-size:12px;line-height:19px;color:#718398;">
                                <strong style="color:#43566b;">Didn't create this account?</strong><br>
                                You can safely ignore this email. No action is required.
                              </p>
                            </td>
                          </tr>
                        </table>

                      </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                      <td style="background:#f8fafc;border-top:1px solid #e5ebf1;padding:20px 24px;text-align:center;">
                        <div style="font-size:13px;line-height:20px;color:#607286;">
                          Regards,<br>
                          <strong style="color:#071b2f;">SmartPark AI</strong>
                        </div>
                        <div style="margin-top:7px;font-size:10px;line-height:16px;color:#94a3b8;">
                          This is an automated security message. Please do not reply to this email.
                        </div>
                      </td>
                    </tr>

                  </table>

                </td>
              </tr>
            </table>

          </body>
        </html>
        """

        await self.email_service.send_email(
            to_email=user.email,
            subject=subject,
            body=body,
            html_body=html_body,
        )

    async def verify_email(
        self,
        token: str,
    ) -> User:
        """
        Validate an email-verification token and mark the
        corresponding user as verified.
        """

        try:
            payload = decode_email_verification_token(token)
        except Exception as exc:
            raise ValueError(
                "Invalid or expired email verification token."
            ) from exc

        user_id = payload.get("uid")
        email = payload.get("sub")

        if user_id is None or email is None:
            raise ValueError(
                "Invalid email verification token."
            )

        try:
            user_id = int(user_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Invalid email verification token."
            ) from exc

        if not isinstance(email, str) or not email.strip():
            raise ValueError(
                "Invalid email verification token."
            )

        managed_user = await self.user_repository.get_by_id(
            user_id,
        )

        if managed_user is None:
            raise InvalidCredentialsException()

        # The token is valid only for the email address that was
        # actually sent the verification message.
        if managed_user.email != email:
            raise ValueError(
                "Email verification token does not match the "
                "user's current email address."
            )

        managed_user.is_verified = True

        await self.user_repository.commit()

        await self.user_repository.refresh(
            managed_user,
        )

        return managed_user

    async def resend_email_verification(
        self,
        user: User,
    ) -> None:
        """
        Resend an email-verification message to an unverified user.
        """

        managed_user = await self.user_repository.get_by_id(
            user.id,
        )

        if managed_user is None:
            raise InvalidCredentialsException()

        if managed_user.is_verified:
            return

        await self.send_email_verification(
            managed_user,
        )

    # ==========================================================
    # Password Reset
    # ==========================================================

    async def request_password_reset(
        self,
        email: str,
    ) -> None:
        """
        Request a password reset for an account.

        The method intentionally performs no externally visible
        action when the email does not belong to an account or
        the account is inactive. This prevents account-enumeration
        through the password-reset endpoint.

        Password-reset links use a purpose-specific signed JWT
        that expires after one hour.
        """

        user = await self.user_repository.get_by_email(
            email.strip(),
        )

        if user is None:
            return

        if not user.is_active:
            return

        token = create_password_reset_token(
            user_id=user.id,
            email=user.email,
            token_version=user.token_version,
        )

        frontend_url = os.getenv(
            "FRONTEND_URL",
            "http://localhost:5173",
        ).rstrip("/")

        reset_url = (
            f"{frontend_url}/reset-password?token={token}"
        )

        subject = "Reset your SmartPark AI password"

        body = (
            f"Hello {user.first_name},\n\n"
            "We received a request to reset the password for your "
            "SmartPark AI account.\n\n"
            "Reset your password by opening the link below:\n\n"
            f"{reset_url}\n\n"
            "This secure password-reset link expires in 1 hour and "
            "can only be used once.\n\n"
            "If you did not request a password reset, you can safely "
            "ignore this message. Your current password will remain unchanged.\n\n"
            "Regards,\n"
            "SmartPark AI\n"
            "Smart parking. Smarter journeys."
        )

        html_body = f"""
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta name="color-scheme" content="light">
            <meta name="supported-color-schemes" content="light">
            <title>Reset your SmartPark AI password</title>
          </head>

          <body style="margin:0;padding:0;width:100%;background:#f4f7fa;font-family:Arial,Helvetica,sans-serif;color:#10243a;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">

            <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
              Reset your SmartPark AI password securely.
            </div>

            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                   style="width:100%;margin:0;padding:0;background:#f4f7fa;">
              <tr>
                <td align="center" style="padding:24px 12px;">

                  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                         style="width:100%;max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;overflow:hidden;">

                    <tr>
                      <td style="background:#071b2f;padding:28px 24px;text-align:center;">
                        <div style="font-size:25px;line-height:32px;font-weight:700;color:#ffffff;">
                          SmartPark <span style="color:#16c784;">AI</span>
                        </div>
                        <div style="margin-top:5px;font-size:11px;line-height:17px;letter-spacing:1.3px;text-transform:uppercase;color:#b9c8d8;">
                          SMART PARKING. SMARTER JOURNEYS.
                        </div>
                      </td>
                    </tr>

                    <tr>
                      <td style="padding:34px 28px 30px;">

                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center"
                               style="margin:0 auto 20px;">
                          <tr>
                            <td align="center" valign="middle"
                                style="width:60px;height:60px;border-radius:50%;background:#e9f9f3;color:#087a55;font-size:28px;font-weight:700;line-height:60px;">
                              &#128273;
                            </td>
                          </tr>
                        </table>

                        <h1 style="margin:0;text-align:center;font-size:26px;line-height:34px;font-weight:700;color:#071b2f;">
                          Reset your password
                        </h1>

                        <p style="margin:12px auto 0;max-width:460px;text-align:center;font-size:15px;line-height:24px;color:#5f7185;">
                          Hello {user.first_name}, we received a request to reset your
                          <strong style="color:#071b2f;">SmartPark AI</strong> password.
                        </p>

                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center"
                               style="margin:28px auto 24px;">
                          <tr>
                            <td align="center" style="border-radius:8px;background:#075985;">
                              <a href="{reset_url}"
                                 style="display:inline-block;padding:13px 27px;border-radius:8px;background:#075985;color:#ffffff;text-decoration:none;font-size:15px;line-height:20px;font-weight:700;">
                                Reset My Password
                              </a>
                            </td>
                          </tr>
                        </table>

                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                               style="width:100%;background:#f3f7fb;border:1px solid #d9e4ee;border-radius:9px;">
                          <tr>
                            <td style="padding:14px 15px;">
                              <div style="font-size:13px;line-height:20px;color:#43566b;">
                                <strong style="color:#071b2f;">Reset link expires in 1 hour.</strong><br>
                                For your security, the link can only be used once.
                              </div>
                            </td>
                          </tr>
                        </table>

                        <p style="margin:24px 0 7px;font-size:12px;line-height:19px;color:#718398;">
                          If the button does not work, copy and paste this link into your browser:
                        </p>

                        <div style="max-width:100%;overflow-wrap:anywhere;word-break:break-word;font-size:11px;line-height:18px;color:#075985;">
                          {reset_url}
                        </div>

                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                               style="width:100%;margin-top:25px;border-top:1px solid #e5ebf1;">
                          <tr>
                            <td style="padding-top:20px;">
                              <p style="margin:0;font-size:12px;line-height:19px;color:#718398;">
                                <strong style="color:#43566b;">Didn't request this?</strong><br>
                                You can safely ignore this email. Your current password will remain unchanged.
                              </p>
                            </td>
                          </tr>
                        </table>

                      </td>
                    </tr>

                    <tr>
                      <td style="background:#f8fafc;border-top:1px solid #e5ebf1;padding:20px 24px;text-align:center;">
                        <div style="font-size:13px;line-height:20px;color:#607286;">
                          Regards,<br>
                          <strong style="color:#071b2f;">SmartPark AI</strong>
                        </div>
                        <div style="margin-top:7px;font-size:10px;line-height:16px;color:#94a3b8;">
                          This is an automated security message. Please do not reply to this email.
                        </div>
                      </td>
                    </tr>

                  </table>

                </td>
              </tr>
            </table>

          </body>
        </html>
        """

        #
        # Do not expose whether an account exists if email delivery
        # fails. Registration/account functionality remains unaffected.
        #
        try:
            await self.email_service.send_email(
                to_email=user.email,
                subject=subject,
                body=body,
                html_body=html_body,
            )
        except Exception:
            pass

    async def reset_password(
        self,
        token: str,
        new_password: str,
    ) -> None:
        """
        Reset a user's password using a valid password-reset token.

        The reset token is validated against the user's current
        email address and token_version. Incrementing token_version
        after a successful reset invalidates the reset token and
        all previously issued access tokens.
        """

        try:
            payload = decode_password_reset_token(token)
        except Exception as exc:
            raise ValueError(
                "Invalid or expired password reset token."
            ) from exc

        user_id = payload.get("uid")
        email = payload.get("sub")
        token_version = payload.get("token_version")

        if (
            user_id is None
            or email is None
            or token_version is None
        ):
            raise ValueError(
                "Invalid password reset token."
            )

        try:
            user_id = int(user_id)
            token_version = int(token_version)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Invalid password reset token."
            ) from exc

        if not isinstance(email, str) or not email.strip():
            raise ValueError(
                "Invalid password reset token."
            )

        managed_user = await self.user_repository.get_by_id(
            user_id,
        )

        if managed_user is None:
            raise ValueError(
                "Invalid or expired password reset token."
            )

        if managed_user.email != email:
            raise ValueError(
                "Invalid or expired password reset token."
            )

        if managed_user.token_version != token_version:
            raise ValueError(
                "Invalid or expired password reset token."
            )

        #
        # Store the newly hashed password.
        #
        managed_user.password_hash = hash_password(
            new_password,
        )

        #
        # Increment token_version so:
        #   1. The reset token cannot be reused.
        #   2. All previously issued access tokens are invalidated.
        #
        managed_user.token_version += 1

        await self.user_repository.commit()

        await self.user_repository.refresh(
            managed_user,
        )

    # ==========================================================
    # Authentication
    # ==========================================================

    async def authenticate_user(
        self,
        email: str,
        password: str,
    ) -> User:
        """
        Authenticate a user.
        """

        user = await self.user_repository.get_by_email(
            email,
        )

        if user is None:
            raise InvalidCredentialsException()

        if not verify_password(
            password,
            user.password_hash,
        ):
            raise InvalidCredentialsException()

        return user

    # ==========================================================
    # Logout
    # ==========================================================

    async def logout(
        self,
        token_jti: str,
        token_expires_at: datetime,
    ) -> None:
        """
        Revoke the JWT used for logout.

        The operation is intentionally idempotent. If the token
        has already been revoked, no duplicate revoked-token
        record is created.
        """

        #
        # Avoid creating a duplicate JTI record if logout is
        # submitted more than once for the same token.
        #
        if await self.revoked_token_repository.is_revoked(
            token_jti,
        ):
            return

        #
        # Store the JWT identifier and its original expiration
        # time so the token remains unusable for the remainder
        # of its lifetime.
        #
        await self.revoked_token_repository.revoke(
            jti=token_jti,
            expires_at=token_expires_at,
        )

        #
        # Commit the revocation.
        #
        await self.user_repository.commit()

    # ==========================================================
    # Logout All Sessions
    # ==========================================================

    async def logout_all(
        self,
        user: User,
    ) -> None:
        """
        Invalidate all access tokens currently issued to the user.

        This is implemented by incrementing the user's token version.
        Any JWT issued with the previous token version will subsequently
        be rejected by the authentication dependency.

        A new login will receive the updated token version and will
        therefore remain valid.
        """

        #
        # Retrieve the authenticated user through the
        # repository/session used by this service.
        #
        managed_user = await self.user_repository.get_by_id(
            user.id,
        )

        if managed_user is None:
            raise InvalidCredentialsException()

        #
        # Increment the token version.
        #
        # This immediately invalidates every previously issued
        # JWT belonging to this user.
        #
        managed_user.token_version += 1

        #
        # Persist the new token version.
        #
        await self.user_repository.commit()

        #
        # Refresh the managed instance so it reflects the
        # latest database state.
        #
        await self.user_repository.refresh(
            managed_user,
        )

    # ==========================================================
    # Profile
    # ==========================================================

    async def update_user_profile(
        self,
        user: User,
        user_data: UserUpdate,
    ) -> User:
        """
        Update the authenticated user's editable profile fields.

        Email, role, activation status, verification status,
        and password are intentionally not editable through
        this operation.
        """

        #
        # Retrieve the authenticated user through the
        # repository/session used by this service.
        #
        managed_user = await self.user_repository.get_by_id(
            user.id,
        )

        if managed_user is None:
            raise InvalidCredentialsException()

        #
        # Extract only fields supplied by the client.
        #
        update_data = user_data.model_dump(
            exclude_unset=True,
        )

        #
        # Ensure the new phone number is unique.
        #
        if "phone_number" in update_data:
            phone_number = update_data["phone_number"]

            if phone_number is not None:
                existing_user = (
                    await self.user_repository.get_by_phone(
                        phone_number,
                    )
                )

                if (
                    existing_user is not None
                    and existing_user.id != managed_user.id
                ):
                    raise PhoneAlreadyExistsException()

        #
        # Apply the permitted profile changes to the
        # session-managed User instance.
        #
        for field, value in update_data.items():
            setattr(
                managed_user,
                field,
                value,
            )

        #
        # SQLAlchemy is already tracking managed_user,
        # so no repository.save() is required here.
        #
        await self.user_repository.commit()

        #
        # Refresh to return the latest database state.
        #
        await self.user_repository.refresh(
            managed_user,
        )

        return managed_user

    # ==========================================================
    # Profile Picture
    # ==========================================================

    async def upload_profile_picture(
        self,
        user: User,
        file: UploadFile,
    ) -> User:
        """
        Upload or replace the authenticated user's profile picture.

        The image is validated using Pillow before it is stored.

        The dedicated profile-picture StorageService is injected
        into AuthService so profile-picture files remain isolated
        from receipt storage.
        """

        #
        # Retrieve the authenticated user through the
        # repository/session used by this service.
        #
        managed_user = await self.user_repository.get_by_id(
            user.id,
        )

        if managed_user is None:
            raise InvalidCredentialsException()

        #
        # Read the uploaded file.
        #
        content = await file.read()

        if not content:
            raise ValueError(
                "Profile picture cannot be empty."
            )

        #
        # Enforce a 5 MB maximum upload size.
        #
        max_file_size = 5 * 1024 * 1024

        if len(content) > max_file_size:
            raise ValueError(
                "Profile picture must not exceed 5 MB."
            )

        #
        # Validate the actual image content rather than
        # trusting the client-provided MIME type.
        #
        try:
            image = Image.open(
                BytesIO(content),
            )

            image.verify()

            image_format = image.format

        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
        ) as exc:
            raise ValueError(
                "Uploaded file is not a valid image."
            ) from exc

        #
        # Only allow formats appropriate for profile pictures.
        #
        allowed_formats = {
            "JPEG": ("jpg", "image/jpeg"),
            "PNG": ("png", "image/png"),
            "WEBP": ("webp", "image/webp"),
        }

        if image_format not in allowed_formats:
            raise ValueError(
                "Unsupported profile picture format. "
                "Allowed formats are JPEG, PNG, and WEBP."
            )

        extension, content_type = allowed_formats[
            image_format
        ]

        #
        # Generate a unique filename so profile-picture
        # uploads never collide.
        #
        filename = f"{uuid4().hex}.{extension}"

        #
        # Keep each user's profile pictures isolated.
        #
        storage_path = (
            f"profile_pictures/"
            f"{managed_user.id}/"
            f"{filename}"
        )

        #
        # Preserve the previous storage reference before
        # replacing it.
        #
        previous_picture_reference = (
            managed_user.profile_picture_url
        )

        #
        # Store the new profile picture.
        #
        stored_path = await self.storage_service.upload(
            path=storage_path,
            content=content,
            content_type=content_type,
            overwrite=False,
        )

        #
        # Generate the URL/reference exposed through the
        # user profile.
        #
        picture_url = await self.storage_service.get_url(
            path=stored_path,
        )

        #
        # Store the generated profile-picture URL.
        #
        managed_user.profile_picture_url = picture_url

        #
        # Commit the database change.
        #
        await self.user_repository.commit()

        #
        # Refresh the managed instance so the returned User
        # contains the latest persisted state.
        #
        await self.user_repository.refresh(
            managed_user,
        )

        #
        # Remove the previous profile picture only after the
        # new picture has been successfully stored and the
        # database has been updated.
        #
        if previous_picture_reference:
            previous_picture_path = (
                self._extract_profile_picture_storage_path(
                    previous_picture_reference,
                )
            )

            if previous_picture_path:
                try:
                    await self.storage_service.delete(
                        path=previous_picture_path,
                    )
                except (
                    FileNotFoundError,
                    ValueError,
                ):
                    #
                    # The database already points to the new
                    # picture, so failure to remove an old
                    # file must not fail the upload operation.
                    #
                    pass

        return managed_user

    # ==========================================================
    # Delete Profile Picture
    # ==========================================================

    async def delete_profile_picture(
        self,
        user: User,
    ) -> User:
        """
        Delete the authenticated user's profile picture.

        The storage object is removed first, after which the
        user's profile_picture_url is cleared from the database.

        If no profile picture is currently configured, the
        authenticated user's current profile is returned unchanged.
        """

        #
        # Retrieve the authenticated user through the
        # repository/session used by this service.
        #
        managed_user = await self.user_repository.get_by_id(
            user.id,
        )

        if managed_user is None:
            raise InvalidCredentialsException()

        #
        # Nothing to delete if the user has no profile picture.
        #
        if not managed_user.profile_picture_url:
            return managed_user

        #
        # Convert the stored URL/reference into the
        # storage-relative object path.
        #
        profile_picture_path = (
            self._extract_profile_picture_storage_path(
                managed_user.profile_picture_url,
            )
        )

        #
        # If the stored reference cannot safely be resolved,
        # do not attempt to delete an arbitrary storage object.
        #
        if profile_picture_path:
            try:
                await self.storage_service.delete(
                    path=profile_picture_path,
                )
            except FileNotFoundError:
                #
                # The storage object is already absent, so the
                # database reference can still safely be cleared.
                #
                pass

        #
        # Clear the profile-picture reference from the database.
        #
        managed_user.profile_picture_url = None

        #
        # Persist the database change.
        #
        await self.user_repository.commit()

        #
        # Refresh the managed instance so the returned User
        # reflects the current database state.
        #
        await self.user_repository.refresh(
            managed_user,
        )

        return managed_user

    # ==========================================================
    # Profile Picture Storage Path Helper
    # ==========================================================

    @staticmethod
    def _extract_profile_picture_storage_path(
        reference: str,
    ) -> str | None:
        """
        Convert a stored profile-picture URL/reference back
        into the storage-relative path expected by
        StorageService.delete().

        Supported references include:

            profile_pictures/<user_id>/<filename>

        LocalStorage URL:

            /storage/profile_pictures/<user_id>/<filename>

        Supabase public URL:

            https://<project>.supabase.co/
            storage/v1/object/public/profile-pictures/
            profile_pictures/<user_id>/<filename>

        Returns:
            Storage-relative profile-picture path, or None when
            the reference cannot safely be interpreted as a
            profile-picture storage path.
        """

        if not reference:
            return None

        #
        # Already a storage-relative path.
        #
        if reference.startswith(
            "profile_pictures/",
        ):
            return reference

        #
        # LocalStorage get_url() returns:
        #
        #     /storage/<storage-relative-path>
        #
        local_prefix = "/storage/"

        if reference.startswith(local_prefix):
            path = reference[len(local_prefix):]

            if path.startswith(
                "profile_pictures/",
            ):
                return path

            return None

        #
        # Supabase public URL.
        #
        # Example:
        #
        # https://<project>.supabase.co/storage/v1/object/
        # public/profile-pictures/profile_pictures/6/example.jpg
        #
        try:
            parsed_url = urlparse(
                reference,
            )
        except ValueError:
            return None

        #
        # Only process HTTP(S) URLs.
        #
        if parsed_url.scheme not in {
            "http",
            "https",
        }:
            return None

        #
        # The URL must point specifically to the public
        # profile-pictures bucket.
        #
        expected_prefix = (
            "storage/v1/object/public/"
            "profile-pictures/"
        )

        url_path = parsed_url.path.lstrip("/")

        if not url_path.startswith(
            expected_prefix,
        ):
            return None

        #
        # Extract the storage-relative object path.
        #
        path = url_path[
            len(expected_prefix):
        ]

        #
        # Ensure the resulting path belongs to the
        # profile-picture namespace.
        #
        if not path.startswith(
            "profile_pictures/",
        ):
            return None

        return path

    # ==========================================================
    # Password
    # ==========================================================

    async def change_password(
        self,
        user: User,
        password_data: ChangePasswordRequest,
        token_jti: str,
        token_expires_at: datetime,
    ) -> None:
        """
        Change the authenticated user's password and revoke
        the JWT used to perform the password change.

        The current password must be verified before the
        new password is stored.

        The new password must also be different from
        the current password.

        Password-strength validation is handled by the
        ChangePasswordRequest schema.

        The current JWT is revoked after the password change
        so that it can no longer be used for authenticated
        requests.
        """

        #
        # Retrieve the authenticated user through the
        # repository/session used by this service.
        #
        managed_user = await self.user_repository.get_by_id(
            user.id,
        )

        if managed_user is None:
            raise InvalidCredentialsException()

        #
        # Verify the user's existing password.
        #
        if not verify_password(
            password_data.current_password,
            managed_user.password_hash,
        ):
            raise InvalidCurrentPasswordException()

        #
        # Ensure the new password is different from
        # the current password.
        #
        if verify_password(
            password_data.new_password,
            managed_user.password_hash,
        ):
            raise ValueError(
                "New password must be different from the current password."
            )

        #
        # Hash the new password before storing it.
        #
        managed_user.password_hash = hash_password(
            password_data.new_password,
        )

        #
        # Revoke the JWT that was used to perform the
        # password change.
        #
        await self.revoked_token_repository.revoke(
            jti=token_jti,
            expires_at=token_expires_at,
        )

        #
        # Commit both the password change and token
        # revocation together.
        #
        await self.user_repository.commit()

        #
        # Refresh the managed instance after the database
        # transaction has completed.
        #
        await self.user_repository.refresh(
            managed_user,
        )