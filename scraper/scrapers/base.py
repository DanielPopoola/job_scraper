import time
import logging
import traceback
from typing import Optional, Dict, List, Any
from abc import ABC, abstractmethod
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from scraper.models import RawJobPosting, ScrapingSession


class BaseScraper(ABC):
    """
    Abstract base class for all job site scrapers.
    
    Defines the common workflow and provides shared utilities.
    Each site-specific scraper inherits from this and implements the abstract methods.
    """
    def __init__(self, headless=True, implicit_wait=10):
        self.logger = logging.getLogger(f"{self.__class__.__name__}")
        self.headless = headless
        self.implicit_wait = implicit_wait
        self.driver: Optional[webdriver.Chrome] = None
        self.current_session = None
        
        # Configure logging
        self.setup_logging()

    def setup_logging(self):
        """Configure logging for this scrapper"""
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)

    def setup_driver(self):
        """Initialize Selenium WebDriver with appropriate options"""
        chrome_options = Options()

        if self.headless:
            chrome_options.add_argument('--headless')

        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.implicitly_wait(self.implicit_wait)
            self.logger.info("WebDriver initialized succesfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize WebDriver: {e}")
            raise

    def cleanup_driver(self):
        """Clean up WebDriver resources"""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("WebDriver cleaned up successfully")
            except Exception as e:
                self.logger.warning(f"Error during WebDriver cleanup: {e}")
            finally:
                self.driver = None

    def retry_with_backoff(self, func, max_retries=3, base_delay=2):
        """
        Execute a function with exponential backoff retry logic.
        
        Args:
            func: Function to execute
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds (will be exponentially increased)
            
        Returns:
            Function result if successful
            
        Raises:
            Exception: If all retries are exhausted
        """
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                return func()
            except Exception as e:
                last_exception = e

                if attempt == max_retries:
                    self.logger.error(f"All {max_retries} retries exhausted. Final error: {e}")
                    raise last_exception
                
                delay = base_delay * (2 ** attempt)
                self.logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                time.sleep(delay)
    
    def safe_find_element(self, locator, timeout=10) -> Optional[WebElement]:
        """
        Safely find an element with explicit wait and error handling.
        
        Args:
            locator: Tuple of (By, value) for element location
            timeout: Maximum wait time in seconds
            
        Returns:
            WebElement if found, None if not found or error occurs
        """
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(locator)
            )
            return element
        except TimeoutException:
            self.logger.debug(f"Element not found: {locator}")
            return None
        except Exception as e:
            self.logger.warning(f"Error finding element {locator}: {e}")
            return None
        
    def safe_find_elements(self, locator, timeout=10) -> List[WebElement]:
        """
        Safely find multiple elements with explicit wait.
        
        Returns:
            List of WebElements (empty list if none found)
        """
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(locator)
            )
            return self.driver.find_elements(*locator)
        except TimeoutException:
            self.logger.debug(f"No elements found: {locator}")
            return []
        except Exception as e:
            self.logger.warning(f"Error finding elements {locator}: {e}")
            return []
        
    def scrape_jobs(self, search_term, max_jobs=20) -> List:
        """
        Main scraping workflow. This is the public interface.
        
        Args:
            search_term: What to search for (e.g., "python developer")
            max_jobs: Maximum number of jobs to scrape
            
        Returns:
            List of successfully scraped job data dictionaries
        """
        scraped_jobs = []

        # Create scraping session for tracking
        self.current_session = ScrapingSession.objects.create(
            source_site=self.get_site_name(),
            search_term=search_term,
            status='running'
        )
        
        try:
            self.setup_driver()

            search_url = self.build_search_url(search_term)
            self.logger.info(f"Navigating to: {search_url}")

            def navigate():
                self.driver.get(search_url)
                return True
            
            self.retry_with_backoff(navigate)

            time.sleep(3)

            # Get job listings
            job_elements = self.find_job_elements()
            self.logger.info(f"Found {len(job_elements)} job elements")

            # Limit the number of jobs to scrape
            job_elements = job_elements[:max_jobs]
            self.current_session.jobs_attempted = len(job_elements)
            self.current_session.save()

            # Extract data from each job element
            for i, job_element in enumerate(job_elements):
                try:
                    self.logger.info(f"Processing job{i+1}/{len(job_elements)}")

                    job_data = self.extract_job_data(job_element)

                    if job_data and self.validate_job_data(job_data):
                        # Save to database
                        raw_job = self.save_raw_job(job_data, search_term)
                        scraped_jobs.append(job_data)
                        self.current_session.jobs_successful += 1

                        self.logger.info(f"Successfully scraped: {job_data.get('title', 'N/A')}")
                    else:
                        self.logger.warning(f"Invalid job data for job{i+1}")
                        self.current_session.jobs_failed += 1

                except Exception as e:
                    self.logger.error(f"Error processing job {i+1}: {e}")
                    self.logger.debug(traceback.format_exc())
                    self.current_session.jobs_failed += 1

                time.sleep(1)

            # Update session status
            self.current_session.status = 'completed'
            self.current_session.finished_at = datetime.now()

        except Exception as e:
            self.logger.error(f"Scraping session failed: {e}")
            self.logger.debug(traceback.format_exc())
            
            self.current_session.status = 'failed'
            self.current_session.error_message = str(e)
            self.current_session.finished_at = datetime.now()
        
        finally:
            self.current_session.save()
            self.cleanup_driver()
        
        self.logger.info(f"Scraping completed. Success: {len(scraped_jobs)} jobs")
        return scraped_jobs

    def validate_job_data(self, job_data) -> bool:
        """
        Validate that extracted job data has required fields.
        
        Args:
            job_data: Dictionary containing job information
            
        Returns:
            bool: True if data is valid, False otherwise
        """
        required_fields = ['title', 'company', 'location', 'description', 'url']
        
        for field in required_fields:
            if not job_data.get(field) or not job_data[field].strip():
                self.logger.warning(f"Missing or empty required field: {field}")
                return False
        
        return True

    def save_raw_job(self, job_data, search_term) -> RawJobPosting:
        """
        Save raw job data to database.
        Args:
            job_data: Dictionary containing job information
            search_term: The search term used to find this job
        Returns:
            RawJobPosting instance
        """
        try:
            raw_job, created = RawJobPosting.objects.get_or_create(
                source_site=self.get_site_name(),
                source_url=job_data['url'],
                defaults={
                    'raw_title': job_data['title'],
                    'raw_company': job_data['company'],
                    'raw_location': job_data['location'],
                    'raw_description': job_data['description'],
                }
            )

            if created:
                self.logger.info(f"Saved new job: {job_data['title']}")
            else:
                self.logger.info(f"Job already exists: {job_data['title']}")

            return raw_job

        except Exception as e:
            self.logger.error(f"Error saving job data: {e}")
            raise

    # Abtstract methods

    @abstractmethod
    def get_site_name(self) -> str:
        """Return the name of the job site (e.g., 'linkedin', 'indeed')"""
        pass

    @abstractmethod
    def build_search_url(self, search_term) -> Optional[str]:
        """Build the search URL for the given search term"""
        pass
    
    @abstractmethod
    def fetch_single_page(self, *args):
        """Fetch single page of data"""
        pass

    @abstractmethod 
    def extract_job_data(self, job_element) -> Optional[Dict[str, Any]]:
        """
        Extract job data from a job element.
        
        Args:
            job_element: WebElement containing job information
            
        Returns:
            dict: Job data with keys: title, company, location, description, url
        """
        pass
