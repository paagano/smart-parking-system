from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.exceptions.auth import (
    AuthenticationException,
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    PhoneAlreadyExistsException,
)


# ==========================================================
# Generic Application Exceptions
# ==========================================================


class NotFoundException(Exception):
    """
    Raised when a requested resource cannot be found.
    """

    def __init__(self, detail: str = "Resource not found."):
        self.detail = detail


class BadRequestException(Exception):
    """
    Raised when a request is invalid.
    """

    def __init__(self, detail: str = "Bad request."):
        self.detail = detail


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register application-wide exception handlers.
    """

    # ==========================================================
    # Authentication
    # ==========================================================

    @app.exception_handler(InvalidCredentialsException)
    async def invalid_credentials_handler(
        request: Request,
        exc: InvalidCredentialsException,
    ):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "detail": "Invalid email or password."
            },
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    @app.exception_handler(EmailAlreadyExistsException)
    async def email_exists_handler(
        request: Request,
        exc: EmailAlreadyExistsException,
    ):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Email address is already registered."
            },
        )

    @app.exception_handler(PhoneAlreadyExistsException)
    async def phone_exists_handler(
        request: Request,
        exc: PhoneAlreadyExistsException,
    ):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Phone number is already registered."
            },
        )

    @app.exception_handler(AuthenticationException)
    async def authentication_exception_handler(
        request: Request,
        exc: AuthenticationException,
    ):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "detail": "Authentication failed."
            },
        )

    # ==========================================================
    # Generic Application Exceptions
    # ==========================================================

    @app.exception_handler(NotFoundException)
    async def not_found_exception_handler(
        request: Request,
        exc: NotFoundException,
    ):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "detail": exc.detail,
            },
        )

    @app.exception_handler(BadRequestException)
    async def bad_request_exception_handler(
        request: Request,
        exc: BadRequestException,
    ):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "detail": exc.detail,
            },
        )