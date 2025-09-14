# API Documentation

This document provides detailed documentation for the Job Scraper API.

## Authentication

The API currently does not require authentication, but this can be added in the future using Django REST Framework's authentication classes.

## Endpoints

### Actions

#### Trigger Orchestration

- **Endpoint:** `POST /api/v1/orchestrate/`
- **Description:** Starts a new scraping orchestration session in the background. The server will immediately respond with a `202 Accepted` status if the request is valid. The actual scraping will run as a background task.
- **Request Body:**
    - `sites` (array of strings, required): A list of sites to scrape. Options: `"linkedin"`, `"indeed"`.
    - `max_jobs` (integer, optional, default: 50): The maximum number of new jobs to scrape per search criterion.
    - `searches` (array of objects, required): A list of search criteria.
        - `search_term` (string, required): The job title or keyword to search for.
        - `location` (string, optional): The location to search in.
- **Example Request:**
    ```json
    {
        "sites": ["linkedin", "indeed"],
        "max_jobs": 30,
        "searches": [
            { "search_term": "Data Scientist", "location": "New York, NY" },
            { "search_term": "Backend Engineer", "location": "Remote" },
            { "search_term": "Frontend Developer" }
        ]
    }
    ```
- **Example Success Response (202 Accepted):**
    ```json
    {
        "message": "Scraping session started for 6 tasks in the background."
    }
    ```
- **Example `curl` Command:**
    ```bash
    curl -X POST http://127.0.0.1:8000/api/v1/orchestrate/ \
    -H "Content-Type: application/json" \
    -d '{
        "sites": ["linkedin", "indeed"],
        "max_jobs": 30,
        "searches": [
            { "search_term": "Data Scientist", "location": "New York, NY" },
            { "search_term": "Backend Engineer", "location": "Remote" }
        ]
    }'
    ```

### Jobs

#### List Jobs

- **Endpoint:** `GET /api/v1/jobs/`
- **Description:** Retrieves a paginated list of canonical jobs.
- **Query Parameters:**
    - `search` (string): Search for a keyword in the title, company, or description.
    - `company_exact` (string): Filter by an exact company name (case-insensitive).
    - `location_contains` (string): Filter by a location that contains the given string.
    - `posted_within_days` (integer): Filter for jobs posted within the last N days.
    - `recently_active` (boolean): Filter for jobs that have been active in the last 7 days (`true` or `false`).
    - `ordering` (string): Sort the results. Options: `posted`, `-posted`, `company`, `-company`.
    - `page` (integer): The page number to retrieve.
    - `limit` (integer): The number of results per page.
- **Example Request:**
    ```
    GET /api/v1/jobs/?search=python&company_exact=Google&limit=10
    ```
- **Example Response:**
    ```json
    {
        "count": 123,
        "next": "/api/v1/jobs/?page=2&search=python&company_exact=Google&limit=10",
        "previous": null,
        "results": [
            {
                "id": 1,
                "title": "Software Engineer, Python",
                "company": "Google",
                "location": "Mountain View, CA",
                "canonical_url": "https://careers.google.com/jobs/results/12345/",
                "first_seen": "2025-09-10T10:00:00Z",
                "last_seen": "2025-09-13T12:00:00Z",
                "days_since_first_seen": 3,
                "is_recently_active": true
            }
        ]
    }
    ```

#### Get Job

- **Endpoint:** `GET /api/v1/jobs/{id}/`
- **Description:** Retrieves the details of a specific job.
- **URL Parameters:**
    - `id` (integer): The ID of the job to retrieve.
- **Example Request:**
    ```
    GET /api/v1/jobs/1/
    ```
- **Example Response:**
    ```json
    {
        "id": 1,
        "title": "Software Engineer, Python",
        "company": "Google",
        "location": "Mountain View, CA",
        "description": "...",
        "canonical_url": "https://careers.google.com/jobs/results/12345/",
        "first_seen": "2025-09-10T10:00:00Z",
        "last_seen": "2025-09-13T12:00:00Z",
        "first_seen_formatted": "2025-09-10 10:00:00",
        "last_seen_formatted": "2025-09-13 12:00:00",
        "days_since_first_seen": 3,
        "days_since_last_seen": 0,
        "is_recently_active": true,
        "created_at": "2025-09-10T10:00:00Z",
        "updated_at": "2025-09-13T12:00:00Z"
    }
    ```

### Trends

#### Get Trends

- **Endpoint:** `GET /api/v1/trends/`
- **Description:** Retrieves market trends and analytics.
- **Query Parameters:**
    - `metric` (string): The metric to retrieve. Options: `companies`, `locations`, `activity`, `all`.
    - `days` (integer): The number of days to analyze (default: 30).
    - `limit` (integer): The number of results to return (default: 10).
- **Example Request:**
    ```
    GET /api/v1/trends/?metric=companies&days=7&limit=5
    ```

#### Get Skill Trends

- **Endpoint:** `GET /api/v1/trends/skills/`
- **Description:** Retrieves skill trends from job descriptions.
- **Query Parameters:**
    - `days` (integer): The number of days to analyze (default: 30).
    - `limit` (integer): The number of results to return (default: 15).
- **Example Request:**
    ```
    GET /api/v1/trends/skills/?days=14&limit=10
    ```

### Monitoring

#### Get System Health

- **Endpoint:** `GET /api/v1/health/`
- **Description:** Retrieves system health metrics.

#### Get Quick Stats

- **Endpoint:** `GET /api/v1/quick-stats/`
- **Description:** Retrieves a quick overview of the system stats.

#### List Scraping Sessions

- **Endpoint:** `GET /api/v1/scraping-sessions/`
- **Description:** Retrieves a paginated list of scraping sessions.
- **Query Parameters:**
    - `site` (string): Filter by site. Options: `linkedin`, `indeed`.
    - `status` (string): Filter by session status. Options: `running`, `completed`, `failed`, `partial`.
    - `within_days` (integer): Filter for sessions within the last N days.
    - `min_success_rate` (integer): Filter by minimum success rate (0-100).
    - `ordering` (string): Sort the results. Options: `started_at`, `-started_at`, `ended_at`, `-ended_at`, `status`, `-status`.
    - `page` (integer): The page number to retrieve.
    - `limit` (integer): The number of results per page.

### Raw Data

#### List Raw Jobs

- **Endpoint:** `GET /api/v1/raw-jobs/`
- **Description:** Retrieves a paginated list of raw job postings.
- **Query Parameters:**
    - `site` (string): Filter by site. Options: `linkedin`, `indeed`.
    - `status` (string): Filter by processing status. Options: `pending`, `processed`, `failed`.
    - `scraped_within_days` (integer): Filter for jobs scraped within the last N days.
    - `page` (integer): The page number to retrieve.
    - `limit` (integer): The number of results per page.