# Scraper Documentation

This document provides detailed documentation for the scraper and processing pipeline.

## Scrapers

The scrapers are responsible for collecting job posting data from different websites. Each scraper is a class that inherits from `scraper.scrapers.base.BaseScraper`.

### Individual Scraper Usage

You can use the scrapers individually to scrape jobs for a specific search term.

```python
from scraper.scrapers.linkedin import LinkedInScraper
from scraper.scrapers.indeed import IndeedScraper

# Scrape LinkedIn
linkedin_scraper = LinkedInScraper()
linkedin_jobs = linkedin_scraper.scrape_jobs("python developer", max_jobs=50)

# Scrape Indeed
indeed_scraper = IndeedScraper()
indeed_jobs = indeed_scraper.scrape_jobs("data scientist", max_jobs=30)
```

## Processing Pipeline

The processing pipeline takes the raw scraped data and transforms it into clean, canonical job postings. The pipeline consists of the following steps:

1.  **Cleaning:** The `JobDataCleaner` class cleans the raw HTML and text from the scraped job postings. It removes HTML tags, extra whitespace, and other noise.
2.  **Normalization:** The `JobDataNormalizer` class normalizes the cleaned data. It standardizes location names, company names, and other fields.
3.  **Duplicate Detection:** The `JobDuplicateDetector` class identifies and merges duplicate job postings. It uses a similarity algorithm to compare job titles, companies, and locations.

### Pipeline Usage

The `JobProcessingPipeline` class orchestrates the entire processing flow.

```python
from scraper.pipeline.processor import JobProcessingPipeline

pipeline = JobProcessingPipeline()

# Process all pending raw job postings
stats = pipeline.process_pending_jobs()
print(stats)

# Reprocess failed jobs
stats = pipeline.reprocess_failed_jobs()
print(stats)
```

## Orchestrator

The `JobScrapingOrchestrator` is the main component that coordinates the entire scraping and processing workflow. It is designed to run multiple scraping tasks concurrently for high efficiency.

### Orchestrator Features

- **Concurrent Execution**: The orchestrator uses a thread pool to run multiple scraping tasks in parallel, significantly speeding up large scraping sessions.
- **Intelligent Location Handling**: It automatically adapts search queries for different sites. For sites with dedicated location fields (like Indeed), it uses them. For others (like LinkedIn), it appends the location to the search term.
- **Task Management**: It takes a list of `ScrapingTask` objects, each defining a site, a search term, and an optional location.
- **Resilience**: Each task runs in a completely isolated scraper instance. If a task fails, it is retried automatically up to a configured number of times.
- **Rate Limiting**: It enforces delays between retries to avoid being blocked.

### Running the Orchestrator

The orchestrator is run by calling the `run_scraping_session` method with a list of `ScrapingTask` objects.

```python
from scraper.orchestrator import ScrapingTask, JobScrapingOrchestrator

orchestrator = JobScrapingOrchestrator()

tasks = [
    ScrapingTask(site="linkedin", search_term="Python Developer", location="New York, NY", max_jobs=50),
    ScrapingTask(site="indeed", search_term="Python Developer", location="New York, NY", max_jobs=50),
    ScrapingTask(site="linkedin", search_term="Data Scientist", location="Remote", max_jobs=25),
]

results = orchestrator.run_scraping_session(tasks)
print(results)
```

## Logging

The application now uses a structured, file-based logging system configured in `settings.py`. Logs for different components are written to separate files, making debugging much easier.

- **Log Directory:** `logs/`
- **Structure:**
    - `logs/linkedin/scraper.log`: Logs from the `LinkedInScraper`.
    - `logs/indeed/scraper.log`: Logs from the `IndeedScraper`.
    - `logs/orchestrator/orchestrator.log`: Logs from the `JobScrapingOrchestrator`.
    - `logs/pipeline/pipeline.log`: Logs from all pipeline components (`JobProcessingPipeline`, `JobDataCleaner`, etc.).

Each log file is automatically rotated when it reaches 5MB to prevent files from growing too large.

## Management Commands

The project includes several management commands for interacting with the scraper and pipeline.

- **`orchestrate`**: Runs the job scraping orchestrator with a predefined set of tasks.
    ```bash
    python manage.py orchestrate
    ```
- **`process_jobs`**: Processes all pending raw job postings.
    ```bash
    python manage.py process_jobs
    ```
- **`test_indeed`**: A command to test the Indeed scraper.
    ```bash
    python manage.py test_indeed
    ```
- **`test_linkedin`**: A command to test the LinkedIn scraper.
    ```bash
    python manage.py test_linkedin
    ```
