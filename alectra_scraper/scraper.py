"""Playwright-based scraper for the Alectra Green Button portal."""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone

from playwright.async_api import Page, async_playwright, TimeoutError as PlaywrightTimeout

_LOGGER = logging.getLogger(__name__)

# Portal constants
PORTAL_URL = "https://alectrautilitiesgbportal.savagedata.com"
DOWNLOAD_PAGE_PATH = "/DownloadMyData"
SELECTOR_ACCOUNT_NAME = "#account-name"
SELECTOR_ACCOUNT_NUMBER = "#idAccountNumber"
SELECTOR_PHONE = "input[name='Phone']"
SELECTOR_SIGN_IN = "a.btn-primary.btn-block"
SELECTOR_DOWNLOAD_NAV = "a[href*='DownloadMyData']"
SELECTOR_START_DATE = "#start"
SELECTOR_END_DATE = "#end"
SELECTOR_ELECTRICITY_CHECKBOX = "label:has-text('Electricity Usage Data')"
SELECTOR_DOWNLOAD_BTN = "#dataTable button.btn"

LOGIN_TIMEOUT_MS = 30_000
DOWNLOAD_TIMEOUT_MS = 60_000

SCREENSHOT_DIR = os.environ.get("SCREENSHOT_DIR", "/screenshots")


class AlectraAuthError(Exception):
    """Raised when portal credentials are rejected."""


class AlectraConnectionError(Exception):
    """Raised when the portal cannot be reached or download fails."""


async def _save_failure_screenshot(page: Page) -> None:
    """Capture a full-page screenshot and save it to SCREENSHOT_DIR."""
    try:
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        path = os.path.join(SCREENSHOT_DIR, f"failure_{timestamp}.png")
        await page.screenshot(path=path, full_page=True)
        _LOGGER.info("Failure screenshot saved: %s", path)
    except Exception as screenshot_err:
        _LOGGER.warning("Could not save failure screenshot: %s", screenshot_err)


class AlectraScraper:
    """Automate the Alectra Green Button portal to download ESPI XML data."""

    def __init__(self, account_name: str, account_number: str, phone_number: str) -> None:
        self._account_name = account_name
        self._account_number = account_number
        self._phone_number = phone_number

    async def fetch_usage_data(self, start_date: date, end_date: date) -> str:
        """Fetch ESPI XML usage data for the given date range."""
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await self._login(page)
                return await self._download(page, start_date, end_date)
            except Exception as err:
                await _save_failure_screenshot(page)
                if isinstance(err, (AlectraAuthError, AlectraConnectionError)):
                    raise
                if isinstance(err, PlaywrightTimeout):
                    raise AlectraConnectionError(f"Portal timed out: {err}") from err
                _LOGGER.exception("Unexpected error during portal scraping")
                raise AlectraConnectionError(f"Portal error: {err}") from err
            finally:
                await browser.close()

    async def _login(self, page: Page) -> None:
        """Log in to the Alectra portal."""
        _LOGGER.debug("Navigating to portal login page")
        await page.goto(PORTAL_URL, wait_until="domcontentloaded")
        await page.fill(SELECTOR_ACCOUNT_NAME, self._account_name)
        await page.fill(SELECTOR_ACCOUNT_NUMBER, self._account_number)
        # Phone uses a Radzen masked input -- type digits individually so the
        # mask's oninput handler fires for each character.
        phone_digits = "".join(c for c in self._phone_number if c.isdigit())
        await page.click(SELECTOR_PHONE)
        await page.type(SELECTOR_PHONE, phone_digits)
        _LOGGER.debug("Clicking Sign In")
        login_url = page.url
        await page.click(SELECTOR_SIGN_IN)
        try:
            # Blazor Server apps keep a persistent SignalR WebSocket open, so
            # wait_for_load_state("networkidle") never fires. Instead wait for
            # the URL to change — a successful login redirects to a landing page.
            await page.wait_for_url(
                lambda url: url != login_url,
                timeout=LOGIN_TIMEOUT_MS,
            )
            _LOGGER.debug("Post-login URL: %s", page.url)
        except PlaywrightTimeout as err:
            raise AlectraAuthError(
                "Login failed — portal did not redirect after sign in. Check credentials."
            ) from err
        try:
            # Wait for Blazor to finish rendering the post-login component.
            # A failed login keeps the form visible; success removes it.
            await page.wait_for_selector(
                SELECTOR_ACCOUNT_NAME, state="hidden", timeout=10_000
            )
        except PlaywrightTimeout as err:
            raise AlectraAuthError(
                "Login failed — credentials rejected by portal."
            ) from err

    async def _download(self, page: Page, start_date: date, end_date: date) -> str:
        """Set date range and capture the downloaded XML."""
        # Navigate to the download page by clicking the link. The portal uses
        # Blazor Server (SignalR/WebSocket): the WebSocket circuit is bound to the
        # page instance, not the HTTP session cookie. Calling page.goto() would
        # create a new unauthenticated circuit and redirect back to login.
        # Clicking within the existing page preserves the live circuit.
        _LOGGER.debug("Navigating to download page")
        await page.click(SELECTOR_DOWNLOAD_NAV)
        await page.wait_for_url(f"**{DOWNLOAD_PAGE_PATH}**", timeout=LOGIN_TIMEOUT_MS)

        # The portal's JS calls window.saveFile() to trigger a file download.
        # By replacing it, we capture the ESPI XML content in-memory, avoiding
        # Playwright's download API and filesystem I/O.
        _LOGGER.debug("Setting up download interception")
        await page.evaluate(
            """
            window._capturedXML = null;
            window.saveFile = function() {
                // Capture whichever argument is a non-empty string (XML content).
                // The portal may call saveFile(filename, content) or saveFile(content, filename).
                for (var i = 0; i < arguments.length; i++) {
                    // trim().startsWith('<') handles leading whitespace; if BOM (\ufeff)
                // is ever encountered, prepend: arguments[i].replace(/^\uFEFF/, '')
                if (typeof arguments[i] === 'string' && arguments[i].trim().startsWith('<')) {
                        window._capturedXML = arguments[i];
                        return;
                    }
                }
            };
        """
        )
        await page.fill(SELECTOR_START_DATE, start_date.strftime("%m/%d/%Y"))
        await page.keyboard.press("Tab")
        await page.fill(SELECTOR_END_DATE, end_date.strftime("%m/%d/%Y"))
        await page.keyboard.press("Tab")
        _LOGGER.debug("Selecting Electricity Usage Data")
        await page.click(SELECTOR_ELECTRICITY_CHECKBOX)
        _LOGGER.debug("Clicking download button")
        await page.click(SELECTOR_DOWNLOAD_BTN)
        try:
            await page.wait_for_function(
                "window._capturedXML !== null", timeout=DOWNLOAD_TIMEOUT_MS
            )
        except PlaywrightTimeout as err:
            raise AlectraConnectionError(
                "Download timed out — XML data was not received"
            ) from err
        xml_content = await page.evaluate("window._capturedXML")
        _LOGGER.debug("Successfully captured XML data (%d chars)", len(xml_content))
        return xml_content
