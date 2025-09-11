import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from scraper.models import RawJobPosting, ScrapingSession
from scraper.pipeline.processor import JobProcessingPipeline
from scraper.scrapers.base import BaseScraper
from scraper.scrapers.indeed import IndeedScraper
from scraper.scrapers.linkedin import LinkedInScraper


@dataclass
class ScrapingTask:
    """Configuration for a single scraping task"""
    site: str
    search_term: str
    max_jobs: int = 50
    priority: int = 1

@dataclass
class OrchestrationConfig:
    """Overall orchestration configuration"""
    # Rate limiting
    delay_between_sites: int = 30  # seconds
    delay_between_searches: int = 10  # seconds
    
    # Retry settings
    max_retries: int = 3
    retry_delay: int = 60  # seconds
    
    # Processing
    process_immediately: bool = False
    
    # Safety limits
    max_jobs_per_site: int = 200
    timeout_per_task: int = 600


class JobScrapingOrchestrator:
    """
    Coordinates scraping from multiple sites and processing the results.
    
    Think of this as the "project manager" that:
    1. Decides what to scrape and when
    2. Manages rate limits across sites
    3. Handles failures gracefully
    4. Coordinates the data pipeline
    5. Provides monitoring/reporting
    """
    def __init__(self, config: Optional[OrchestrationConfig]):
        self.config = config or OrchestrationConfig()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self._scrapers: Dict[str, BaseScraper] = {}
        self.pipeline = JobProcessingPipeline()
        
        # Track orchestration state
        self.current_session_id = None
        self.failed_tasks = []

    def get_scraper(self, site: str) -> BaseScraper:
        """Get or create scraper instance for a site"""
        if site not in self._scrapers:
            if site == 'linkedin':
                self._scrapers[site] = LinkedInScraper()
            elif site == 'indeed':
                self._scrapers[site] = IndeedScraper()
            else:
                raise ValueError(f"Unsupported site: {site}")
        
        return self._scrapers[site]

    def run_scraping_session(self, tasks: List[ScrapingTask]) -> Dict[str, Any]:
        """
        Run a complete scraping session with multiple tasks.
        
        This is the main orchestration method!
        """
        session_start = time.time()
        self.logger.info(f"Starting orchestration session with {len(tasks)} tasks")

        sorted_tasks = sorted(tasks, key=lambda t: (t.priority, t.site, t.search_term))

        results = {
            'session_start': session_start,
            'tasks_completed': 0,
            'tasks_failed': 0,
            'total_jobs_scraped': 0,
            'total_jobs_processed': 0,
            'errors': [],
            'site_stats': {}
        }
        
        try:
            for i, task in enumerate(sorted_tasks):
                self.logger.info(f"Task {i+1}/{len(tasks)}: {task.site} - '{task.search_term}'")

                task_result = self._execute_single_task(task)

                if task_result['success']:
                    results['tasks_completed'] += 1
                    results['total_jobs_scraped'] += task_result['jobs_scraped']

                    # Track per site statistics
                    site = task.site
                    if site not in results['site_stats']:
                        results['site_stats'][site] = {'jobs': 0, 'searches': 0, 'failures': 0}
                    
                    results['site_stats'][site]['jobs'] += task_result['jobs_scraped']
                    results['site_stats'][site]['searches'] += 1
                else:
                    results['tasks_failed'] += 1
                    results['errors'].append({
                        'task': f"{task.site} - {task.search_term}",
                        'error': task_result['error']
                    })
                    
                    # Track site failures
                    site = task.site
                    if site not in results['site_stats']:
                        results['site_stats'][site] = {'jobs': 0, 'searches': 0, 'failures': 0}
                    results['site_stats'][site]['failures'] += 1

                # Delay between tasks
                if i < len(sorted_tasks) - 1:  # Don't delay after the last task
                    self._delay_between_tasks(task, sorted_tasks[i+1])

            # Process all scraped data if configured to batch process
            if not self.config.process_immediately:
                self.logger.info("Running batch processing of scraped data...")
                processing_stats = self.pipeline.process_pending_jobs()
                results['total_jobs_processed'] = processing_stats['processed']
                results['processing_stats'] = processing_stats

        except Exception as e:
            self.logger.error(f"Orchestration session failed: {e}")
            results['session_error'] = str(e)
        
        results['session_end'] = time.time()
        results['total_duration'] = results['session_end'] - session_start
        
        self.logger.info(f"Orchestration session completed in {results['total_duration']}")
        self._log_session_summary(results)
        
        return results
    
    def _execute_single_task(self, task: ScrapingTask) -> Dict[str, Any]:
        """Execute a single scraping task with retry logic"""

        task_result = {
            'success': False,
            'jobs_scraped': 0,
            'error': None,
            'attempts': 0
        }

        for attempt in range(self.config.max_retries + 1):
            task_result['attempts'] = attempt + 1

            try:
                self.logger.info(f"Attempt {attempt + 1} for {task.site} - {task.search_term}")

                # Get the appropriate scraper
                scraper = self.get_scraper(task.site)

                # Execute scraping
                scraped_jobs = scraper.scrape_jobs(task.search_term, max_jobs=task.max_jobs)

                task_result['success'] = True
                task_result['jobs_scraped'] += len(scraped_jobs)

                # Process immediately if configured
                if self.config.process_immediately:
                    processing_stats = self.pipeline.process_pending_jobs()
                    task_result['jobs_processed'] = processing_stats['processed']

                self.logger.info(f"Task completed successfully: {task_result['jobs_scraped']} jobs")
                break

            except Exception as e:
                error_msg = f"Attempt {attempt + 1} failed: {str(e)}"
                self.logger.error(error_msg)
                task_result['error'] = error_msg

                # If not the last attempt, wait before trying
                if attempt < self.config.max_retries:
                    self.logger.info(f"Waiting {self.config.retry_delay}s before retry...")
                    time.sleep(self.config.retry_delay)
                else:
                    self.logger.error(f"All {self.config.max_retries + 1} attempts failed for {task.site}")
        
        return task_result

    def _delay_between_tasks(self, current_task: ScrapingTask, next_task: ScrapingTask):
        """Smart delay logic based on task transitions"""

        if current_task.site != next_task.site:
            # Different site = longer delay
            delay = self.config.delay_between_sites
            self.logger.info(f"Switching from {current_task.site} to {next_task.site}, waiting {delay}s...")
        else:
            # Same site, different search = shorter delay
            delay = self.config.delay_between_searches
            self.logger.info(f"Next search on {next_task.site}, waiting {delay}s...")
        
        time.sleep(delay)

    def _log_session_summary(self, results: Dict[str, Any]):
        """Log a nice summary of the orchestration session"""
        self.logger.info("=" * 60)
        self.logger.info("ORCHESTRATION SESSION SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Duration: {results['total_duration']}")
        self.logger.info(f"Tasks completed: {results['tasks_completed']}")
        self.logger.info(f"Tasks failed: {results['tasks_failed']}")
        self.logger.info(f"Total jobs scraped: {results['total_jobs_scraped']}")
        
        if 'total_jobs_processed' in results:
            self.logger.info(f"Total jobs processed: {results['total_jobs_processed']}")
        
        # Site-by-site breakdown
        for site, stats in results['site_stats'].items():
            self.logger.info(f"{site.upper()}: {stats['jobs']} jobs, {stats['searches']} searches, {stats['failures']} failures")
        
        # Errors summary
        if results['errors']:
            self.logger.info("ERRORS:")
            for error in results['errors']:
                self.logger.info(f"  {error['task']}: {error['error']}")

    def get_system_health(self) -> Dict[str, Any]:
        """
        Check system health - recent scraping success rates, processing backlogs, etc.
        """
        now = datetime.now()
        last_24h = now - timedelta(hours=24)
        
        # Recent scraping sessions
        recent_sessions = ScrapingSession.objects.filter(
            started_at__gte=last_24h
        ).order_by('-started_at')
        
        # Pending processing jobs
        pending_jobs = RawJobPosting.objects.filter(processing_status='pending').count()
        failed_jobs = RawJobPosting.objects.filter(processing_status='failed').count()
        
        # Calculate success rates by site
        site_health = {}
        for site in ['linkedin', 'indeed']:
            site_sessions = recent_sessions.filter(source_site=site)
            if site_sessions.exists():
                successful = site_sessions.filter(status='completed').count()
                total = site_sessions.count()
                success_rate = (successful / total) * 100 if total > 0 else 0
                
                site_health[site] = {
                    'sessions_24h': total,
                    'success_rate': success_rate,
                    'last_successful': site_sessions.filter(status='completed').first(),
                    'total_jobs_24h': sum(s.jobs_successful for s in site_sessions)
                }
        
        return {
            'timestamp': now,
            'pending_processing': pending_jobs,
            'failed_processing': failed_jobs,
            'site_health': site_health,
            'recent_sessions_count': recent_sessions.count()
        }
