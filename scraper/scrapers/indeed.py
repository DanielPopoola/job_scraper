import time
import random
import urllib.parse
from typing import Dict, Optional, Any, List
from datetime import datetime
from bs4 import BeautifulSoup

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from .base import BaseScraper


class IndeedScraper(BaseScraper):
    """
    Indeed job scraper that respects the login requirement after 2 pages.
    
    This scraper will only scrape the first 2 pages (about 20 jobs) to avoid
    hitting Indeed's login wall, making it suitable for sample data collection.
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Indeed-specific settings
        self.base_url = "https://www.indeed.com/jobs"
        self.jobs_per_page = 15
        self.max_pages = 1
        self.current_page = 0
        self.search_params = {}
    
    def get_site_name(self) -> str:
        return 'indeed'
    
    def build_search_url(self, search_term: str, location: str = "remote", radius: int = 50, start: int = 0) -> str:
        """
        Build Indeed search URL with pagination support.
        
        Args:
            search_term: Job search query (e.g., "python developer")
            location: Job location (default: "remote")
            radius: Search radius in miles
            start: Starting job index for pagination
            
        Returns:
            Complete Indeed search URL
        """
        self.search_params = {
            'q': search_term,
            'l': location,
            'radius': radius,
            'from': 'searchOnDesktopSerp,whereautocomplete',
            'start': start
        }

        query_string = urllib.parse.urlencode(self.search_params)
        url = f"{self.base_url}?{query_string}"

        self.logger.info(f"Built Indeed search URL: {url}")
        return url
    
    def find_job_elements(self) -> List[Any]:
        """
        Find all job elements on the current Indeed page.
        
        Returns:
            List of WebElements representing job postings
        """
        try:
            # Wait for job listings to load
            job_container_locator = (By.CLASS_NAME, 'job_seen_beacon')
            
            # Use explicit wait to ensure jobs are loaded
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(job_container_locator)
            )
            
            # Find all job elements
            job_elements = self.driver.find_elements(*job_container_locator)
            
            self.logger.info(f"Found {len(job_elements)} job elements on page {self.current_page + 1}")
            return job_elements
            
        except TimeoutException:
            self.logger.warning("Timeout waiting for job elements to load")
            return []
        except Exception as e:
            self.logger.error(f"Error finding job elements: {e}")
            return []

    def extract_job_data(self, job_element: Any) -> Optional[Dict[str, Any]]:
        """
        Extract job data from an Indeed job element.
        
        Args:
            job_element: Selenium WebElement containing job information
            
        Returns:
            Dictionary with job data or None if extraction fails
        """
        try:
            result_html = job_element.get_attribute('innerHTML')
            soup = BeautifulSoup(result_html, 'html.parser')
            
            # Extract job link first (we need this for the URL)
            try:
                link_elements = job_element.find_elements(By.TAG_NAME, "a")
                if not link_elements:
                    self.logger.warning("No link found in job element")
                    return None
                job_url = link_elements[0].get_attribute("href")
            except Exception as e:
                self.logger.warning(f"Could not extract job URL: {e}")
                return None
            
            # Extract title using your selector approach
            try:
                title_elem = soup.select('.jobTitle')[0]
                title = title_elem.get_text().strip()
            except (IndexError, AttributeError):
                self.logger.warning("Could not extract job title")
                return None
            
            # Extract company name
            try:
                company_elem = soup.find_all(attrs={'data-testid': 'company-name'})[0]
                company = company_elem.get_text().strip()
            except (IndexError, AttributeError):
                self.logger.warning("Could not extract company name")
                company = 'Unknown Company'
            
            # Extract location
            try:
                location_elem = soup.find_all(attrs={'data-testid': 'text-location'})[0]
                location = location_elem.get_text().strip()
            except (IndexError, AttributeError):
                self.logger.warning("Could not extract location")
                location = 'Unknown Location'
            
            # Extract job snippet description
            try:
                description = self.get_full_job_description(job_element)
            except (IndexError, AttributeError):
                self.logger.warning("Could not extract job description")
                description = 'No description available'
    
            return {
                'title': title,
                'company': company,
                'location': location,
                'description': description if description else "Description not available",
                'url': job_url
            }
            
        except Exception as e:
            self.logger.error(f"Error extracting job data: {e}")
            return None
    
    def get_full_job_description(self, job_element) -> Optional[str]:
        """
        Fetch full job description from Indeed's side panel.
        """
        try:
            job_element.click()
            
            description = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "jobDescriptionText"))
            )

            return description.text
        except Exception as e:
            self.logger.warning("Could not extract full job description")
            description = 'No description available'
    
    def scrape_jobs(self, search_term: str, max_jobs: int = 100, location: str = "United States"):
        """
        Override the base scraping method to handle Indeed's US-only pagination.
        
        Args:
            search_term: What to search for
            max_jobs: Maximum jobs to scrape (can be higher now)
            location: Job location filter (defaults to "United States" for best results)
            
        Returns:
            List of scraped job data
        """
        
        # Create scraping session
        from scraper.models import ScrapingSession
        self.current_session = ScrapingSession.objects.create(
            source_site=self.get_site_name(),
            search_term=f"{search_term} in {location}",
            status='running'
        )
        
        scraped_jobs = []
        
        try:
            self.setup_driver()
            
            # Scrape multiple pages until we hit the limit or get enough jobs
            page_num = 0
            jobs_on_current_page = 0
            
            while len(scraped_jobs) < max_jobs and page_num < self.max_pages:
                self.current_page = page_num
                
                # Calculate start index for Indeed's pagination
                # Indeed uses start=0, start=10, start=20, etc.
                start_index = page_num * 10

                search_url = self.build_search_url(search_term, location, start=start_index)
                
                self.logger.info(f"Scraping Indeed page {page_num + 1} (jobs collected so far: {len(scraped_jobs)})")
                
                # Navigate to search page
                def navigate():
                    self.driver.get(search_url)
                    return True
                
                self.retry_with_backoff(navigate)
                
                # Small delay for page to fully load
                time.sleep(random.uniform(2, 4))
                
                # Find actual job elements on current page
                job_elements = self.find_job_elements()
                
                if not job_elements:
                    self.logger.warning(f"No job elements found on page {page_num + 1}, stopping pagination")
                    break
                
                jobs_on_current_page = len(job_elements)
                
                # Update session with attempted jobs
                self.current_session.jobs_attempted += jobs_on_current_page
                self.current_session.save()
                
                # Process each job on this page
                for i, job_element in enumerate(job_elements):
                    if len(scraped_jobs) >= max_jobs:
                        self.logger.info(f"Reached max_jobs limit ({max_jobs}), stopping")
                        break
                    
                    try:
                        self.logger.info(f"Processing job {i+1}/{jobs_on_current_page} on page {page_num + 1}")
                        
                        job_data = self.extract_job_data(job_element)
                        
                        if job_data and self.validate_job_data(job_data):
                            # Save to database
                            raw_job = self.save_raw_job(job_data, search_term)
                            scraped_jobs.append(job_data)
                            self.current_session.jobs_successful += 1
                            
                            self.logger.info(f"Successfully scraped: {job_data.get('title', 'N/A')}")
                        else:
                            self.logger.warning("Invalid job data, skipping")
                            self.current_session.jobs_failed += 1
                    
                    except Exception as e:
                        self.logger.error(f"Error processing job {i+1}: {e}")
                        self.current_session.jobs_failed += 1
                    
                    # Small delay between jobs to be polite
                    time.sleep(random.uniform(1, 2))
                
                page_num += 1
                
                # Check if we should continue to next page
                if len(scraped_jobs) < max_jobs and page_num < self.max_pages:
                    delay = random.uniform(10, 15)
                    self.logger.info(f"Waiting {delay:.1f}s before next page...")
                    time.sleep(delay)
                elif len(scraped_jobs) >= max_jobs:
                    self.logger.info("Reached target number of jobs, stopping")
                    break
            
            # Update session status
            self.current_session.status = 'completed'
            self.current_session.finished_at = datetime.now()
            
            self.logger.info(f"Indeed scraping completed: {len(scraped_jobs)} jobs scraped from {page_num} pages")
            
        except Exception as e:
            self.logger.error(f"Indeed scraping failed: {e}")
            self.current_session.status = 'failed'
            self.current_session.error_message = str(e)
            self.current_session.finished_at = datetime.now()
        
        finally:
            self.current_session.save()
            self.cleanup_driver()
        
        return scraped_jobs
    
    def validate_job_data(self, job_data):
        """
        Override validation to be more lenient with Indeed data.
        
        Indeed sometimes has missing company names or locations,
        so we'll be more flexible than the base validation.
        """
        # Must have title and URL at minimum
        if not job_data.get('title') or not job_data.get('title').strip():
            return False
        if not job_data.get('url') or not job_data.get('url').strip():
            return False
        
        # Other fields can be missing or "Unknown"
        return True