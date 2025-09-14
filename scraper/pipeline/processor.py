import logging
import traceback
from datetime import datetime
from typing import Any, Dict, Optional

from scraper.models import Job, JobMapping, RawJobPosting

from .cleaner import JobDataCleaner
from .duplicate_detector import JobDuplicateDetector
from .normalizer import JobDataNormalizer


class JobProcessingPipeline:
    """
    Processes raw job postings through cleaning, normalization, and duplicate detection.
    """
    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cleaner = JobDataCleaner()
        self.normalizer = JobDataNormalizer()
        self.duplicate_detector = JobDuplicateDetector()

    

    def process_pending_jobs(self) -> Dict[str, int]:
        """
        Process all pending RawJobPosting records.
        Returns:
            Dict with processing statistics
        """
        stats = {
            'processed': 0,
            'failed': 0,
            'duplicates_found': 0,
            'new_canonical_jobs': 0
        }

        # Get all pending raw job postings
        pending_jobs = RawJobPosting.objects.filter(processing_status='pending')

        self.logger.info(f"Processing {pending_jobs.count()} pending job postings")

        for raw_job in pending_jobs:
            try:
                self.logger.debug(f"Processing job {raw_job.id}: {raw_job.raw_title}")

                # Clean row data
                cleaned_data = self._clean_job_data(raw_job)
                if not cleaned_data:
                    self._mark_as_failed(raw_job, "Data cleaning failed")
                    stats['failed'] += 1
                    continue
                

                # Normalize data
                normalized_data = self._normalize_job_data(cleaned_data)
                if not normalized_data:
                    self._mark_as_failed(raw_job, "Data normalization failed")
                    stats['failed'] += 1
                    continue

                # Create canonical job
                canonical_job, is_duplicate = self._find_or_create_canonical_job(normalized_data)

                # Create mapping
                similarity_score = 1.0
                if is_duplicate:
                    canonical_job_dict = {
                        'title': canonical_job.title,
                        'company': canonical_job.company,
                        'location': canonical_job.location,
                        'description': canonical_job.description,
                    }
                    similarity_score = self.duplicate_detector.calculate_similarity(
                        normalized_data, canonical_job_dict
                    )
                    stats['duplicates_found'] += 1

                    canonical_job.last_seen = raw_job.scraped_at
                    canonical_job.save()
                else:
                    stats['new_canonical_jobs'] += 1

                # Create the mapping
                JobMapping.objects.create(
                    raw_posting=raw_job,
                    canonical_job=canonical_job,
                    similarity_score=similarity_score
                )

                # Mark as processed
                self._mark_as_processed(raw_job)
                stats['processed'] += 1

                self.logger.debug(f"Successfully processed job {raw_job.id}")

            except Exception as e:
                error_message = f"Pipeline processing failed: {str(e)}"
                self.logger.error(f"Error processing job {raw_job.id}: {error_message}")
                self.logger.debug(traceback.format_exc())
                
                self._mark_as_failed(raw_job, error_message)
                stats['failed'] += 1

        self.logger.info(f"Processing complete. Stats: {stats}")
        return stats
    
    def _clean_job_data(self, raw_job: RawJobPosting) -> Optional[Dict[str, Any]]:
        """Clean raw job data"""
        try:
            return self.cleaner.clean_job_data({
                'raw_title': raw_job.raw_title,
                'raw_company': raw_job.raw_company,
                'raw_location': raw_job.raw_location,
                'raw_description': raw_job.raw_description,
                'source_url': raw_job.source_url,
                'source_site': raw_job.source_site,
            })
        except Exception as e:
            self.logger.error(f"Cleaning failed for job {raw_job.id}: {e}")
            return None
        
    def _normalize_job_data(self, cleaned_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize cleaned job data"""
        try:
            return self.normalizer.normalize_job_data(cleaned_data)
        except Exception as e:
            self.logger.error(f"Normalization failed: {e}")
            return None

    def _find_or_create_canonical_job(self, normalized_data: Dict[str, Any]) -> tuple[Job, bool]:
        """
        Find existing canonical job or create new one.
        
        Returns:
            (Job instance, is_duplicate boolean)
        """
        # Find potential duplicates based on title and company
        potential_duplicates = Job.objects.filter(
            title__icontains=normalized_data['title'],
            company__icontains=normalized_data['company'],
            location__icontains=normalized_data['location']
        )

        potential_duplicates_dicts = [
            {
                'title': job.title,
                'company': job.company,
                'location': job.location,
                'description': job.description,
            }
            for job in potential_duplicates
        ]

        best_match = self.duplicate_detector.find_best_match(normalized_data, potential_duplicates_dicts)

        if best_match:
            self.logger.debug(f"Found duplicate for: {normalized_data['title']}")
            existing_job = Job.objects.get(id=best_match['id'])
            return existing_job, True
            
        # Create new canonical job
        canonical_job = Job.objects.create(
            title=normalized_data['title'],
            company=normalized_data['company'],
            location=normalized_data['location'],
            description=normalized_data['description'],
            canonical_url=normalized_data.get('url', ''),
            first_seen=datetime.now(),
            last_seen=datetime.now()
        )

        self.logger.debug(f"Created new canonical job: {canonical_job.title}")
        return canonical_job, False

    def _mark_as_processed(self, raw_job: RawJobPosting):
        """Mark raw job posting as successfully processed"""
        raw_job.processing_status = 'processed'
        raw_job.processing_error = None  # Clear any previous error
        raw_job.save()
    
    def _mark_as_failed(self, raw_job: RawJobPosting, error_message: str):
        """Mark raw job posting as failed with error message"""
        raw_job.processing_status = 'failed'
        raw_job.processing_error = error_message
        raw_job.save()
        
        self.logger.warning(f"Marked job {raw_job.id} as failed: {error_message}")
    
    def reprocess_failed_jobs(self) -> Dict[str, int]:
        """
        Retry processing jobs that previously failed.
        Useful for when you fix bugs in your pipeline logic.
        """
        failed_jobs = RawJobPosting.objects.filter(processing_status='failed')
        
        self.logger.info(f"Reprocessing {failed_jobs.count()} failed jobs")
        
        # Reset them to pending and process again
        failed_jobs.update(processing_status='pending', processing_error=None)
        
        return self.process_pending_jobs()