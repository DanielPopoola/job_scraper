import urllib.parse
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from django.utils import timezone

from scraper.models import ScrapingSession

from ..decorators import paginated_data
from .base import BaseScraper


class LinkedInScraper(BaseScraper):
    """
    A scraper for LinkedIn job postings.
    It uses LinkedIn's guest API for fetching job data, which is more stable
    than scraping the main site's HTML.
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.jobs_search_api = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        self.job_detail_api = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        self.jobs_per_page = 10
        self.search_term: str
        self.jobs_existing_count = 0

    def get_site_name(self) -> str:
        return 'linkedin'

    def setup_driver(self):
        self.logger.info("Using requests-based scraping for LinkedIn")
        pass

    def cleanup_driver(self):
        pass
    
    def build_search_url(self, search_term: str, start: int = 0) -> str | None:
        """
        Build search URL for LinkedIn, including pagination.
        """
        params = {'keywords': search_term, 'start': start}
        return f"{self.jobs_search_api}?{urllib.parse.urlencode(params)}"
        

    def find_job_elements(self, start: int = 0):
        try:
            search_url = self.build_search_url(self.search_term, start)
            self.logger.info(f"Fetching LinkedIn jobs from: {search_url}")
            
            def make_request():
                response = requests.get(search_url, headers=self.headers)
                response.raise_for_status()
                return response
            
            response = self.retry_with_backoff(make_request)
            soup = BeautifulSoup(response.text, "html.parser")
            job_elements = [li for li in soup.find_all("li") if li.find("div", {"class": "base-card"})]
            self.logger.info(f"Found {len(job_elements)} job elements on current page")
            return job_elements
        except requests.RequestException as e:
            self.logger.error(f"Network error fetching jobs: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error parsing job elements: {e}")
            return []
        
    def extract_job_data(self, job_element) -> Optional[Dict[str, Any]]:
        try:
            base_card = job_element.find("div", {"class": "base-card"})
            if not base_card or not base_card.get("data-entity-urn"):
                self.logger.warning("No job ID found in job element")
                return None
            
            job_id = base_card.get("data-entity-urn").split(":")[-1]
            title = job_element.find("h3", {"class": "base-search-card__title"}).get_text(strip=True)
            company = (job_element.find("a", {"class": "hidden-nested-link"}) or job_element.find("h4", {"class": "base-search-card__subtitle"})).get_text(strip=True)
            location = job_element.find("span", {"class": "job-search-card__location"}).get_text(strip=True)
            job_url = f"{self.job_detail_api}/{job_id}"
            description = self._get_job_description(job_url)
            
            return {
                "title": title,
                "company": company,
                "location": location,
                "url": job_url,
                "description": description or "Description not available",
            }
        except Exception as e:
            self.logger.error(f"Error extracting job data: {e}")
            return None
    
    def _get_job_description(self, job_url: str) -> Optional[str]:
        try:
            def fetch_description():
                response = requests.get(job_url, headers=self.headers)
                response.raise_for_status()
                return response
            
            response = self.retry_with_backoff(fetch_description)
            soup = BeautifulSoup(response.text, "html.parser")
            desc_div = soup.find("div", class_="description__text description__text--rich")
            
            if desc_div and (markup_div := desc_div.find("div", class_="show-more-less-html__markup")):
                return " ".join(elem.get_text(" ", strip=True) for elem in markup_div.find_all(['p', 'ul', 'li', 'div']) if elem.get_text(" ", strip=True))
            
            self.logger.warning(f"No description found for job: {job_url}")
            return None
        except Exception as e:
            self.logger.error(f"Error parsing job description from {job_url}: {e}")
            return None

    @paginated_data(page_size=10, max_pages=100, max_retries=3)
    def _fetch_pages(self, search_term: str, page: int, page_size: int) -> List[Dict[str, Any]]:
        """
        Internal generator method to fetch and process one page of jobs.
        The decorator handles the pagination loop, retries, and safeguards.
        """
        self.logger.info(f"Fetching page {page}...")
        start_index = (page - 1) * page_size
        job_elements = self.find_job_elements(start=start_index)

        self.current_session.jobs_attempted += len(job_elements)
        self.current_session.save()

        jobs_on_page = []
        for element in job_elements:
            job_data = self.extract_job_data(element)
            if job_data and self.validate_job_data(job_data):
                _, created = self.save_raw_job(job_data, search_term)
                if created:
                    jobs_on_page.append(job_data)
                    self.current_session.jobs_successful += 1
                else:
                    self.jobs_existing_count += 1
            else:
                self.current_session.jobs_failed += 1
        
        self.current_session.save()
        return jobs_on_page

    def scrape_jobs(self, search_term, max_jobs=50) -> Dict[str, Any]:
        """
        Public method to scrape jobs. It now returns a dict with scraped jobs and existing jobs count.
        """
        self.current_session = ScrapingSession.objects.create(
            source_site=self.get_site_name(),
            search_term=search_term,
            status='running'
        )
        self.search_term = search_term
        self.jobs_existing_count = 0  # Reset counter
        all_scraped_jobs = []

        try:
            job_page_generator = self._fetch_pages(search_term=search_term)

            for page_of_jobs in job_page_generator:
                all_scraped_jobs.extend(page_of_jobs)
                if len(all_scraped_jobs) >= max_jobs:
                    all_scraped_jobs = all_scraped_jobs[:max_jobs]
                    self.logger.info(f"Reached max_jobs limit ({max_jobs}).")
                    break
            
            self.current_session.status = 'completed'
            self.logger.info(f"LinkedIn scraping completed: {len(all_scraped_jobs)} new jobs scraped, {self.jobs_existing_count} existing jobs found.")

        except Exception as e:
            self.logger.error(f"LinkedIn scraping failed: {e}")
            self.current_session.status = 'failed'
            self.current_session.error_message = str(e)
        finally:
            self.current_session.finished_at = timezone.now()
            self.current_session.save()
        
        return {"scraped_jobs": all_scraped_jobs, "jobs_existing": self.jobs_existing_count}

    def validate_job_data(self, job_data):
        required_fields = ['title', 'company', 'location', 'url', 'description']
        for field in required_fields:
            if not job_data.get(field) or not job_data.get(field).strip():
                self.logger.warning(f"Validation failed: missing or empty field '{field}'")
                return False
        return True
