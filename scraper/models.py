from django.db import models
from django.utils import timezone


class RawJobPosting(models.Model):
    """
    Stores exactly what we scraped from job sites.
    This is our "source of truth" for the raw data.
    """
    # Source tracking
    source_site = models.CharField(
        max_length=50,
        choices=[
            ('linkedin', 'LinkedIn'),
            ('indeed', 'Indeed'),
        ],
        help_text="Which site this was scraped from"
    )

    # Raw scraped data (exactly as found on the site)
    raw_title = models.TextField(help_text="Job title as it appears on the site")
    raw_company = models.TextField(help_text="Company name as it appears on the site")
    raw_location = models.TextField(help_text="Location as it appears on the site")
    raw_description = models.TextField(help_text="Full job description")
    
    # Metadata
    source_url = models.URLField(max_length=500, help_text="Direct link to the job posting")
    scraped_at = models.DateTimeField(auto_now_add=True)

    # Processing status tracking
    processing_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending Processing'),
            ('processed', 'Successfully Processed'),
            ('failed', 'Processing Failed'),
        ],
        default='pending'
    )

    # Error tracking for debugging
    processing_error = models.TextField(
        blank=True, 
        null=True,
        help_text="Error message if processing failed"
    )

    class Meta:
        # Prevent duplicate scraping of the same URL
        unique_together = ['source_site', 'source_url']
        indexes = [
            models.Index(fields=['source_site', 'scraped_at']),
            models.Index(fields=['processing_status']),
        ]
    
    def __str__(self):
        return f"{self.source_site}: {self.raw_title[:50]}..."
    

class Job(models.Model):
    """
    Canonical, normalized job posting.
    Multiple RawJobPostings can map to the same Job (duplicates).
    """
    # Normalized/cleaned data
    title = models.CharField(max_length=200, help_text="Normalized job title")
    company = models.CharField(max_length=100, help_text="Normalized company name")
    location = models.CharField(max_length=100, help_text="Normalized location")
    description = models.TextField(help_text="Cleaned job description")
    
    # Best URL (prefer LinkedIn over Indeed, for example)
    canonical_url = models.URLField(max_length=500)
    
    # Temporal tracking
    first_seen = models.DateTimeField(help_text="When we first discovered this job")
    last_seen = models.DateTimeField(help_text="When we last confirmed this job still exists")
    
    # Useful for analytics
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['company', 'location']),
            models.Index(fields=['first_seen']),
            models.Index(fields=['last_seen']),
        ]
    
    def __str__(self):
        return f"{self.title} at {self.company}"
    
    def is_recently_seen(self, days=7):
        """Helper method to check if job was seen recently"""
        from datetime import timedelta
        return self.last_seen >= timezone.now() - timedelta(days=days)


class JobMapping(models.Model):
    """
    Links raw job postings to their canonical job.
    Tracks our confidence in the duplicate detection.
    """
    
    raw_posting = models.ForeignKey(
        RawJobPosting, 
        on_delete=models.CASCADE,
        help_text="The raw scraped posting"
    )
    
    canonical_job = models.ForeignKey(
        Job, 
        on_delete=models.CASCADE,
        help_text="The canonical job this maps to"
    )
    
    # Track our confidence in this mapping
    similarity_score = models.FloatField(
        help_text="Jaccard similarity score (0.0 to 1.0)"
    )
    
    # When this mapping was created
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Track if this was manual override or automatic
    is_manual = models.BooleanField(
        default=False,
        help_text="True if a human manually verified this mapping"
    )
    
    class Meta:
        # Each raw posting can only map to one canonical job
        unique_together = ['raw_posting', 'canonical_job']
        indexes = [
            models.Index(fields=['similarity_score']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Mapping (score: {self.similarity_score:.2f}): {self.raw_posting.source_site} → Job#{self.canonical_job.id}"


class ScrapingSession(models.Model):
    """
    Track scraping runs for monitoring and debugging.
    Helps answer: "How did the last scraping run go?"
    """
    
    source_site = models.CharField(max_length=50)
    search_term = models.CharField(max_length=100)
    
    # Session timing
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    
    # Results
    jobs_attempted = models.IntegerField(default=0)
    jobs_successful = models.IntegerField(default=0)
    jobs_failed = models.IntegerField(default=0)
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=[
            ('running', 'Running'),
            ('completed', 'Completed Successfully'),
            ('failed', 'Failed'),
            ('partial', 'Partially Completed'),
        ],
        default='running'
    )
    
    # Error information
    error_message = models.TextField(blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['source_site', 'started_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.source_site} scraping ({self.search_term}) - {self.status}"
    
    def duration(self):
        """Calculate how long the scraping session took"""
        if self.finished_at:
            return self.finished_at - self.started_at
        return None
    
    def success_rate(self):
        """Calculate success percentage"""
        if self.jobs_attempted == 0:
            return 0
        return (self.jobs_successful / self.jobs_attempted) * 100