
from django.utils import timezone as django_timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from scraper.models import Job, JobMapping, RawJobPosting, ScrapingSession


class JobSerializer(serializers.ModelSerializer):
    """
    Serializer for the canonical Job model.
    This is what most API consumers will use - clean, processed job data.
    """
    # Computed fields - not stored in database, calculated on demand
    days_since_first_seen = serializers.SerializerMethodField()
    days_since_last_seen = serializers.SerializerMethodField()
    is_recently_active = serializers.SerializerMethodField()
    
    # Make some fields more API-friendly
    first_seen_formatted = serializers.DateTimeField(
        source='first_seen', 
        format='%Y-%m-%d %H:%M:%S',
        read_only=True
    )
    last_seen_formatted = serializers.DateTimeField(
        source='last_seen',
        format='%Y-%m-%d %H:%M:%S', 
        read_only=True
    )

    class Meta:
        model = Job
        fields = ['id', 'title', 'company', 'location', 'description', 'canonical_url', 'first_seen', 'last_seen',
                  'first_seen_formatted', 'last_seen_formatted', 'days_since_first_seen', 'days_since_last_seen', 'is_recently_active',
                  'created_at', 'updated_at']
        
        read_only_fields = [
            'id', 'created_at', 'updated_at', 
            'first_seen', 'last_seen'
        ]

    @extend_schema_field(serializers.IntegerField)
    def get_days_since_first_seen(self, obj):
        """Calculate how many days ago this job was first discovered"""
        if obj.first_seen:
            delta = django_timezone.now() - obj.first_seen
            return delta.days
        return None
    
    @extend_schema_field(serializers.IntegerField)
    def get_days_since_last_seen(self, obj):
        """Calculate how many days ago this job was last confirmed active"""
        if obj.last_seen:
            delta = django_timezone.now() - obj.last_seen
            return delta.days
        return None
    
    @extend_schema_field(serializers.IntegerField)
    def get_is_recently_active(self, obj):
        """Helper field to quickly identify if job is still active"""
        return obj.is_recently_seen(days=7)

class JobSummarySerializer(serializers.ModelSerializer):
    """
    Lightweight version of JobSerializer for list views.
    When you're showing 50 jobs, you don't need full descriptions.
    """
    days_since_first_seen = serializers.SerializerMethodField()
    is_recently_active = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = ['id', 'title', 'company', 'location', 'canonical_url', 'first_seen', 'last_seen',
            'days_since_first_seen', 'is_recently_active',
        ]

    @extend_schema_field(serializers.IntegerField)
    def get_days_since_first_seen(self, obj):
        if obj.first_seen:
            delta = django_timezone.now() - obj.first_seen
            return delta.days
        return None
    
    @extend_schema_field(serializers.IntegerField)
    def get_is_recently_active(self, obj):
        return obj.is_recently_seen(days=7)
    

class RawJobPostingSerializer(serializers.ModelSerializer):
    """
    Serializer for raw scraped data
    """
    # Make the source site more readable
    source_site_display = serializers.CharField(
        source='get_source_site_display',
        read_only=True
    )
    processing_status_display = serializers.CharField(
        source='get_processing_status_display',
        read_only=True
    )
    
    # Add helpful computed fields
    days_since_scraped = serializers.SerializerMethodField()

    
    class Meta:
        model = RawJobPosting
        fields = [
            'id', 'source_site', 'source_site_display','raw_title', 'raw_company', 'raw_location', 'raw_description',
            'source_url', 'processing_status', 'processing_status_display', 'processing_error', 'scraped_at',
            'days_since_scraped',
        ]
    
    @extend_schema_field(serializers.IntegerField)
    def get_days_since_scraped(self, obj):
        """How long ago was this scraped?"""
        if obj.scraped_at:
            delta = django_timezone.now() - obj.scraped_at
            return delta.days
        return None

class ScrapingSessionSerializer(serializers.ModelSerializer):
    """
    Serializer for monitoring scraping operations.
    Shows how scraping sessions performed.
    """
    # Computed fields for better monitoring
    duration_minutes = serializers.SerializerMethodField()
    success_rate_percent = serializers.SerializerMethodField()
    jobs_per_minute = serializers.SerializerMethodField()
    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )
    
    class Meta:
        model = ScrapingSession
        fields = ['id', 'source_site', 'search_term', 'started_at', 'finished_at', 'duration_minutes',
            'jobs_attempted', 'jobs_successful', 'jobs_failed', 'success_rate_percent',
            'jobs_per_minute','status', 'status_display', 'error_message',
        ]
    
    @extend_schema_field(serializers.FloatField)
    def get_duration_minutes(self, obj):
        """How long did this scraping session take?"""
        duration = obj.duration()
        if duration:
            return round(duration.total_seconds() / 60, 2)
        return None
    
    @extend_schema_field(serializers.FloatField)
    def get_success_rate_percent(self, obj):
        """What percentage of jobs were successfully scraped?"""
        return round(obj.success_rate(), 2)
    
    @extend_schema_field(serializers.FloatField)
    def get_jobs_per_minute(self, obj):
        """Scraping efficiency metric"""
        duration = obj.duration()
        if duration and duration.total_seconds() > 0 and obj.jobs_successful > 0:
            minutes = duration.total_seconds() / 60
            return round(obj.jobs_successful / minutes, 2)
        return None

class JobMappingSerializer(serializers.ModelSerializer):
    """
    Serializer for duplicate detection mappings.
    Useful for understanding how raw jobs are grouped into canonical jobs.
    """
    
    # Include related data for context
    raw_job_title = serializers.CharField(
        source='raw_posting.raw_title',
        read_only=True
    )
    canonical_job_title = serializers.CharField(
        source='canonical_job.title',
        read_only=True
    )
    confidence_level = serializers.SerializerMethodField()
    
    class Meta:
        model = JobMapping
        fields = ['id', 'raw_posting', 'canonical_job', 'raw_job_title', 'canonical_job_title', 'similarity_score',
            'confidence_level', 'is_manual', 'created_at',
        ]
    
    def get_confidence_level(self, obj):
        """Convert similarity score to human-readable confidence"""
        score = obj.similarity_score
        if score >= 0.9:
            return 'Very High'
        elif score >= 0.8:
            return 'High'
        elif score >= 0.7:
            return 'Medium'
        elif score >= 0.6:
            return 'Low'
        else:
            return 'Very Low'


# Specialized serializers for analytics/trends

class CompanyStatsSerializer(serializers.Serializer):
    """
    For market intelligence - company hiring statistics
    This doesn't correspond to a model, it's for aggregated data
    """
    company = serializers.CharField()
    job_count = serializers.IntegerField()
    latest_posting = serializers.DateTimeField()
    avg_days_active = serializers.FloatField()


class LocationStatsSerializer(serializers.Serializer):
    """
    For market intelligence - location-based job statistics
    """
    location = serializers.CharField()
    job_count = serializers.IntegerField()
    top_companies = serializers.ListField(
        child=serializers.CharField()
    )


class SystemHealthSerializer(serializers.Serializer):
    """
    For system monitoring - overall health metrics
    """
    timestamp = serializers.DateTimeField()
    
    # Processing queue health
    pending_processing = serializers.IntegerField()
    failed_processing = serializers.IntegerField()
    
    # Recent activity
    recent_sessions_count = serializers.IntegerField()
    
    # Per-site health (this will be nested data)
    site_health = serializers.DictField()