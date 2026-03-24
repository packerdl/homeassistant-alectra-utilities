# Alectra Utilities Scraper

This add-on runs a Playwright-based scraper that fetches electricity usage data from the [Alectra Utilities Green Button portal](https://alectrautilitiesgbportal.savagedata.com). It is used by the **Alectra Utilities** custom integration for Home Assistant.

## Requirements

> **Note:** This add-on requires an x86-64 (amd64) system. ARM-based installations (e.g. Raspberry Pi) are not supported due to Playwright/Chromium limitations.

## How it works

The scraper launches headless Chromium on demand to log in to the portal, set a date range, and capture the downloaded ESPI XML data. Each fetch takes roughly 30-60 seconds. Between fetches the add-on idles at minimal resource usage (~30-50 MB RAM).

By default the integration polls once every 24 hours.

## Configuration

| Option | Description |
|--------|-------------|
| `sidecar_token` | Optional shared secret for request authentication. If set, the integration must send the same token in its config. Leave blank to disable. |

## Finding the sidecar URL

After installing and starting this add-on, you need its URL for the Alectra Utilities integration config flow:

1. Go to **Settings → Add-ons → Alectra Utilities Scraper**
2. The hostname is shown on the add-on info page
3. The port is **8080**
4. Enter the full URL (e.g. `http://<hostname>:8080`) when configuring the integration

## Failure screenshots

If a scrape fails, a screenshot of the portal page is saved to `/addon_configs/alectra_scraper/screenshots/`. You can access these files from the **addon_configs** shared folder on your HA instance.
