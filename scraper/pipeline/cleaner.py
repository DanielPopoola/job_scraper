import re
import logging
from typing import Dict, Optional, Any
from html import unescape


class JobDataCleaner:
    """
    Cleans raw job data from various sources.
    
    Handles common data quality issues like:
    - HTML entities and extra whitespace
    - Inconsistent text formatting
    - Missing or placeholder data
    """
    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

        # Common patterns to clean
        self.whitespace_pattern = re.compile(r'\s+')
        self.html_tag_pattern = re.compile(r'<[^>]+>')
        self.special_chars_pattern = re.compile(r'[^\w\s\-.,()&]')

        # Placeholder values that indicate missing data
        self.missing_indicators = {
            'description': ['no description available', 'description not available', '', 'n/a', 'na'],
            'company': ['unknown company', 'n/a', 'na', ''],
            'location': ['unknown location', 'n/a', 'na', ''],
        }

    def clean_job_data(self, raw_job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clean raw job data from scrapers.
        
        Args:
            raw_job_data: Raw job data dictionary
            
        Returns:
            Cleaned job data dictionary
        """
        try:
            cleaned_data = {}

            cleaned_data['title'] = self.clean_title(raw_job_data.get('title', ''))
            cleaned_data['company'] = self.clean_company(raw_job_data.get('company', ''))
            cleaned_data['location'] = self.clean_location(raw_job_data.get('location', ''))
            cleaned_data['description'] = self.clean_description(raw_job_data.get('description', ''))

            # Keep original URL and metadata
            cleaned_data['source_url'] = raw_job_data.get('source_url', '')
            cleaned_data['source_site'] = raw_job_data.get('source_site', '')
            
            self.logger.debug(f"Cleaned job: {cleaned_data['title']} at {cleaned_data['company']}")
            return cleaned_data
        
        except Exception as e:
            self.logger.error(f"Error cleaning job data: {e}")
            return raw_job_data
        
    def clean_title(self, title: str) -> str:
        """Clean job title text"""
        if not title:
            return ''
        
        cleaned = self._basic_text_clean(title)

        # Remove common prefixes/suffixes that add noise
        noise_patterns = [
            r'^(job|position|role):\s*',  # "Job: Data Scientist"
            r'\s*-\s*(remote|hybrid|onsite)$',  # "Data Scientist - Remote"
            r'\s*\([^)]*\)$',  # Remove trailing parentheses
        ]

        for pattern in noise_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        cleaned = cleaned.title()

        return cleaned.strip()
    
    def clean_company(self, company: str) -> str:
        """Clean company name"""
        if not company:
            return ''
 
        cleaned = self._basic_text_clean(company)

        # Check if it's a missing indicator
        if cleaned.lower() in self.missing_indicators['company']:
            return ''
        
        return cleaned.strip()
    
    def clean_location(self, location: str) -> str:
        """Clean location text"""
        if not location:
            return ''
        
        cleaned = self._basic_text_clean(location)
        
        # Check if it's a missing indicator
        if cleaned.lower() in self.missing_indicators['location']:
            return ''
        
        # Remove extra details in parentheses for Indeed locations
        # "Houston, TX 77002 (Downtown area)" -> "Houston, TX 77002"
        cleaned = re.sub(r'\s*\([^)]+\)$', '', cleaned)
        
        return cleaned.strip()
    
    def clean_description(self, description: str) -> str:
        """Clean job description text"""
        if not description:
            return ''
        
        # Check if it's a missing indicator first
        if description.lower().strip() in self.missing_indicators['description']:
            return ''
        
        cleaned = self._basic_text_clean(description)
        
        # Remove HTML tags (sometimes scraped descriptions have HTML)
        cleaned = self.html_tag_pattern.sub(' ', cleaned)
        
        # Normalize whitespace more aggressively for descriptions
        cleaned = self.whitespace_pattern.sub(' ', cleaned)
        
        # Remove excessive repetition (sometimes scraped text has duplicated sentences)
        cleaned = self._remove_repetitive_text(cleaned)
        
        return cleaned.strip()
    
    def _basic_text_clean(self, text: str) -> str:
        """Apply basic text cleaning operations"""
        if not text:
            return ''
        
        # Decode HTML entities
        text = unescape(text)

        # Normalize whitespace
        text = self.whitespace_pattern.sub(' ', text)

        # Remove control characters but keep basic punctuation
        text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t')

        return text.strip()
    
    def _remove_repetitive_text(self, text:str) -> str:
        """Remove obviously repetitive sentences from text"""
        if not text or len(text) < 100:
            return text
        
        # Split into sentences
        sentences = re.split(r'[.!?]+', text)

        # Remove duplicate sentences
        seen_sentences = set()
        unique_sentences = []

        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and sentence.lower() not in seen_sentences:
                seen_sentences.add(sentence.lower())
                unique_sentences.append(sentence)

        return '. '.join(unique_sentences)

    def validate_cleaned_data(self, cleaned_data: Dict[str, Any]) -> bool:
        """
        Validate that cleaned data meets minimum quality standards.
        Args:
            cleaned_data: Dictionary of cleaned job data 
        Returns:
            True if data passes validation, False otherwise
        """
        # Must have title
        if not cleaned_data.get('title') or not cleaned_data['title'].strip():
            self.logger.warning("Missing job title after cleaning")
            return False
        
        # Must have either company or location
        has_company = bool(cleaned_data.get('company', '').strip())
        has_location = bool(cleaned_data.get('location', '').strip())

        if not has_company and not has_location:
            self.logger.warning("Missing both company and location after cleaning")
            return False
        
        # Title should be reasonable length
        title_length = len(cleaned_data['title'])
        if title_length < 3 or title_length > 200:
            self.logger.warning(f"Unusual title length: {title_length} characters")
            return False
        
        return True
    
    def get_cleaning_stats(self, original_data: Dict[str, Any], cleaned_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate statistics about what was cleaned.
        
        Useful for monitoring data quality and cleaning effectiveness.
        """
        stats = {}
        
        for field in ['title', 'company', 'location', 'description']:
            original_key = f'{field}' if f'{field}' in original_data else field
            original_val = original_data.get(original_key, '')
            cleaned_val = cleaned_data.get(field, '')
            
            stats[field] = {
                'original_length': len(str(original_val)),
                'cleaned_length': len(str(cleaned_val)),
                'chars_removed': len(str(original_val)) - len(str(cleaned_val)),
                'was_missing': not bool(str(original_val).strip()),
                'is_empty_after_cleaning': not bool(str(cleaned_val).strip())
            }
        
        return stats