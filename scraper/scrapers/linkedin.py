import time
import urllib.parse
from datetime import datetime
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

from scraper.models import ScrapingSession

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

        self.jobs_per_page = 10  # LinkedIn's default page size
        self.current_start = 0  # Track pagination state
        self.search_term: str 

    def get_site_name(self) -> str:
        return 'linkedin'

    def setup_driver(self):
        """Override to skip Selenium setup - we're using requests instead"""
        self.logger.info("Using requests-based scraping for LinkedIn")
        pass

    def cleanup_driver(self):
        """Override to skip Selenium cleanup"""
        pass
    
    def build_search_url(self, search_term) -> str:
        """Build the initial search URL - required by BaseScraper"""
        self.search_term = search_term
        return self._build_search_url_with_pagination(search_term, 0)
    
    def _build_search_url_with_pagination(self, search_term: str, start: int) -> str:
        """Build search URL with pagination parameters"""
        params = {
            'keywords': search_term,
            'start': start,
        }
        return f"{self.jobs_search_api}?{urllib.parse.urlencode(params)}"

    def find_job_elements(self):
        """
        Fetch and return job elements from current page - required by BaseScraper
        
        This method handles the HTTP request and returns parsed job elements.
        """
        try:
            # Build URL for current pagination state
            search_url = self._build_search_url_with_pagination(
                self.search_term, self.current_start
            )
            
            self.logger.info(f"Fetching LinkedIn jobs from: {search_url}")
            
            # Make the request with retry logic
            def make_request():
                response = requests.get(search_url, headers=self.headers)
                response.raise_for_status()
                return response
            
            response = self.retry_with_backoff(make_request)
            
            # Parse HTML response
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Find job listing elements
            job_elements = [
                li for li in soup.find_all("li") 
                if li.find("div", {"class": "base-card"})
            ]
            
            self.logger.info(f"Found {len(job_elements)} job elements on current page")
            
            # Update pagination state for next call
            self.current_start += 1
            
            return job_elements
            
        except requests.RequestException as e:
            self.logger.error(f"Network error fetching jobs: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error parsing job elements: {e}")
            return []
        
    def extract_job_data(self, job_element) -> Optional[Dict[str, Any]]:
        """
        Extract job data from a single job element - required by BaseScraper
        
        Args:
            job_element: BeautifulSoup element containing job information
            
        Returns:
            Dict with job data or None if extraction fails
        """
        try:
            # Get the base card element
            base_card = job_element.find("div", {"class": "base-card"})
            if not base_card or not base_card.get("data-entity-urn"):
                self.logger.warning("No job ID found in job element")
                return None
            
            # Extract job ID from URN
            job_id = base_card.get("data-entity-urn").split(":")[-1]
            
            # Extract basic job information
            title_elem = job_element.find("h3", {"class": "base-search-card__title"})
            company_elem = (
                job_element.find("a", {"class": "hidden-nested-link"}) or 
                job_element.find("h4", {"class": "base-search-card__subtitle"})
            )
            location_elem = job_element.find("span", {"class": "job-search-card__location"})
            
            # Extract text content
            title = title_elem.get_text(strip=True)
            company = company_elem.get_text(strip=True)
            location = location_elem.get_text(strip=True)
            
            # Build job detail URL
            job_url = f"{self.job_detail_api}/{job_id}"
            
            # Fetch detailed description (with retry logic)
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
        """
        Fetch detailed job description from job posting URL
        
        Args:
            job_url: Full URL to job detail page
            
        Returns:
            Job description text or None if failed
        """
        try:
            def fetch_description():
                response = requests.get(job_url, headers=self.headers)
                response.raise_for_status()
                return response
            
            # Use retry logic for description fetching
            response = self.retry_with_backoff(fetch_description)
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Look for the description container
            desc_div = soup.find("div", class_="description__text description__text--rich")
            
            if desc_div:
                # Look for the main content markup
                markup_div = desc_div.find("div", class_="show-more-less-html__markup")
                
                if markup_div:
                    # Extract text from paragraphs, lists, etc.
                    text_parts = []
                    for elem in markup_div.find_all(['p', 'ul', 'li', 'div']):
                        text = elem.get_text(" ", strip=True)
                        if text:
                            text_parts.append(text)
                    
                    return " ".join(text_parts)
            
            self.logger.warning(f"No description found for job: {job_url}")
            return None
            
        except requests.RequestException as e:
            self.logger.error(f"Network error fetching description from {job_url}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error parsing job description from {job_url}: {e}")
            return None
        
    def scrape_jobs(self, search_term, max_jobs=50):
        """
        Override the base scraping workflow to handle LinkedIn's pagination properly.
        
        This method coordinates multiple page requests to get the desired number of jobs.
        """
        scraped_jobs = []

        # Create scraping session
        self.current_session = ScrapingSession.objects.create(
            source_site=self.get_site_name(),
            search_term=search_term,
            status='running'
        )

        try:
            # Initialize jos
            self.current_start = 0
            self.search_term  = search_term

            # Calculate how many pages we might need
            estimated_pages = (max_jobs // self.jobs_per_page) + 1
            self.logger.info(f"Planning to fetch up to {estimated_pages} pages for {max_jobs} jobs")

            jobs_collected = 0
            pages_fetched = 0
            
            while jobs_collected < max_jobs and pages_fetched < 10:
                self.logger.info(f"Fetching page {pages_fetched + 1}, jobs collected: {jobs_collected}")

                # Get job element from current page
                job_elements = self.find_job_elements()

                if not job_elements:
                    self.logger.info("No more job elements found, stopping pagination")
                    break

                # Update session with attempted jobs
                self.current_session.jobs_attempted += len(job_elements)
                self.current_session.save()

                # Process each job element
                for job_element in job_elements:
                    if jobs_collected >= max_jobs:
                        break

                    try:
                        job_data = self.extract_job_data(job_element)

                        if job_data and self.validate_job_data(job_data):
                            # Save to database
                            self.save_raw_job(job_data, search_term)
                            scraped_jobs.append(job_data)
                            jobs_collected += 1
                            self.current_session.jobs_successful += 1

                            self.logger.info(f"Successfully scraped: {job_data.get('title', 'N/A')}")
                        else:
                            self.logger.warning("Invalid job data, skipping")
                            self.current_session.jobs_failed += 1

                    except Exception as e:
                        self.logger.error(f"Error processing job: {e}")
                        self.current_session.jobs_failed += 1

                pages_fetched += 1

                if jobs_collected < max_jobs:
                    time.sleep(2)

            # Update session status
            self.current_session.status = 'completed'
            self.current_session.finished_at = datetime.now()
            
            self.logger.info(f"LinkedIn scraping completed successfully: {jobs_collected} jobs")

        except Exception as e:
            self.logger.error(f"LinkedIn scraping failed: {e}")
            self.current_session.status = 'failed'
            self.current_session.error_message = str(e)
            self.current_session.finished_at = datetime.now()
        finally:
            self.current_session.save()
        
        return scraped_jobs