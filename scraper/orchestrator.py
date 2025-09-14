import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from django.utils import timezone

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
    location: Optional[str] = None
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
    def __init__(self, config: OrchestrationConfig = None):
        self.config = config or OrchestrationConfig()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.pipeline = JobProcessingPipeline()
        
        # Track orchestration state
        self.current_session_id = None
        self.failed_tasks = []

    def run_scraping_session(self, tasks: List[ScrapingTask]) -> Dict[str, Any]:
        """
        Run a complete scraping session with multiple tasks concurrently.
        
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
            'total_jobs_existing': 0, # new
            'total_jobs_processed': 0,
            'errors': [],
            'site_stats': {}
        }
        
        try:
            with ThreadPoolExecutor() as executor:
                future_to_task = {executor.submit(self._execute_single_task, task): task for task in sorted_tasks}

                for future in as_completed(future_to_task):
                    task = future_to_task[future]
                    try:
                        task_result = future.result()

                        if task_result['success']:
                            results['tasks_completed'] += 1
                            results['total_jobs_scraped'] += task_result['jobs_scraped']
                            results['total_jobs_existing'] += task_result['jobs_existing']

                            # Track per site statistics
                            site = task.site
                            if site not in results['site_stats']:
                                results['site_stats'][site] = {'jobs': 0, 'searches': 0, 'failures': 0, 'existing': 0} # new
                            
                            results['site_stats'][site]['jobs'] += task_result['jobs_scraped']
                            results['site_stats'][site]['existing'] += task_result['jobs_existing'] # new
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
                                results['site_stats'][site] = {'jobs': 0, 'searches': 0, 'failures': 0, 'existing': 0} # new
                            results['site_stats'][site]['failures'] += 1
                    except Exception as exc:
                        self.logger.error(f"Task {task.site} - '{task.search_term}' generated an exception: {exc}")
                        results['tasks_failed'] += 1
                        results['errors'].append({
                            'task': f"{task.site} - {task.search_term}",
                            'error': str(exc)
                        })
                        
                        # Track site failures
                        site = task.site
                        if site not in results['site_stats']:
                            results['site_stats'][site] = {'jobs': 0, 'searches': 0, 'failures': 0, 'existing': 0} # new
                        results['site_stats'][site]['failures'] += 1


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
        
        self.logger.info(f"Orchestration session completed in {results['total_duration']:.2f} seconds")
        self._log_session_summary(results)
        
        return results
    
    def _execute_single_task(self, task: ScrapingTask) -> Dict[str, Any]:
        """Execute a single scraping task with retry logic"""

        task_result = {
            'success': False,
            'jobs_scraped': 0,
            'jobs_existing': 0,
            'error': None,
            'attempts': 0
        }

        for attempt in range(self.config.max_retries + 1):
            task_result['attempts'] = attempt + 1

            try:
                log_search_term = f"'{task.search_term}'"
                if task.location:
                    log_search_term += f" in '{task.location}'"
                self.logger.info(f"Attempt {attempt + 1} for {task.site} - {log_search_term}")

                # Create a new scraper instance for each task for thread safety
                if task.site == 'linkedin':
                    scraper = LinkedInScraper()
                elif task.site == 'indeed':
                    scraper = IndeedScraper()
                else:
                    raise ValueError(f"Unsupported site: {task.site}")

                # Prepare arguments for scrape_jobs
                kwargs = {'max_jobs': task.max_jobs}
                final_search_term = task.search_term

                if task.location:
                    if isinstance(scraper, IndeedScraper):
                        kwargs['location'] = task.location
                    else: # For LinkedIn and others, append location to search term
                        final_search_term = f"{task.search_term} {task.location}"
                
                kwargs['search_term'] = final_search_term

                # Execute scraping
                scrape_result = scraper.scrape_jobs(**kwargs)
                scraped_jobs = scrape_result["scraped_jobs"]
                jobs_existing = scrape_result["jobs_existing"]


                task_result['success'] = True
                task_result['jobs_scraped'] += len(scraped_jobs)
                task_result['jobs_existing'] += jobs_existing

                # Process immediately if configured
                if self.config.process_immediately:
                    processing_stats = self.pipeline.process_pending_jobs()
                    task_result['jobs_processed'] = processing_stats['processed']

                self.logger.info(f"Task completed successfully: {task_result['jobs_scraped']} new jobs, {task_result['jobs_existing']} existing jobs.")
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
        self.logger.info(f"Duration: {results['total_duration']:.2f} seconds")
        self.logger.info(f"Tasks completed: {results['tasks_completed']}")
        self.logger.info(f"Tasks failed: {results['tasks_failed']}")
        self.logger.info(f"Total new jobs scraped: {results['total_jobs_scraped']}")
        self.logger.info(f"Total existing jobs found: {results['total_jobs_existing']}") # new
        
        if 'total_jobs_processed' in results:
            self.logger.info(f"Total jobs processed: {results['total_jobs_processed']}")
        
        # Site-by-site breakdown
        if results.get('site_stats'):
            for site, stats in results['site_stats'].items():
                self.logger.info(f"{site.upper()}: {stats['jobs']} new jobs, {stats['existing']} existing, {stats['searches']} searches, {stats['failures']} failures") # new
        
        # Errors summary
        if results.get('errors'):
            self.logger.info("ERRORS:")
            for error in results['errors']:
                self.logger.info(f"  {error['task']}: {error['error']}")

    def create_daily_job_tasks(self, search_terms: List[str]) -> List[ScrapingTask]:
        """
        Create a standard set of daily scraping tasks.
        
        This is a convenience method for regular operations.
        """
        tasks = []
        
        for priority, search_term in enumerate(search_terms, 1):
            # LinkedIn tasks (usually more reliable, so lower max_jobs)
            tasks.append(ScrapingTask(
                site='linkedin',
                search_term=search_term,
                max_jobs=40,
                priority=priority
            ))
            
            # Indeed tasks (can handle more volume)
            tasks.append(ScrapingTask(
                site='indeed', 
                search_term=search_term,
                max_jobs=15,
                priority=priority
            ))
        
        return tasks

    def get_system_health(self) -> Dict[str, Any]:
        """
        Check system health - recent scraping success rates, processing backlogs, etc.
        """
        now = timezone.now()
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


class OrchestrationExamples:
    """Example orchestration patterns for different use cases"""
    
    @staticmethod
    def daily_job_scraping():
        """Standard daily job scraping routine"""
        config = OrchestrationConfig(
            delay_between_sites=60,  # 1 minute between sites
            delay_between_searches=30,  # 30 seconds between searches
            process_immediately=False,  # Batch process at end
            max_jobs_per_site=100
        )
        
        orchestrator = JobScrapingOrchestrator(config)
        
        # Define what we want to scrape daily
        search_terms = [
            "python developer",
            "data scientist", 
            "backend engineer",
            "machine learning engineer"
        ]
        
        tasks = orchestrator.create_daily_job_tasks(search_terms)
        
        return orchestrator.run_scraping_session(tasks)
    
    @staticmethod
    def urgent_market_research():
        """Quick scraping for immediate market research"""
        config = OrchestrationConfig(
            delay_between_sites=10,  # Faster for urgent needs
            delay_between_searches=5,
            process_immediately=True,  # Process right away
            max_jobs_per_site=30  # Smaller batches
        )
        
        orchestrator = JobScrapingOrchestrator(config)
        
        # Targeted research tasks
        tasks = [
            ScrapingTask("linkedin", "supply chain analyst", max_jobs=20, priority=1),
            ScrapingTask("indeed", "virtual assistant", max_jobs=30, priority=1),
            ScrapingTask("linkedin", "ui/ux designer", max_jobs=15, priority=2),
        ]
        
        return orchestrator.run_scraping_session(tasks)
    
    @staticmethod
    def conservative_scraping():
        """Very conservative scraping to avoid any rate limiting"""
        config = OrchestrationConfig(
            delay_between_sites=120,  # 2 minutes between sites
            delay_between_searches=60,  # 1 minute between searches  
            max_retries=1,  # Don't retry failures
            max_jobs_per_site=25  # Small batches
        )
        
        orchestrator = JobScrapingOrchestrator(config)
        
        tasks = [
            ScrapingTask("linkedin", "logistics manager", max_jobs=25, priority=1),
            ScrapingTask("indeed", "seo expert  ", max_jobs=25, priority=2),
        ]
        
        return orchestrator.run_scraping_session(tasks)