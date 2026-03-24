# Alectra Utilities for Home Assistant

A custom Home Assistant integration that scrapes electricity usage data from the [Alectra Utilities Green Button portal](https://alectrautilitiesgbportal.savagedata.com).

## Requirements

- Home Assistant 2024.1 or later
- **x86-64 (amd64) system** — ARM (e.g. Raspberry Pi) is not supported due to Playwright/Chromium limitations
- An Alectra Utilities account with Green Button portal access

## Sensors

| Sensor | Description | Unit |
|--------|-------------|------|
| **Energy** | Cumulative meter register reading | kWh |
| **Daily Usage** | Total energy consumed yesterday | kWh |
| **Latest Interval** | Most recent hourly reading | kWh |
| **Daily Cost** | Total cost for yesterday (if available in portal data) | CAD |

The integration polls the portal once every 24 hours (configurable via options flow).

## Installation

This repo serves as both a **HACS integration** and a **Supervisor add-on repository**. You need to install two components: the integration and the scraper sidecar.

### Step 1: Install the Scraper Add-on

The scraper runs headless Chromium in a Docker container to automate the portal.

1. Go to **Settings > Add-ons > Add-on Store**
2. Open the three-dot menu (top right) and select **Repositories**
3. Paste `https://github.com/packerdl/homeassistant-alectra-utilities` and click **Add**
4. Find **Alectra Utilities Scraper** in the store and click **Install**
5. (Optional) Set a `sidecar_token` in the add-on configuration for request authentication
6. Click **Start**

### Step 2: Install the Integration via HACS

1. Open **HACS > Integrations**
2. Open the three-dot menu (top right) and select **Custom repositories**
3. Paste `https://github.com/packerdl/homeassistant-alectra-utilities`, select **Integration**, and click **Add**
4. Search for **Alectra Utilities** and click **Install**
5. Restart Home Assistant

### Step 3: Configure the Integration

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for **Alectra Utilities**
3. Enter your portal credentials:
   - **Sidecar URL** — The URL of the scraper add-on (default: `http://localhost:8080`)
   - **Account Name** — Your name as it appears on the portal
   - **Account Number** — Your Alectra account number
   - **Phone Number** — The phone number linked to your account
   - **Sidecar Token** — Must match the token set in the add-on config (leave blank if not set)
4. The integration will validate your credentials by performing a test scrape

## How It Works

The portal is a Blazor Server application that doesn't expose a standard API. The scraper sidecar launches headless Chromium to automate login, date range selection, and ESPI XML download. The integration communicates with the sidecar over HTTP on your local network.

```
HA Integration  --HTTP-->  Scraper Add-on  --Chromium-->  Alectra Portal
   (sensors)                 (Playwright)                  (Blazor app)
```

## Troubleshooting

- **Sensors show "unavailable"** — Check that the scraper add-on is running. Look at the add-on logs for errors.
- **"Cannot connect" during setup** — Verify the sidecar URL. If the add-on is running on the same machine, use `http://localhost:8080`.
- **"Invalid auth" during setup** — Double-check your account name, number, and phone number match exactly what the portal expects.
- **Failure screenshots** — When a scrape fails, a screenshot is saved to `/addon_configs/alectra_scraper/screenshots/` for debugging.

## Services

| Service | Description |
|---------|-------------|
| `alectra_utilities.refresh` | Trigger an immediate data refresh for all configured accounts |

## License

MIT
