"""HTTP client for the Alectra scraper sidecar service."""

from __future__ import annotations

import logging
from datetime import date

import aiohttp

_LOGGER = logging.getLogger(__name__)
SIDECAR_TIMEOUT = aiohttp.ClientTimeout(total=120)


class AlectraAuthError(Exception):
    """Raised when portal credentials are rejected."""


class AlectraConnectionError(Exception):
    """Raised when the sidecar or portal cannot be reached."""


class AlectraPortalClient:
    def __init__(
        self,
        sidecar_url: str,
        account_name: str,
        account_number: str,
        phone_number: str,
        session: aiohttp.ClientSession | None = None,
        sidecar_token: str = "",
    ) -> None:
        self._url = sidecar_url.rstrip("/") + "/fetch"
        self._account_name = account_name
        self._account_number = account_number
        self._phone_number = phone_number
        self._session = session
        self._token = sidecar_token

    async def fetch_usage_data(self, start_date: date, end_date: date) -> str:
        payload = {
            "account_name": self._account_name,
            "account_number": self._account_number,
            "phone_number": self._phone_number,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        try:
            if self._session:
                return await self._do_fetch(self._session, payload)
            async with aiohttp.ClientSession(timeout=SIDECAR_TIMEOUT) as session:
                return await self._do_fetch(session, payload)
        except (AlectraAuthError, AlectraConnectionError):
            raise
        except aiohttp.ClientError as err:
            raise AlectraConnectionError(f"Cannot reach sidecar: {err}") from err

    async def _do_fetch(self, session: aiohttp.ClientSession, payload: dict) -> str:
        headers = {"X-Sidecar-Token": self._token} if self._token else {}
        async with session.post(self._url, json=payload, headers=headers, timeout=SIDECAR_TIMEOUT) as resp:
            if resp.status == 200:
                data = await resp.json()
                if not isinstance(data, dict) or "xml" not in data:
                    raise AlectraConnectionError(
                        "Sidecar returned 200 but response is missing 'xml' key"
                    )
                return data["xml"]
            # Sidecar returns {"detail": {"error": "...", "message": "..."}} on errors
            try:
                body = await resp.json()
                detail = body.get("detail", {})
                if isinstance(detail, dict):
                    message = detail.get("message", f"Sidecar returned {resp.status}")
                else:
                    message = str(detail)
            except (aiohttp.ContentTypeError, ValueError) as parse_err:
                _LOGGER.debug("Could not parse sidecar error body: %s", parse_err)
                message = f"Sidecar returned {resp.status}"
            if resp.status == 401:
                raise AlectraAuthError(message)
            raise AlectraConnectionError(message)
