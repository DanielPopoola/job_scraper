import re
import logging
from typing import Dict, Any, Optional, Set


class JobDataNormalizer:
    """
    Normalizes cleaned job data to standard formats.
    
    Handles:
    - Location standardization (NYC -> New York City)
    - Company name normalization (Apple Inc. -> Apple)
    - Job title standardization (Sr. -> Senior)
    """
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

        # Location mappings for common abbreviations
        self.location_mappings = {
            # US Cities
            'nyc': 'New York City',
            'sf': 'San Francisco',
            'la': 'Los Angeles',
            'dc': 'Washington',
            'philly': 'Philadelphia',
            
            # States
            'ca': 'California',
            'ny': 'New York',
            'tx': 'Texas',
            'fl': 'Florida',
            'wa': 'Washington',
            'il': 'Illinois',
            'pa': 'Pennsylvania',
            'oh': 'Ohio',
            'ga': 'Georgia',
            'nc': 'North Carolina',
            'mi': 'Michigan',
            'nj': 'New Jersey',
            'va': 'Virginia',
            'tn': 'Tennessee',
            'az': 'Arizona',
            'ma': 'Massachusetts',
            'co': 'Colorado',
            'md': 'Maryland',
            'or': 'Oregon',
            'mn': 'Minnesota',
            'wi': 'Wisconsin',
        }
        
        # Job title standardizations
        self.title_mappings = {
            # Seniority levels
            'sr.': 'Senior',
            'sr': 'Senior',
            'jr.': 'Junior',
            'jr': 'Junior',
            'lead': 'Lead',
            'principal': 'Principal',
            'staff': 'Staff',
            
            # Common abbreviations
            'dev': 'Developer',
            'eng': 'Engineer',
            'mgr': 'Manager',
            'admin': 'Administrator',
            'sys': 'System',
            'db': 'Database',
            'qa': 'Quality Assurance',
            'ui': 'User Interface',
            'ux': 'User Experience',
            'api': 'API',
            'ml': 'Machine Learning',
            'ai': 'Artificial Intelligence',
        }
        
        # Company suffixes to normalize
        self.company_suffixes = {
            'inc.', 'inc', 'incorporated',
            'llc', 'l.l.c.', 'l.l.c',
            'corp.', 'corp', 'corporation',
            'co.', 'co', 'company',
            'ltd.', 'ltd', 'limited',
            'plc', 'p.l.c.',
        }
        
        # Remote work indicators
        self.remote_indicators = {
            'remote', 'work from home', 'wfh', 'telecommute', 
            'distributed', 'anywhere', 'virtual'
        }

    def setup_logging(self):
        """Configure logging for this class"""
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)

    def normalize_job_data(self, cleaned_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize cleaned job data to standard formats.
        Args:
            cleaned_data: Cleaned job data dictionary
        Returns:
            Normalized job data dictionary
        """
        try:
            normalized_data = cleaned_data.copy()

            # Normalize each field
            normalized_data['title'] = self.normalize_title(cleaned_data.get('title', ''))
            normalized_data['company'] = self.normalize_company(cleaned_data.get('company', ''))
            normalized_data['location'] = self.normalize_location(cleaned_data.get('location', ''))

            # Keep original URL and metadata
            normalized_data['source_url'] = cleaned_data.get('source_url', '')
            normalized_data['source_site'] = cleaned_data.get('source_site', '')

            # Extract additional normalized fields
            normalized_data['is_remote'] = self.detect_remote_work(
                normalized_data['title'], normalized_data['location']
            )
            normalized_data['seniority_level'] = self.extract_seniority_level(
                normalized_data['title']
            )
            normalized_data['job_type'] = self.extract_job_type(
                normalized_data['title']
            )
            
            self.logger.debug(f"Normalized job: {normalized_data['title']} at {normalized_data['company']}")
            return normalized_data
            
        except Exception as e:
            self.logger.error(f"Error normalizing job data: {e}")
            return cleaned_data
        
    def normalize_title(self, title: str) -> str:
        """Normalize job title to standard format"""
        if not title:
            return ''
        
        normalized = title.lower()

        # Apply title mappings
        for abbrev, full in self.title_mappings.items():
            # Word boundary matching to avoid partial replacements
            pattern = r'\b' + re.escape(abbrev) + r'\b'
            normalized = re.sub(pattern, full.lower(), normalized)  

        # Convert back to title case
        normalized = normalized.title()
        
        # Fix common overcorrections
        normalized = re.sub(r'\bApi\b', 'API', normalized)
        normalized = re.sub(r'\bUi\b', 'UI', normalized)
        normalized = re.sub(r'\bUx\b', 'UX', normalized)
        normalized = re.sub(r'\bMl\b', 'ML', normalized)
        normalized = re.sub(r'\bAi\b', 'AI', normalized)
        
        return normalized
    
    def normalize_company(self, company: str) -> str:
        """Normalize company name"""
        if not company:
            return ''
        
        normalized = company.strip()

        # Remove common suffixes for normalization
        # "Apple Inc." -> "Apple"
        words = normalized.lower().split()
        if words and words[-1].rstrip(',') in self.company_suffixes:
            normalized = ' '.join(words[:-1])

         # Handle multi-word suffixes like "L.L.C."
        if len(words) >= 2:
            last_two = ' '.join(words[-2:]).lower().rstrip(',')
            if last_two in self.company_suffixes:
                normalized = ' '.join(words[:-2])
        
        # Convert to title case
        normalized = normalized.title()
        
        return normalized
    
    def normalize_location(self, location: str) -> str:
        """Normalize location to standard format"""
        if not location:
            return ''
        
        # Check if it's a remote work indicator
        if location.lower() in self.remote_indicators:
            return 'Remote'
        
        # Remove zip codes
        location_clean = re.sub(r'\s*\d{5}(-\d{4})?\s*', '', location)

        # Split by comma for analysis
        parts = [part.strip() for part in location_clean.split(',')]

        if len(parts) == 1:
            # Single word location - might be abbreviation
            single_location = parts[0].lower()
            if single_location in self.location_mappings:
                # If it's a known city abbreviation, add state if known
                mapped = self.location_mappings[single_location]
                if single_location in ['nyc', 'sf', 'la', 'dc', 'philly']:
                    state_map = {
                        'nyc': 'NY', 'sf': 'CA', 'la': 'CA', 
                        'dc': 'DC', 'philly': 'PA'
                    }
                    return f"{mapped}, {state_map[single_location]}"
                else:
                    return mapped
            else:
                return parts[0].title()
            
        elif len(parts) == 2:
            # "City, State" format - normalize each part
            city, state = parts
            
            # Normalize state
            state_lower = state.lower()
            if state_lower in self.location_mappings:
                state = self.location_mappings[state_lower].upper()
                # Convert full state names to abbreviations for consistency
                state_abbrevs = {
                    'CALIFORNIA': 'CA', 'NEW YORK': 'NY', 'TEXAS': 'TX',
                    'FLORIDA': 'FL', 'WASHINGTON': 'WA', 'ILLINOIS': 'IL',
                    'PENNSYLVANIA': 'PA', 'OHIO': 'OH', 'GEORGIA': 'GA',
                    'NORTH CAROLINA': 'NC', 'MICHIGAN': 'MI', 'NEW JERSEY': 'NJ',
                    'VIRGINIA': 'VA', 'TENNESSEE': 'TN', 'ARIZONA': 'AZ',
                    'MASSACHUSETTS': 'MA', 'COLORADO': 'CO', 'MARYLAND': 'MD',
                    'OREGON': 'OR', 'MINNESOTA': 'MN', 'WISCONSIN': 'WI'
                }
                state = state_abbrevs.get(state, state)

            # Normalize city
            city_lower = city.lower()
            if city_lower in self.location_mappings:
                city = self.location_mappings[city_lower]
            else:
                city = city.title()
            
            return f"{city}, {state.upper()}"
        
        else:
            # More complex format - just clean it up
            return ', '.join(part.title() for part in parts[:2])
        
    def detect_remote_work(self, title: str, location: str) -> bool:
        """Detect if job is remote work"""
        text_to_check = f"{title} {location}".lower()
        
        return any(indicator in text_to_check for indicator in self.remote_indicators)

    def extract_seniority_level(self, title: str) -> str:
        """Extract seniority level from job title"""
        title_lower = title.lower()
        
        seniority_keywords = {
            'intern': 'Intern',
            'junior': 'Junior',
            'associate': 'Associate', 
            'senior': 'Senior',
            'lead': 'Lead',
            'principal': 'Principal',
            'staff': 'Staff',
            'director': 'Director',
            'vp': 'VP',
            'vice president': 'VP',
            'head of': 'Head',
            'chief': 'C-Level'
        }
        
        for keyword, level in seniority_keywords.items():
            if keyword in title_lower:
                return level
        
        # Default to mid-level if no indicators found
        return 'Mid-Level'
    
    def extract_job_type(self, title: str) -> str:
        """Extract general job type/category from title"""
        title_lower = title.lower()
        
        job_types = {
            'engineer': 'Engineering',
            'developer': 'Engineering', 
            'programmer': 'Engineering',
            'architect': 'Engineering',
            'scientist': 'Data Science',
            'analyst': 'Analytics',
            'manager': 'Management',
            'director': 'Management',
            'product': 'Product',
            'design': 'Design',
            'marketing': 'Marketing',
            'sales': 'Sales',
            'recruiter': 'HR',
            'consultant': 'Consulting',
            'researcher': 'Research'
        }
        
        for keyword, job_type in job_types.items():
            if keyword in title_lower:
                return job_type
        
        return 'Other'
    
    def generate_search_tokens(self, normalized_data: Dict[str, Any]) -> Set[str]:
        """
        Generate normalized search tokens for duplicate detection.
        
        Creates a set of standardized tokens that can be used for
        similarity comparison across different data sources.
        """
        tokens = set()
        
        # Title tokens (most important for matching)
        title = normalized_data.get('title', '')
        if title:
            # Split title and normalize
            title_tokens = re.findall(r'\w+', title.lower())
            tokens.update(title_tokens)
        
        # Company tokens
        company = normalized_data.get('company', '')
        if company:
            company_tokens = re.findall(r'\w+', company.lower())
            tokens.update(company_tokens)
        
        # Location tokens (less weight but useful)
        location = normalized_data.get('location', '')
        if location and location != 'Remote':
            location_tokens = re.findall(r'\w+', location.lower())
            tokens.update(location_tokens)
        
        # Remove very common words that don't help with matching
        stop_words = {'the', 'and', 'or', 'of', 'in', 'at', 'to', 'for', 'a', 'an'}
        tokens = tokens - stop_words
        
        return tokens