"""
M-Pesa Daraja Client.

Enterprise-grade client responsible for communicating
with the Safaricom Daraja API.

Responsibilities
----------------
- OAuth authentication
- Access token management
- HTTP communication
- Timestamp generation
- Password generation

Business rules DO NOT belong here.

Those remain inside MpesaProvider and PaymentService.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import httpx

from app.config.settings import settings
from app.schemas.mpesa import (
    MpesaStkPushRequest,
    MpesaStkPushResponse,
)


class MpesaClient:
    """
    Enterprise-grade client for Safaricom Daraja API.
    """

    def __init__(
        self,
    ) -> None:
        """
        Initialize the client.
        """
        self.base_url = settings.MPESA_BASE_URL.rstrip("/")
        self.consumer_key = settings.MPESA_CONSUMER_KEY
        self.consumer_secret = settings.MPESA_CONSUMER_SECRET
        self.shortcode = settings.MPESA_SHORTCODE
        self.passkey = settings.MPESA_PASSKEY
        self.callback_url = settings.MPESA_CALLBACK_URL
        self.timeout = settings.MPESA_TIMEOUT_SECONDS

        #
        # Shared async HTTP client.
        #
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        #
        # OAuth token cache.
        #
        self._access_token: str | None = None
        self._token_expiry: datetime | None = None

    # ==========================================================
    # Authentication
    # ==========================================================

    async def get_access_token(
        self,
    ) -> str:
        """
        Retrieve a valid OAuth access token.

        The access token is cached until shortly before
        expiry to avoid unnecessary authentication calls.
        """
        #
        # Reuse cached token if still valid.
        #
        if (
            self._access_token is not None
            and self._token_expiry is not None
            and datetime.now(timezone.utc) < self._token_expiry
        ):
            return self._access_token

        #
        # Build Basic Authentication credentials.
        #
        credentials = f"{self.consumer_key}:{self.consumer_secret}"
        encoded_credentials = base64.b64encode(
            credentials.encode("utf-8")
        ).decode("utf-8")

        headers = {
            "Authorization": f"Basic {encoded_credentials}"
        }

        response = await self.client.get(
            "/oauth/v1/generate",
            params={
                "grant_type": "client_credentials",
            },
            headers=headers,
        )

        #
        # Raise exception for HTTP errors.
        #
        # Debugging
        print("========== OAUTH REQUEST ==========")
        print("URL:", response.request.url)
        print("HEADERS:", response.request.headers)

        print("========== OAUTH RESPONSE ==========")
        print("STATUS:", response.status_code)
        print("BODY:", response.text)

        response.raise_for_status()

        payload = response.json()

        access_token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 3599))

        if not access_token:
            raise RuntimeError(
                "Safaricom OAuth response did not "
                "contain an access token."
            )

        #
        # Cache the token.
        #
        self._access_token = access_token

        #
        # Refresh one minute before expiry.
        #
        self._token_expiry = (
            datetime.now(timezone.utc)
            + timedelta(seconds=expires_in - 60)
        )

        return self._access_token

    # ==========================================================
    # Timestamp
    # ==========================================================

    @staticmethod
    def generate_timestamp() -> str:
        """
        Generate Daraja timestamp.

        Format:
            YYYYMMDDHHMMSS
        """
        return datetime.now().strftime("%Y%m%d%H%M%S")

    # ==========================================================
    # Password
    # ==========================================================

    def generate_password(
        self,
        timestamp: str,
    ) -> str:
        """
        Generate the Daraja STK Push password.

        Password =
            Base64(
                ShortCode +
                Passkey +
                Timestamp
            )
        """
        password = f"{self.shortcode}{self.passkey}{timestamp}"
        return base64.b64encode(
            password.encode("utf-8")
        ).decode("utf-8")

    # ==========================================================
    # Authorization Header
    # ==========================================================

    async def authorization_header(
        self,
    ) -> dict[str, str]:
        """
        Build Authorization header.
        """
        token = await self.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
        }

    # ==========================================================
    # Generic Request Pipeline
    # ==========================================================

    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict:
        """
        Execute an authenticated request against
        the Daraja API.
        """
        headers = await self.authorization_header()

        # For Debugging
        response = await self.client.request(
            method=method,
            url=endpoint,
            headers=headers,
            json=json,
            params=params,
        )

        # Debugging:
        print("\n========== MPESA REQUEST ==========")
        print("URL:", response.request.url)
        print("METHOD:", response.request.method)
        print("HEADERS:", response.request.headers)

        if json is not None:
            print("JSON:", json)

        print("\n========== MPESA RESPONSE ==========")
        print("STATUS:", response.status_code)
        print("BODY:", response.text)

        response.raise_for_status()

        return response.json()

    # ==========================================================
    # HTTP GET
    # ==========================================================

    async def get(
        self,
        endpoint: str,
        *,
        params: dict | None = None,
    ) -> dict:
        """
        Execute an authenticated GET request.
        """
        return await self.request(
            "GET",
            endpoint,
            params=params,
        )

    # ==========================================================
    # HTTP POST
    # ==========================================================

    async def post(
        self,
        endpoint: str,
        *,
        json: dict,
    ) -> dict:
        """
        Execute an authenticated POST request.
        """
        return await self.request(
            "POST",
            endpoint,
            json=json,
        )

    # ==========================================================
    # STK Push
    # ==========================================================

    async def stk_push(
        self,
        request: MpesaStkPushRequest,
    ) -> MpesaStkPushResponse:
        """
        Initiate an M-Pesa STK Push.

        Parameters
        ----------
        request:
            STK Push request payload.

        Returns
        -------
        MpesaStkPushResponse
            Parsed Daraja response.
        """
        timestamp = self.generate_timestamp()
        password = self.generate_password(timestamp)

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": request.amount,
            "PartyA": request.phone_number,
            "PartyB": self.shortcode,
            "PhoneNumber": request.phone_number,
            "CallBackURL": self.callback_url,
            "AccountReference": request.account_reference,
            "TransactionDesc": request.transaction_desc,
        }

        # ======================================================
        # Debug
        # ======================================================
        print("\n========== STK PUSH ==========")
        print("Business ShortCode :", self.shortcode)
        print("Phone Number       :", request.phone_number)
        print("Amount             :", request.amount)
        print("Account Reference  :", request.account_reference)
        print("Callback URL       :", self.callback_url)
        print("Timestamp          :", timestamp)
        # Don't print the full password.
        print("Password Length    :", len(password))
        print("================================\n")

        response = await self.post(
            "/mpesa/stkpush/v1/processrequest",
            json=payload,
        )

        return MpesaStkPushResponse.model_validate(response)

    # ==========================================================
    # STK Push Query
    # ==========================================================

    async def stk_query(
        self,
        timestamp: str,
        *,
        checkout_request_id: str,
    ) -> dict:
        """
        Query the status of an STK Push request.
        """
        timestamp = self.generate_timestamp()
        password = self.generate_password(timestamp)

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }

        return await self.post(
            "/mpesa/stkpushquery/v1/query",
            json=payload,
        )

    # ==========================================================
    # Health Check
    # ==========================================================

    async def health_check(
        self,
    ) -> bool:
        """
        Verify connectivity with Daraja.

        Returns
        -------
        bool
        """
        try:
            await self.get_access_token()
            return True
        except Exception:
            return False

    # ==========================================================
    # Cleanup
    # ==========================================================

    async def close(
        self,
    ) -> None:
        """
        Close the shared HTTP client.
        """
        await self.client.aclose()

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(
        self,
    ) -> str:
        return (
            f"{self.__class__.__name__}"
            f"(base_url={self.base_url})"
        )