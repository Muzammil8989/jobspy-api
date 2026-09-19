# JobSpy API

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)

A lightweight REST API around [JobSpy](https://github.com/speedyapply/JobSpy). Search job boards through one JSON endpoint and consume normalized results from applications, scripts, or automation tools such as n8n.

## Features

- Search multiple job sites in a single request
- Filter by search term, location, age, and remote status
- JSON-safe results with readable date values and no `NaN` fields
- Input validation and a 200-result safety limit
- Health-check endpoint and structured error responses
- Docker and Gunicorn configuration for deployment

## Quick start with Docker

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- Docker Compose

Clone and start the service:

```bash
git clone https://github.com/Muzammil8989/jobspy-api.git
cd jobspy-api
docker compose up --build -d
```

Confirm that it is running:

```bash
curl http://localhost:5000/health
```

Stop the service with:

```bash
docker compose down
```

## Local installation

Python 3.11 is recommended.

```bash
git clone https://github.com/Muzammil8989/jobspy-api.git
cd jobspy-api
python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS or Linux
source .venv/bin/activate
```

Install the dependencies and run the development server:

```bash
pip install -r requirements.txt
python jobspy_api.py
```

The API is available at `http://localhost:5000`.

## API reference

### `GET /health`

Returns the service status and current UTC time.

```json
{
  "service": "jobspy-api",
  "status": "ok",
  "time": "2026-09-19T12:00:00+00:00"
}
```

### `POST /scrape`

Runs a job search. Send a JSON request body with the following fields:

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `search_term` | string | Yes | — | Job title or keywords to search for |
| `location` | string | No | `""` | Location used by the selected job sites |
| `site_names` | string[] | No | `["linkedin", "indeed"]` | Job sites passed to JobSpy |
| `results_wanted` | integer | No | `20` | Requested result count; values over 200 are capped |
| `hours_old` | integer | No | `96` | Maximum age of job listings in hours |
| `is_remote` | boolean | No | `null` | Set to `true` or `false` to apply a remote filter |
| `country_indeed` | string | No | `"USA"` | Country used for Indeed searches |
| `linkedin_fetch_description` | boolean | No | `false` | Fetch each LinkedIn job's full description (slower per-job, but needed for keyword/skill matching downstream) |

Example request:

```bash
curl --request POST http://localhost:5000/scrape \
  --header "Content-Type: application/json" \
  --header "X-API-Key: replace-with-your-api-key" \
  --data '{
    "search_term": "Python Developer",
    "location": "Karachi, Pakistan",
    "site_names": ["linkedin", "indeed"],
    "results_wanted": 20,
    "hours_old": 72,
    "is_remote": true,
    "country_indeed": "Pakistan"
  }'
```

Successful response:

```json
{
  "success": true,
  "count": 1,
  "jobs": [
    {
      "site": "linkedin",
      "title": "Python Developer",
      "company": "Example Company",
      "location": "Karachi, Pakistan",
      "job_url": "https://example.com/job/123",
      "date_posted": "2026-09-19"
    }
  ],
  "failed_sites": []
}
```

Job fields can vary by source. The API returns the columns supplied by JobSpy rather than enforcing a fixed job schema.

Each requested site is scraped independently, so one blocked or unsupported site (e.g. Glassdoor rejecting a country, or a site rate-limiting the request) does not fail the whole search. `failed_sites` lists which of the requested `site_names` produced no results because their scraper raised an error; the request still returns `success: true` with results from the sites that did work, as long as at least one site succeeded.

## Errors

Errors use a consistent JSON shape:

```json
{
  "success": false,
  "error": "A human-readable error message.",
  "jobs": []
}
```

| Status | Meaning |
| --- | --- |
| `400` | Invalid JSON or request validation failure |
| `404` | Route not found |
| `405` | HTTP method not allowed |
| `500` | Results could not be serialized |
| `502` | JobSpy or an upstream job site failed |

## Configuration

The service recognizes these environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `PORT` | `5000` | Development server port |
| `FLASK_DEBUG` | `0` | Set to `1` to enable Flask debug mode locally |
| `LOG_LEVEL` | `INFO` | Python logging level, such as `DEBUG` or `WARNING` |
| `API_KEY` | — | Required secret sent by clients in the `X-API-Key` header |

For a direct production-style launch:

```bash
gunicorn --bind 0.0.0.0:5000 --timeout 180 --workers 1 jobspy_api:app
```

## Using the API from n8n

Add an **HTTP Request** node with:

- Method: `POST`
- URL from another Docker container: `http://host.docker.internal:5000/scrape`
- URL when n8n shares this Compose network: `http://jobspy-api:5000/scrape`
- Body content type: JSON
- Header: `X-API-Key` with the same secret configured in the service's `API_KEY` environment variable
- Body: any valid `/scrape` request shown above

On Linux, `host.docker.internal` may require the Docker host-gateway mapping. Sharing a Docker network and using the service name is usually simpler.

## Project structure

```text
.
├── jobspy_api.py       # Flask application, validation, and routes
├── requirements.txt    # Pinned Python dependencies
├── Dockerfile          # Gunicorn production image
└── docker-compose.yml  # Local container configuration
```

## Responsible use

Job sites can impose rate limits and terms governing automated access. Use reasonable result counts, avoid excessive request frequency, and follow the terms and applicable laws for every source you query.

## License

No license has been specified for this repository. All rights are reserved unless a license is added.
