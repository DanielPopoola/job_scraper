from datetime import timedelta

import django_filters
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone

from scraper.models import Job, RawJobPosting, ScrapingSession


class JobFilter(django_filters.FilterSet):
    """
    Advanced filtering for Job listings.
    
    This replaces the basic filtering we had in JobListView.get_queryset()
    with a much more powerful and flexible system.
    
    URL Examples:
    /api/v1/jobs/?search=python&company=google&location_contains=new york
    """
    # Global search across multiple fields
    search = django_filters.CharFilter(
        method='filter_search',
        label='Search across title, company, and description',
        help_text='Search for keywords across job title, company name description'
    )

    # Specific field searches
    title_contains = django_filters.CharFilter(
        field_name='title',
        lookup_expr='icontains',
        label='Job title contains',
        help_text='Filter jobs where title contains this text (case insensitive)'
    )

    company_exact = django_filters.CharFilter(
        field_name='company',
        lookup_expr='iexact',
        label='Company name (exact)',
        help_text='Filter by exact company name (case insensitive)'
    )

    company_contains = django_filters.CharFilter(
        field_name='company',
        lookup_expr='icontains',
        label='Company name contains',
        help_text='Filter jobs where company name contains this text'
    )

    location_contains = django_filters.CharFilter(
        field_name='location',
        lookup_expr='icontains', 
        label='Location contains',
        help_text='Filter jobs where location contains this text'
    )

    # Date Filters
    posted_within_days = django_filters.NumberFilter(
        method='filter_posted_within_days',
        label='Posted within X days',
        help_text='Show only jobs first seen within the last X days'
    )

    active_within_days = django_filters.NumberFilter(
        method='filter_active_within_days',
        label='Active within X days', 
        help_text='Show only jobs last seen within the last X days'
    )
    
    # Date range filters
    posted_after = django_filters.DateFilter(
        field_name='first_seen',
        lookup_expr='gte',
        label='Posted after date',
        help_text='Show jobs posted after this date (YYYY-MM-DD)'
    )
    
    posted_before = django_filters.DateFilter(
        field_name='first_seen',
        lookup_expr='lte',
        label='Posted before date',
        help_text='Show jobs posted before this date (YYYY-MM-DD)'
    )

    # Status Filters
    recently_active = django_filters.BooleanFilter(
        method='filter_recently_active',
        label='Recently active jobs only',
        help_text='If true, show only jobs seen within the last 7 days'
    )
    
    # Jobs with substantial descriptions
    has_description = django_filters.BooleanFilter(
        method='filter_has_description',
        label='Jobs with substantial descriptions',
        help_text='If true, show only jobs with descriptions longer than 100 characters'
    )


    # Multi-value Filters
    companies = django_filters.CharFilter(
        method='filter_companies',
        label='Company names (comma-separated)',
        help_text='Filter by multiple companies: "Google,Meta,Apple"'
    )

    locations = django_filters.CharFilter(
        method='filter_locations',
        label='Locations (comma-separated)',
        help_text='Filter by multiple locations: "New York,San Francisco,Remote"'
    )

    skills = django_filters.CharFilter(
        method='filter_skills',
        label='Required skills (comma-separated)',
        help_text='Jobs mentioning these skills: "python,django,rest"'
    )

    # Ordering
    ordering = django_filters.OrderingFilter(
        fields=(
            ('first_seen', 'posted'),
            ('last_seen', 'last_active'),
            ('company', 'company'),
            ('title', 'title'),
            ('location', 'location'),
        ),
        field_labels={
            'posted': 'Date Posted',
            'last_active': 'Last Active',
            'company': 'Company Name',
            'title': 'Job Title',
            'location': 'Location',
        },
        label='Sort by',
        help_text='Sort results by field. Use "-" for descending: "-posted,company"'
    )

    class Meta:
        model = Job
        fields = []

    # Custom filter methods
    
    def filter_search(self, queryset, name, value):
        """
        A ranked search across multiple fields.

        Assigns a relevance score based on where the search term is found
        and orders the results by that score.
        """
        if not value:
            return queryset

        # Annotate the queryset with a relevance score
        queryset = queryset.annotate(
            relevance=Case(
                When(title__icontains=value, then=Value(3)),
                When(company__icontains=value, then=Value(2)),
                When(description__icontains=value, then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            )
        )

        # Filter out non-matches and order by relevance (highest first)
        return queryset.filter(relevance__gt=0).order_by('-relevance', '-first_seen')

    def filter_posted_within_days(self, queryset, name, value):
        """Filter job posted within last N days"""
        if not value or value < 0:
            return queryset

        cutoff_date = timezone.now() - timedelta(days=int(value))
        return queryset.filter(first_seen__gte=cutoff_date)
    
    def filter_active_within_days(self, queryset, name, value):
        """Filter jobs that were active (last_seen) within the last N days"""
        if not value or value < 0:
            return queryset
        
        cutoff_date = timezone.now() - timedelta(days=int(value))
        return queryset.filter(last_seen__gte=cutoff_date)
    
    def filter_recently_active(self, queryset, name, value):
        """Filter for jobs that are recently active (within 7 days)"""
        if not value:
            return queryset
        
        cutoff_date = timezone.now() - timedelta(days=7)
        return queryset.filter(last_seen__gte=cutoff_date)
    
    def filter_has_description(self, queryset, name, value):
        """Filter for jobs with substantial descriptions"""
        if not value:
            return queryset
        
        # Jobs with descriptions longer than 100 characters
        return queryset.extra(where=["CHAR_LENGTH(description) > %s"], params=[100])
    
    def filter_companies(self, queryset, name, value):
        """Filter by multiple companies (comma-separated)"""
        if not value:
            return queryset
        
        # Split by comma and clean up whitespace
        companies = [company.strip() for company in value.split(',') if company.strip()]

        if companies:
            company_q = Q()
            for company in companies:
                company_q |= Q(company__icontains=company)
            return queryset.filter(company_q)
        
        return queryset

    def filter_locations(self, queryset, name, value):
        """Filter by multiple locations (comma-separated)"""
        if not value:
            return queryset
        
        locations = [loc.strip() for loc in value.split(',') if loc.strip()]
        
        if locations:
            location_q = Q()
            for location in locations:
                location_q |= Q(location__icontains=location)
            return queryset.filter(location_q)
        
        return queryset
    
    def filter_skills(self, queryset, name, value):
        """
        Filter jobs that mention specific skills in the description.
        This is a simple keyword search
        """
        if not value:
            return queryset
        
        skills = [skill.strip().lower() for skill in value.split(',') if skill.strip()]
        
        if skills:
            skill_q = Q()
            for skill in skills:
                skill_q &= Q(description__icontains=skill)
            return queryset.filter(skill_q)
        
        return queryset

class RawJobPostingFilter(django_filters.FilterSet):
    """
    Filtering for raw scraped job postings.
    Useful for debugging and data quality analysis.
    """
    # Filter by source site
    site = django_filters.ChoiceFilter(
        field_name='source_site',
        choices=[
            ('linkedin', 'LinkedIn'),
            ('indeed', 'Indeed'),
        ],
        label='Source site'
    )

    # Filter by processing status
    status = django_filters.ChoiceFilter(
        field_name='processing_status',
        choices=[
            ('pending', 'Pending Processing'),
            ('processed', 'Successfully Processed'), 
            ('failed', 'Processing Failed'),
        ],
        label='Processing Status'
    )
    
    # Date filters
    scraped_within_days = django_filters.NumberFilter(
        method='filter_scraped_within_days',
        label='Scraped within X days'
    )
    
    # Text search in raw content
    raw_search = django_filters.CharFilter(
        method='filter_raw_search',
        label='Search in raw title/company/description'
    )

    class Meta:
        model = RawJobPosting
        fields = []

    def filter_scraped_within_days(self, queryset, name, value):
        if not value or value < 0:
            return queryset
        
        cutoff_date = timezone.now() - timedelta(days=value)
        return queryset.filter(scraped_at__gte=cutoff_date)

    def filter_raw_search(self, queryset, name, value):
        if not value:
            return queryset
        
        return queryset.filter(
            Q(raw_title__icontains=value) |
            Q(raw_company__icontains=value) |
            Q(raw_description__icontains=value)
        )

class ScrapingSessionFilter(django_filters.FilterSet):
    """Filter for scraping session monitoring."""
    
    site = django_filters.CharFilter(
        field_name='source_site',
        lookup_expr='iexact',
        label='Source Site'
    )

    status = django_filters.ChoiceFilter(
        field_name='status',
        choices=[
            ('running', 'Running'),
            ('completed', 'Completed Successfully'),
            ('failed', 'Failed'),
            ('partial', 'Partially Completed'),
        ],
        label='Session Status'
    )
    
    # Sessions within X days
    within_days = django_filters.NumberFilter(
        method='filter_within_days',
        label='Sessions within X days'
    )
    
    # Minimum success rate filter
    min_success_rate = django_filters.NumberFilter(
        method='filter_min_success_rate',
        label='Minimum success rate (%)'
    )
    
    ordering = django_filters.OrderingFilter(
        fields=(
            ('started_at', 'started_at'),
            ('ended_at', 'ended_at'),
            ('status', 'status'),
        ),
    )

    class Meta:
        model = ScrapingSession
        fields = []
    
    def filter_within_days(self, queryset, name, value):
        if not value or value < 0:
            return queryset
        
        cutoff_date = timezone.now() - timedelta(days=value)
        return queryset.filter(started_at__gte=cutoff_date)
    
    def filter_min_success_rate(self, queryset, name, value):
        """Filter sessions with at least X% success rate"""
        if value is None or value < 0 or value > 100:
            return queryset
        
        # Calculate success rate and filter
        filtered_ids = []
        for session in queryset:
            if session.success_rate() >= value:
                filtered_ids.append(session.id)
        
        return queryset.filter(id__in=filtered_ids)