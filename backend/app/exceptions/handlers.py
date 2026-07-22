from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.exceptions.auth import (
    AuthenticationException,
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    PhoneAlreadyExistsException,
)


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register application-wide exception handlers.
    """

    @app.exception_handler(
        InvalidCredentialsException
    )
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

    @app.exception_handler(
        EmailAlreadyExistsException
    )
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

    @app.exception_handler(
        PhoneAlreadyExistsException
    )
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

    @app.exception_handler(
        AuthenticationException
    )
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