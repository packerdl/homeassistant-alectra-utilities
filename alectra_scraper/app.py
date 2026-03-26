"""FastAPI sidecar exposing the Alectra scraper over HTTP."""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
from datetime import date

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from scraper import AlectraAuthError, AlectraConnectionError, AlectraScraper

_LOGGER = logging.getLogger(__name__)

_SIDECAR_TOKEN = os.environ.get("SIDECAR_TOKEN", "")


async def _verify_token(x_sidecar_token: str = Header(default="")) -> None:
    """Validate the shared-secret token if one is configured."""
    if _SIDECAR_TOKEN and not hmac.compare_digest(x_sidecar_token, _SIDECAR_TOKEN):
        _LOGGER.warning("Rejected request with invalid sidecar token")
        raise HTTPException(status_code=401, detail="Invalid sidecar token")


app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


_scrape_lock = asyncio.Lock()


class FetchRequest(BaseModel):
    account_name: str
    account_number: str
    phone_number: str
    start_date: date
    end_date: date


@app.post("/fetch", dependencies=[Depends(_verify_token)])
async def fetch(req: FetchRequest):
    async with _scrape_lock:
        _LOGGER.debug("Received fetch request for %s to %s", req.start_date, req.end_date)
        scraper = AlectraScraper(req.account_name, req.account_number, req.phone_number)
        try:
            xml = await scraper.fetch_usage_data(req.start_date, req.end_date)
            return {"xml": xml}
        except AlectraAuthError as e:
            _LOGGER.error("Auth error: %s", e)
            raise HTTPException(
                status_code=401,
                detail={"error": "auth_error", "message": str(e)},
            )
        except AlectraConnectionError as e:
            _LOGGER.error("Connection error: %s", e)
            raise HTTPException(
                status_code=502,
                detail={"error": "connection_error", "message": str(e)},
            )
        except Exception as e:
            _LOGGER.exception("Unexpected error during fetch")
            raise HTTPException(
                status_code=500,
                detail={"error": "internal_error", "message": str(e)},
            )
