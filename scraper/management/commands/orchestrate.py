from django.core.management.base import BaseCommand, CommandError, CommandParser

from scraper.orchestrator import (
    JobScrapingOrchestrator,
    OrchestrationConfig,
    OrchestrationExamples,
    ScrapingTask,
)


class Command(BaseCommand):
    help = 'Run coordinated job scraping across multiple sites'

    def add_arguments(self, parser: CommandParser):
        parser.add_argument(
            '--mode',
            type=str,
            choices=['daily', 'urgent', 'conservative', 'custom'],
            default='daily',
            help='Orchestration mode to run'
        )

        parser.add_argument(
            '--search-terms',
            type=str,
            nargs='+',
            default=['python developer'],
            help='Search terms to scrape'
        )

        parser.add_argument(
            '--sites',
            type=str,
            nargs='+',
            choices=['linkedin', 'indeed'],
            default=['linkedin', 'indeed'],
            help='Sites to scrape from'
        )
        
        parser.add_argument(
            '--max-jobs',
            type=int,
            default=20,
            help='Maximum jobs per search term per site'
        )
        
        parser.add_argument(
            '--delay-between-sites',
            type=int,
            default=30,
            help='Delay in seconds between different sites'
        )
        
        parser.add_argument(
            '--delay-between-searches',
            type=int,
            default=10,
            help='Delay in seconds between searches on same site'
        )
        
        parser.add_argument(
            '--process-immediately',
            action='store_true',
            help='Process jobs immediately instead of batch processing'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be scraped without actually scraping'
        )
        
        parser.add_argument(
            '--health-check',
            action='store_true',
            help='Show system health instead of running scraping'
        )
        
    def handle(self, *args, **options):
        if options['health_check']:
            self._show_health_check()
            return
        
        if options['mode'] in ['daily', 'urgent', 'conservative']:
            self._run_predefined_mode(options['mode'])
        else:
            self._run_custom_mode(options)

    def _show_health_check(self):
        """Show system health information"""
        orchestrator = JobScrapingOrchestrator()
        health = orchestrator.get_system_health()
        
        self.stdout.write(self.style.SUCCESS("=== SYSTEM HEALTH CHECK ==="))
        self.stdout.write(f"Timestamp: {health['timestamp']}")
        self.stdout.write(f"Pending processing jobs: {health['pending_processing']}")
        self.stdout.write(f"Failed processing jobs: {health['failed_processing']}")
        self.stdout.write(f"Recent sessions (24h): {health['recent_sessions_count']}")
        
        self.stdout.write("\nSite Health (Last 24 hours):")
        for site, stats in health['site_health'].items():
            self.stdout.write(f"  {site.upper()}:")
            self.stdout.write(f"    Sessions: {stats['sessions_24h']}")
            self.stdout.write(f"    Success rate: {stats['success_rate']:.1f}%")
            self.stdout.write(f"    Jobs scraped: {stats['total_jobs_24h']}")
            
            if stats['last_successful']:
                last_success = stats['last_successful'].started_at
                self.stdout.write(f"    Last successful: {last_success}")
        
        # Recommendations
        if health['pending_processing'] > 100:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️  High backlog: {health['pending_processing']} jobs pending processing"
                )
            )
            self.stdout.write("Consider running: python manage.py process_jobs")
        
        if health['failed_processing'] > 50:
            self.stdout.write(
                self.style.ERROR(
                    f"❌ Many failed jobs: {health['failed_processing']} need attention"
                )
            )

    def _run_predefined_mode(self, mode):
        """Run one of the predefined orchestration modes"""
        self.stdout.write(f"Running {mode} scraping mode...")

        try:
            if mode == 'daily':
                results = OrchestrationExamples.daily_job_scraping()
            elif mode == 'urgent':
                results = OrchestrationExamples.urgent_market_research()
            elif mode == 'conservative':
                results = OrchestrationExamples.conservative_scraping()

            self._display_results(results)

        except Exception as e:
            raise CommandError(f"Orchestration failed: {e}") from e
        
    def _run_custom_mode(self, options):
        """Run custom orchestration based on command line options"""
        
        # Create configuration
        config = OrchestrationConfig(
            delay_between_sites=options['delay_between_sites'],
            delay_between_searches=options['delay_between_searches'],
            process_immediately=options['process_immediately'],
            max_concurrent_tasks=options['max_concurrency']
        )

        # Create orchestrator
        orchestrator = JobScrapingOrchestrator(config)

        # Build tasks
        tasks = []
        priority = 1

        for search_term in options['search_terms']:
            for site in options['sites']:
                task = ScrapingTask(
                    site=site,
                    search_term=search_term,
                    max_jobs=options['max_jobs'],
                    priority=priority
                )
                tasks.append(task)
            priority += 1

        if options['dry_run']:
            self._show_dry_run(tasks, config)
            return
        
        # Execute orchestration
        self.stdout.write(f"Starting custom orchestration with {len(tasks)} tasks...")
        
        try:
            results = orchestrator.run_scraping_session(tasks)
            self._display_results(results)
        except Exception as e:
            raise CommandError(f"Custom orchestration failed: {e}") from e
    
    def _show_dry_run(self, tasks, config):
        """Show what would be executed without actually doing it"""
        self.stdout.write(self.style.WARNING("=== DRY RUN MODE ==="))
        self.stdout.write("The following tasks would be executed:")
        
        total_estimated_time = 0
        
        for i, task in enumerate(tasks, 1):
            self.stdout.write(f"\n{i}. {task.site.upper()} - '{task.search_term}'")
            self.stdout.write(f"   Max jobs: {task.max_jobs}")
            self.stdout.write(f"   Priority: {task.priority}")
            
            # Estimate time (very rough)
            estimated_minutes = (task.max_jobs / 25) * 2  # ~2 minutes per page
            total_estimated_time += estimated_minutes
            
            if i < len(tasks):
                next_task = tasks[i]
                if task.site != next_task.site:
                    delay = config.delay_between_sites
                else:
                    delay = config.delay_between_searches
                
                total_estimated_time += delay / 60  # Convert to minutes
                self.stdout.write(f"   → Wait {delay}s before next task")
        
        self.stdout.write(f"\nEstimated total time: {total_estimated_time:.1f} minutes")
        self.stdout.write("Configuration:")
        self.stdout.write(f"  Delay between sites: {config.delay_between_sites}s")
        self.stdout.write(f"  Delay between searches: {config.delay_between_searches}s")
        self.stdout.write(f"  Process immediately: {config.process_immediately}")
        
        self.stdout.write(self.style.SUCCESS("\nTo actually run: remove --dry-run flag"))
    
    def _display_results(self, results):
        """Display orchestration results in a nice format"""
        self.stdout.write(self.style.SUCCESS("\n=== ORCHESTRATION RESULTS ==="))
        
        duration = results['total_duration']
        self.stdout.write(f"Duration: {duration:.2f} seconds")
        self.stdout.write(f"Tasks completed: {results['tasks_completed']}")
        self.stdout.write(f"Tasks failed: {results['tasks_failed']}")
        self.stdout.write(f"New jobs scraped: {results['total_jobs_scraped']}")
        self.stdout.write(f"Existing jobs found: {results.get('total_jobs_existing', 0)}")

        if 'total_jobs_processed' in results:
            self.stdout.write(f"Jobs processed: {results['total_jobs_processed']}")
        
        # Site breakdown
        if results['site_stats']:
            self.stdout.write("\nSite Performance:")
            for site, stats in results['site_stats'].items():
                success_rate = 100 - (stats['failures'] / max(stats['searches'], 1) * 100)
                self.stdout.write(f"  {site.upper()}: {stats['jobs']} new jobs, "
                                f"{stats.get('existing', 0)} existing, "
                                f"{stats['searches']} searches, "
                                f"{success_rate:.1f}% success rate")
        
        # Errors
        if results['errors']:
            self.stdout.write(self.style.ERROR("\nErrors encountered:"))
            for error in results['errors']:
                self.stdout.write(f"  ❌ {error['task']}: {error['error']}")
        
        # Processing details
        if 'processing_stats' in results:
            stats = results['processing_stats']
            self.stdout.write("\nProcessing Results:")
            self.stdout.write(f"  Processed: {stats['processed']}")
            self.stdout.write(f"  Failed: {stats['failed']}")
            self.stdout.write(f"  Duplicates: {stats['duplicates_found']}")
            self.stdout.write(f"  New canonical jobs: {stats['new_canonical_jobs']}")
        
        # Next steps
        if results['tasks_completed'] > 0:
            self.stdout.write(self.style.SUCCESS("\n✅ Orchestration completed successfully!"))
            
            if not results.get('processing_stats'):
                self.stdout.write("Next step: python manage.py process_jobs")
        else:
            self.stdout.write(self.style.ERROR("\n❌ No tasks completed successfully"))
