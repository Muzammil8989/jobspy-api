FROM python:3.11-slim

WORKDIR /app

# system deps some jobspy backends need for parsing/requests
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY jobspy_api.py .

EXPOSE 5000

# gunicorn for a steadier long-running server than flask's dev server
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "120", "--workers", "2", "jobspy_api:app"]