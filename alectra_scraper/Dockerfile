FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x run.sh
CMD ["./run.sh"]
