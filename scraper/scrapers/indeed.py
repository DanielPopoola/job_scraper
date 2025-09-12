import random
import time
import urllib.parse
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from django.utils import timezone
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .base import BaseScraper


class IndeedScraper(BaseScraper):
    """
    Scrapes the first page of Indeed results using a stable "new tab" strategy
    and clean, direct URLs to fetch job descriptions.
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.base_url = "https://www.indeed.com/jobs"

    def get_site_name(self) -> str:
        return 'indeed'
    
    def build_search_url(self, search_term: str, location: str = "remote", start: int = 0) -> str:
        params = {'q': search_term, 'l': location, 'radius': 50, 'start': start}
        query_string = urllib.parse.urlencode(params)
        return f"{self.base_url}?{query_string}"
    
    def find_job_elements(self) -> List[Any]:
        try:
            locator = (By.CLASS_NAME, 'job_seen_beacon')
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located(locator))
            return self.driver.find_elements(*locator)
        except TimeoutException:
            self.logger.warning("Timeout waiting for job elements to load on search page.")
            return []

    def _get_description_from_new_tab(self, job_url: str) -> Optional[str]:
        """
        Opens a new tab, navigates to the job URL, scrapes the description,
        and closes the tab, returning focus to the main window.
        """
        main_window = self.driver.current_window_handle
        
        try:
            self.driver.execute_script("window.open(arguments[0]);", job_url)
            new_window = [window for window in self.driver.window_handles if window != main_window][0]
            self.driver.switch_to.window(new_window)
            WebDriverWait(self.driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
            
            time.sleep(random.uniform(2, 4))
            desc_locator = (By.ID, "jobDescriptionText")
            description_element = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located(desc_locator))
            description = description_element.text
            
            return description
        except Exception as e:
            self.logger.warning(f"Could not get description from new tab ({job_url}): {e}")
            return None
        finally:
            if len(self.driver.window_handles) > 1:
                self.driver.close()
            self.driver.switch_to.window(main_window)

    def extract_job_data(self, job_element: Any) -> Optional[Dict[str, Any]]:
        """
        Extracts all data for a job, cleaning the URL before using the new tab strategy.
        """
        try:
            redirect_url = job_element.find_elements(By.TAG_NAME, "a")[0].get_attribute("href")
            if not redirect_url:
                self.logger.warning("Could not find job URL in element.")
                return None

            # --- NEW URL CLEANING LOGIC ---
            parsed_url = urllib.parse.urlparse(redirect_url)
            job_key = urllib.parse.parse_qs(parsed_url.query).get('jk', [None])[0]

            if not job_key:
                self.logger.warning(f"Could not parse job key from URL: {redirect_url}")
                clean_job_url = redirect_url # Fallback to original url
            else:
                clean_job_url = f"https://www.indeed.com/viewjob?jk={job_key}"
            # --- END NEW LOGIC ---

            soup = BeautifulSoup(job_element.get_attribute('innerHTML'), 'html.parser')
            title = soup.select('.jobTitle')[0].get_text(strip=True)
            company = soup.find(attrs={'data-testid': 'company-name'}).get_text(strip=True)
            location = soup.find(attrs={'data-testid': 'text-location'}).get_text(strip=True)

            description = self._get_description_from_new_tab(clean_job_url)

            return {
                'title': title, 'company': company, 'location': location,
                'description': description or "Description not available.",
                'url': redirect_url # Save the original source URL
            }
        except Exception as e:
            self.logger.error(f"Error extracting basic job data: {e}")
            return None
    
    def scrape_jobs(self, search_term: str, max_jobs: int = 15, location: str = "United States") -> List[Dict[str, Any]]:
        from scraper.models import ScrapingSession
        self.current_session = ScrapingSession.objects.create(
            source_site=self.get_site_name(),
            search_term=f"{search_term} in {location}",
            status='running'
        )
        scraped_jobs = []

        try:
            self.setup_driver()
            search_url = self.build_search_url(search_term, location, start=0)
            self.driver.get(search_url)
            time.sleep(random.uniform(3, 5))
            
            job_elements = self.find_job_elements()
            if not job_elements:
                raise Exception("No job elements found on the first page.")

            num_jobs_to_process = min(max_jobs, len(job_elements))
            self.current_session.jobs_attempted = num_jobs_to_process

            for i in range(num_jobs_to_process):
                job_element = job_elements[i]
                self.logger.info(f"Processing job {i+1}/{num_jobs_to_process}...")
                job_data = self.extract_job_data(job_element)
                
                if job_data and self.validate_job_data(job_data):
                    self.save_raw_job(job_data, search_term)
                    scraped_jobs.append(job_data)
                    self.current_session.jobs_successful += 1
                else:
                    self.current_session.jobs_failed += 1
            
            self.current_session.status = 'completed'
        except Exception as e:
            self.logger.error(f"Indeed scraping failed: {e}")
            self.current_session.status = 'failed'
            self.current_session.error_message = str(e)
        finally:
            self.current_session.finished_at = timezone.now()
            self.current_session.save()
            self.cleanup_driver()
        
        self.logger.info(f"Indeed scraping finished. Scraped {len(scraped_jobs)} jobs.")
        return scraped_jobs

    def validate_job_data(self, job_data: Dict[str, Any]) -> bool:
        return bool(job_data.get('title') and job_data.get('url'))