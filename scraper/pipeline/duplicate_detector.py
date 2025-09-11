import logging
from typing import Any, Dict, List, Optional, Set


class JobDuplicateDetector:
    """
    Detects duplicate job postings using Jaccard similarity and other heuristics.
    
    Handles the complex problem of identifying the same job posted across
    different platforms with slightly different formatting.
    """
    def __init__(self, similarity_threshold: float = 0.7):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.similarity_threshold = similarity_threshold

        # Weights for different matching criteria
        self.match_weights = {
            'title_similarity': 0.4,      # Most important
            'company_exact': 0.3,         # Very important
            'location_similarity': 0.3,   # Moderately important
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
    
    def find_best_match(self, new_job: Dict[str, Any], potential_duplicates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Find the best duplicate for a new job from a list of potential duplicates.
        Args:
            new_job: Normalized data for the new job
            potential_duplicates: List of existing jobs from the database
        Returns:
            The best matching job dictionary or None if no good match is found
        """
        best_match = None
        highest_similarity = 0

        for job in potential_duplicates:
            similarity = self.calculate_similarity(new_job, job)
            if similarity > highest_similarity:
                highest_similarity = similarity
                best_match = job

        if highest_similarity >= self.similarity_threshold:
            return best_match
        
        return None
    
    def calculate_similarity(self, job_a: Dict[str, Any], job_b: Dict[str, Any]) -> float:
        """
        Calculate overall similarity between two jobs.
        
        Uses multiple criteria with different weights to determine if jobs
        are likely to be the same posting from different sources.
        """
        try:
            scores = {}

            # 1. Title similarity (Jaccard + fuzzy matching)
            scores['title_similarity'] = self._calculate_title_similarity(
                job_a.get('title', ''), job_b.get('title', '')
            )

            # 2. Company exact match (high weight because company mismatch is rare for duplicates)
            scores['company_exact'] = self._calculate_company_similarity(
                job_a.get('company', ''), job_b.get('company', '')
            )
            
            # 3. Location similarity
            scores['location_similarity'] = self._calculate_location_similarity(
                job_a.get('location', ''), job_b.get('location', '')
            )
            
            # Calculate weighted average
            total_score = 0
            for criterion, score in scores.items():
                weight = self.match_weights.get(criterion, 0)
                total_score += score * weight

            #self.logger.debug(f"Similarity breakdown: {scores} --> {total_score:.3f}")
            return total_score
        
        except Exception as e:
            self.logger.error(f"Error calculating similarity: {e}")
            return 0.0
        
    def _calculate_title_similarity(self, title_a: str, title_b: str) -> float:
        """Calculate similarity between job titles using Jaccard similarity"""
        if not title_a and not title_b:
            return 0.0

        # Tokenize titles
        tokens_a = self._tokenize_text(title_a)
        tokens_b = self._tokenize_text(title_b)

        if not tokens_a or tokens_b:
            return 0.0
        
        # Calculate Jaccard similarity
        jaccard = self._jaccard_similarity(tokens_a, tokens_b)
        
        # Bonus points for exact match
        if title_a.lower().strip() == title_b.lower().strip():
            return 1.0
        
        # Penalty for very different lengths (might indicate different roles)
        length_ratio = min(len(title_a), len(title_b)) / max(len(title_a), len(title_b))
        if length_ratio < 0.5:  # One title is much longer than the other
            jaccard *= 0.8
        
        return jaccard

    def _calculate_company_similarity(self, company_a: str, company_b: str) -> float:
        """Calculate company name similarity (exact match heavily preferred)"""
        if not company_a or not company_b:
            return 0.0

        # Exact match
        if company_a.lower().strip() == company_b.lower().strip():
            return 1.0

        # Partial matching for cases like "Google" vs "Google LLC"
        shorter = min(company_a, company_b, key=len).lower().strip()
        longer = max(company_a, company_b, key=len).lower().strip()

        if shorter in longer:
            return 0.8
        
        tokens_a = self._tokenize_text(company_a)
        tokens_b = self._tokenize_text(company_b)
        
        return self._jaccard_similarity(tokens_a, tokens_b)
    
    def _calculate_location_similarity(self, location_a: str, location_b: str) -> float:
        """Calculate location similarity with geographic awareness"""
        if not location_a or not location_b:
            return 0.5
        
        # Exact match
        if location_a.lower().strip() == location_b.lower().strip():
            return 1.0
        
        # Remote work matching
        remote_indicators = {'remote', 'anywhere', 'work from home'}
        is_remote_a = any(indicator in location_a.lower() for indicator in remote_indicators)
        is_remote_b = any(indicator in location_b.lower() for indicator in remote_indicators)
        
        if is_remote_a and is_remote_b:
            return 1.0
        elif is_remote_a or is_remote_b:
            return 0.3  # One remote, one not - probably different
        
        # City/state matching
        # "San Francisco, CA" vs "SF, CA" should match
        tokens_a = self._tokenize_text(location_a)
        tokens_b = self._tokenize_text(location_b)

        return self._jaccard_similarity(tokens_a, tokens_b)
    
    def _tokenize_text(self, text: str) -> Set[str]:
        if not text:
            return set()
        
        import re
        tokens = re.findall(r'\w+', text.lower())
        return set(tokens)
    
    def _jaccard_similarity(self, tokens_a: Set[str], tokens_b: Set[str]) -> float:
        """
        Calculate Jaccard similarity between two token sets.
        
        Jaccard similarity = |intersection| / |union|
        
        Args:
            tokens_a: First set of tokens
            tokens_b: Second set of tokens
        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not tokens_a and not tokens_b:
            return 1.0  # Both empty = identical
        
        if not tokens_a or not tokens_b:
            return 0.0  # One empty, one not = completely different
        
        intersection = tokens_a.intersection(tokens_b)
        union = tokens_a.union(tokens_b)
        
        return len(intersection) / len(union)