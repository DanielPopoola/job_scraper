from django.core.management.base import BaseCommand

from scraper.models import RawJobPosting, ScrapingSession
from scraper.scrapers.indeed import IndeedScraper


class Command(BaseCommand):
    help = 'Test Indeed scraper'
    
    def add_arguments(self, parser):
        parser.add_argument('--search', type=str, default='python developer', 
                          help='Search term to test with')
        parser.add_argument('--location', type=str, default='remote', 
                          help='Job location to search')
        parser.add_argument('--count', type=int, default=15, 
                          help='Number of jobs to scrape (max 20 due to Indeed limits)')
    
    def handle(self, *args, **options):
        search_term = options['search']
        location = options['location']
        max_jobs = options['count']
        #headless = options['headless']

        self.stdout.write("Testing Indeed scraper...")
        self.stdout.write(f"Search: '{search_term}' in '{location}'")
        self.stdout.write(f"Max jobs: {max_jobs}")
        #self.stdout.write(f"Mode: {'headless' if headless else 'visible browser'}")
        self.stdout.write("="*60)

        self.stdout.write(self.style.SUCCESS(
            "✓ Indeed Recent Discovery:\n"
            "   • Multiple pages accessible in incognito mode\n"
            "   • US locations work best (better than 'remote')\n"
            "   • Smart filtering removes fake job elements\n"
        ))

        # Initialize scraper
        scraper = IndeedScraper(headless=True)

        try:
            jobs = scraper.scrape_jobs(search_term, max_jobs=max_jobs, location=location)

            self.stdout.write(f"\n✓ Scraped {len(jobs)} jobs successfully")
            
            if jobs:
                # Show sample data
                self.stdout.write("\nSample Jobs:")
                self.stdout.write("-" * 60)

                for i, job in enumerate(jobs[:3], ):
                    self.stdout.write(f"\nJob {i}:")
                    self.stdout.write(f"  Title: {job['title']}")
                    self.stdout.write(f"  Company: {job['company']}")
                    self.stdout.write(f"  Location: {job['location']}")
                    self.stdout.write(f"  Description: {job['description'][:100]}...")
                    self.stdout.write(f"  URL: {job['url']}")

                # Data quality analysis
                self.stdout.write("\n" + "="*60)
                self.stdout.write("Data Quality Analysis:")
                
                # Count fields
                total_jobs = len(jobs)
                has_company = sum(1 for job in jobs if job['company'] != 'Unknown Company')
                has_location = sum(1 for job in jobs if job['location'] != 'Unknown Location')
                has_description = sum(1 for job in jobs if job['description'] and job['description'] != 'No description available')
                
                self.stdout.write(f"  Jobs with company info: {has_company}/{total_jobs} ({100*has_company/total_jobs:.1f}%)")
                self.stdout.write(f"  Jobs with location info: {has_location}/{total_jobs} ({100*has_location/total_jobs:.1f}%)")
                self.stdout.write(f"  Jobs with descriptions: {has_description}/{total_jobs} ({100*has_description/total_jobs:.1f}%)")
                
                # Unique companies and locations
                unique_companies = set(job['company'] for job in jobs if job['company'] != 'Unknown Company')
                unique_locations = set(job['location'] for job in jobs if job['location'] != 'Unknown Location')
                
                self.stdout.write(f"  Unique companies: {len(unique_companies)}")
                self.stdout.write(f"  Unique locations: {len(unique_locations)}")
                
            # Show database state
            self.stdout.write("\n" + "="*60)
            self.stdout.write("Database Statistics:")
            self.stdout.write(f"Total raw job postings: {RawJobPosting.objects.count()}")
            self.stdout.write(f"Indeed jobs: {RawJobPosting.objects.filter(source_site='indeed').count()}")

            # Show recent scraping sessions
            recent_sessions = ScrapingSession.objects.filter(
                source_site='indeed'
            ).order_by('-started_at')[:3]
            
            self.stdout.write("\nRecent Indeed scraping sessions:")
            for session in recent_sessions:
                duration = "N/A"
                if session.finished_at:
                    duration = str(session.finished_at - session.started_at).split('.')[0]
                
                self.stdout.write(
                    f"  {session.started_at.strftime('%Y-%m-%d %H:%M')} - "
                    f"{session.status} - "
                    f"{session.jobs_successful}/{session.jobs_attempted} successful - "
                    f"Duration: {duration}"
                )
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Indeed scraper test failed: {e}"))
            
            # Show error details from sessions
            error_sessions = ScrapingSession.objects.filter(
                source_site='indeed', 
                status='failed'
            ).order_by('-started_at')[:1]
            
            if error_sessions:
                session = error_sessions[0]
                self.stdout.write(f"Last error details: {session.error_message}")
        
        self.stdout.write("\n" + "="*60)
        self.stdout.write("Test completed!")
        self.stdout.write("\nTips for Indeed scraping:")
        self.stdout.write("• Use different search terms to avoid being flagged")
        self.stdout.write("• Run tests with delays (scraper has built-in delays)")
        self.stdout.write("• Indeed data quality varies - some fields may be missing")
        self.stdout.write("• Consider LinkedIn for higher-quality data")
        
        self.stdout.write("\nNext test: python manage.py test_indeed --search 'data scientist' --location 'New York'")