# Job Scraper

This project is a web scraping application that collects job postings from various sources, processes them, and provides a dashboard and API for analysis.

## Architecture

```
+-----------------+      +-----------------------+      +--------------------+
|   Scrapers      |----->| JobScrapingOrchestrator |----->| Raw Job Postings   |
| (LinkedIn, Indeed)|      +-----------------------+      | (Database)         |
+-----------------+            |                      +--------------------+
                                     |
                                     v
+-----------------+      +-----------------------+      +--------------------+
|   Dashboard UI  |<---->|      Django API       |<---->|  Canonical Jobs    |
| (HTML+ CSS) |      |                       |      | (Database)         |
+-----------------+      +-----------------------+      +--------------------+
                                     ^
                                     |
                             +--------------------+
                             | Processing Pipeline|
                             +--------------------+
```

### Components

- **Scrapers:** Responsible for scraping job postings from different websites (e.g., LinkedIn, Indeed).
- **JobScrapingOrchestrator:** The central component that manages the scraping process. It coordinates the scrapers, handles rate limiting, and triggers the processing pipeline.
- **Raw Job Postings DB:** A database table that stores the raw, unprocessed data scraped from the job boards.
- **Processing Pipeline:** A series of steps that clean, normalize, and de-duplicate the raw job postings.
- **Canonical Jobs DB:** A database table that stores the clean, processed, and canonical job postings.
- **Django API:** A RESTful API that provides access to the processed job data and system monitoring endpoints.
- **Dashboard UI:** A web-based interface for visualizing the job data and monitoring the scraping process.

## Orchestrator Flow

The `JobScrapingOrchestrator` is the heart of the scraping process. It performs the following steps:

1.  **Task Management:** It takes a list of `ScrapingTask` objects, each defining a site and a search term to scrape.
2.  **Execution with Retries:** For each task, it executes the corresponding scraper. If a task fails, it retries up to a configured number of times.
3.  **Rate Limiting:** It enforces delays between requests to the same site and between different sites to avoid being blocked.
4.  **Data Persistence:** The raw scraped data is saved to the `RawJobPosting` model in the database.
5.  **Processing Trigger:** After the scraping session is complete, it can trigger the `JobProcessingPipeline` to process the newly scraped jobs.

## API Documentation

The API provides several endpoints for accessing the job data and monitoring the system.

### Jobs

- **`GET /api/v1/jobs/`**: List all canonical jobs.
    - **Query Parameters:**
        - `search`: Search for a keyword in the title, company, or description.
        - `company_exact`: Filter by exact company name.
        - `location_contains`: Filter by location.
        - `posted_within_days`: Filter by the number of days since the job was posted.
        - `recently_active`: Filter for jobs that have been active in the last 7 days (`true` or `false`).
        - `ordering`: Sort the results by `posted`, `-posted`, `company`, `-company`.
- **`GET /api/v1/jobs/{id}/`**: Get the details of a specific job.

### Trends

- **`GET /api/v1/trends/`**: Get market trends and analytics.
    - **Query Parameters:**
        - `metric`: The metric to retrieve (`companies`, `locations`, `activity`, `all`).
        - `days`: The number of days to analyze (default: 30).
        - `limit`: The number of results to return (default: 10).
- **`GET /api/v1/trends/skills/`**: Get skill trends from job descriptions.
    - **Query Parameters:**
        - `days`: The number of days to analyze (default: 30).
        - `limit`: The number of results to return (default: 15).

### Monitoring

- **`GET /api/v1/health/`**: Get system health metrics.
- **`GET /api/v1/quick-stats/`**: Get a quick overview of the system stats.
- **`GET /api/v1/scraping-sessions/`**: List all scraping sessions.
    - **Query Parameters:**
        - `site`: Filter by site (`linkedin` or `indeed`).
        - `status`: Filter by session status (`running`, `completed`, `failed`, `partial`).
        - `within_days`: Filter for sessions within the last N days.
        - `min_success_rate`: Filter by minimum success rate.
        - `ordering`: Sort the results by `started_at`, `ended_at`, `status`.

### Raw Data

- **`GET /api/v1/raw-jobs/`**: List all raw job postings.
    - **Query Parameters:**
        - `site`: Filter by site (`linkedin` or `indeed`).
        - `status`: Filter by processing status (`pending`, `processed`, `failed`).
        - `scraped_within_days`: Filter for jobs scraped within the last N days.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd job_scraper
    ```
2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Run database migrations:**
    ```bash
    python manage.py migrate
    ```

## Usage

1.  **Run the Django development server:**
    ```bash
    python manage.py runserver
    ```
2.  **Run the scraper:**
    To run a scraping session, you can use the Django shell:
    ```bash
    python manage.py shell
    ```
    Then, in the shell:
    ```python
    from scraper.orchestrator import OrchestrationExamples
    OrchestrationExamples.daily_job_scraping()
    ```
