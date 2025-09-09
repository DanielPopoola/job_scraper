from django.core.management.base import BaseCommand, CommandParser
from scraper.scrapers.linkedin import LinkedInScraper
from scraper.models import RawJobPosting, ScrapingSession


class Command(BaseCommand):
    help = 'Test LinkedIn scraper with a small sample'

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument('--search', type=str, default='project manager',
                            help='Search term to test with')
        parser.add_argument('--count', type=int, default=5,
                            help='Number of jobs to scrape for testing')
        
    def handle(self, *args, **options):
        search_term = options['search']
        max_jobs = options['count']

        self.stdout.write(f"Testing LinkedIn scraper...")
        self.stdout.write(f"Search term: '{search_term}'")
        self.stdout.write(f"Max jobs: {max_jobs}")
        self.stdout.write("="*50)
        
        # Initialize scraper
        scraper = LinkedInScraper()

        try:
            jobs = scraper.scrape_jobs(search_term, max_jobs=max_jobs)

            self.stdout.write(f"\n✓ Scraped {len(jobs)} jobs successfully")
            
            # Show some sample data
            for i, job in enumerate(jobs[:3], 1):  # Show first 3 jobs
                self.stdout.write(f"\nJob {i}:")
                self.stdout.write(f"  Title: {job['title']}")
                self.stdout.write(f"  Company: {job['company']}")
                self.stdout.write(f"  Location: {job['location']}")
                self.stdout.write(f"  URL: {job['url']}")
                self.stdout.write(f"  Description length: {len(job['description'])} chars")

            # Show database state
            self.stdout.write(f"\n" + "="*50)
            self.stdout.write("Database Statistics:")
            self.stdout.write(f"Total raw job postings: {RawJobPosting.objects.count()}")
            self.stdout.write(f"LinkedIn jobs: {RawJobPosting.objects.filter(source_site='linkedin').count()}")

            # Show recent scraping sessions
            recent_sessions = ScrapingSession.objects.filter(
                source_site='linkedin'
            ).order_by('-started_at')[:3]
            
            self.stdout.write(f"\nRecent LinkedIn scraping sessions:")
            for session in recent_sessions:
                self.stdout.write(f"  {session.started_at.strftime('%Y-%m-%d %H:%M')} - "
                                f"{session.status} - "
                                f"{session.jobs_successful}/{session.jobs_attempted} successful")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ LinkedIn scraper test failed: {e}"))
            # Show any error sessions
            error_sessions = ScrapingSession.objects.filter(
                source_site='linkedin', 
                status='failed'
            ).order_by('-started_at')[:1]
            
            if error_sessions:
                session = error_sessions[0]
                self.stdout.write(f"Last error: {session.error_message}")
        
        self.stdout.write(f"\nTest completed!")
        self.stdout.write(f"Next: python manage.py test_linkedin --search 'data scientist' --count 10")
