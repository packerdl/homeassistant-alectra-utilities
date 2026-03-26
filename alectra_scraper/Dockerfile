FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

ARG BUILD_VERSION=dev

LABEL \
  org.opencontainers.image.title="Alectra Utilities Scraper" \
  org.opencontainers.image.description="Playwright sidecar for Alectra Green Button portal" \
  org.opencontainers.image.source="https://github.com/packerdl/homeassistant-alectra-utilities" \
  org.opencontainers.image.version="${BUILD_VERSION}"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x run.sh

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

CMD ["./run.sh"]
