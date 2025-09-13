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

The `JobScrapingOrchestrator` is the main component that coordinates the entire scraping and processing workflow.

### Orchestrator Configuration

The orchestrator can be configured with an `OrchestrationConfig` object.

```python
from scraper.orchestrator import OrchestrationConfig, JobScrapingOrchestrator

config = OrchestrationConfig(
    delay_between_sites=60,  # 1 minute
    delay_between_searches=30, # 30 seconds
    max_retries=3,
    retry_delay=60, # 1 minute
    process_immediately=False, # Batch process at the end
)

orchestrator = JobScrapingOrchestrator(config)
```

### Running the Orchestrator

The orchestrator is run by calling the `run_scraping_session` method with a list of `ScrapingTask` objects.

```python
from scraper.orchestrator import ScrapingTask

tasks = [
    ScrapingTask(site="linkedin", search_term="python developer", max_jobs=50),
    ScrapingTask(site="indeed", search_term="python developer", max_jobs=50),
]

results = orchestrator.run_scraping_session(tasks)
print(results)
```

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
