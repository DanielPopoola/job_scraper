from collections import Counter
from datetime import timedelta
import logging
import re
import threading

from django.db.models import Avg, Count, F, Max
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from scraper.models import Job, JobMapping, RawJobPosting, ScrapingSession
from scraper.orchestrator import JobScrapingOrchestrator, ScrapingTask, OrchestrationConfig

from .filters import JobFilter, RawJobPostingFilter, ScrapingSessionFilter
from .pagination import CustomPagination
from .serializers import (
    CompanyStatsSerializer,
    JobSerializer,
    JobSummarySerializer,
    LocationStatsSerializer,
    OrchestrationTaskSerializer,
    RawJobPostingSerializer,
    ScrapingSessionSerializer,
    SystemHealthSerializer,
    SkillStatsSerializer,
)

logger = logging.getLogger(__name__)

# =============================================================================
# API Discovery Endpoint
# =============================================================================

class APIRootView(APIView):
    """
    GET /api/v1/
    
    API discovery endpoint. Shows available endpoints and basic usage info.
    """
    @extend_schema(responses={200: OpenApiTypes.STR})
    def get(self, request):
        """Return a directory of available API endpoints"""

        # Build absolute URLS using request context
        def build_url(name):
            return request.build_absolute_uri(f'/api/v1/{name}')

        return Response({
            'message': 'Job Market Intelligence API v1',
            'documentation': 'http://job-scraper/api/',
            'endpoints': {
                'jobs': {
                    'list': build_url('jobs/'),
                    'detail': build_url('jobs/{id}/'),
                    'description': 'Canonical job postings with filtering and search',
                    'filters': ['search', 'company', 'location', 'days_since', 'ordering']
                },
                'trends': {
                    'url': build_url('trends/'),
                    'description': 'Market intelligence and analytics',
                    'metrics': ['companies', 'locations', 'activity', 'all']
                },
                'monitoring': {
                    'health': build_url('health/'),
                    'quick_stats': build_url('quick-stats/'),
                    'scraping_sessions': build_url('scraping-sessions/'),
                    'description': 'System monitoring and performance metrics'
                },
                'raw_data': {
                    'raw_jobs': build_url('raw-jobs/'),
                    'description': 'Access to raw scraped data for debugging'
                }
            },
            'usage_examples': {
                'search_python_jobs': build_url('jobs/?search=python'),
                'google_jobs': build_url('jobs/?company=Google'),
                'recent_jobs': build_url('jobs/?days_since=7'),
                'top_companies': build_url('trends/?metric=companies&limit=5'),
                'system_status': build_url('health/')
            },
            'generated_at': timezone.now().isoformat()
        })
    
# =============================================================================
# Core Job API Views
# =============================================================================

class JobListView(generics.ListAPIView):
    """
    GET /api/jobs/
    
    List all canonical jobs with filtering and search capabilities.
    Uses lightweight JobSummarySerializer for performance.
    
    Query Parameters:
    - search: Search in title, company, or description
    - company: Filter by company name (exact match)
    - location: Filter by location (contains)
    - days_since: Only jobs seen within X days
    - ordering: Sort by 'first_seen', '-first_seen', 'company', etc.
    """
    
    serializer_class = JobSummarySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = JobFilter

    def get_queryset(self):
        """
        All query parameter filtering is now handled automatically by JobFilter.
        We only need to handle the special filtering from semantic URL paths.
        """
        is_company_in_path = 'company_name' in self.kwargs
        is_company_in_query = any(
            key in self.request.query_params for key in
            ['company_exact', 'company_contains', 'companies']
        )

        if is_company_in_path and is_company_in_query:
            raise ValidationError({
                "error": "Cannot filter by company in both the URL path and query parameters at the same time.",
                "path_filter": f"company_name='{self.kwargs['company_name']}",
                "query_filters": [f for f in ['company_exact', 'company_contains', 'companies'] if f in self.request.query_params]
            })

        queryset = Job.objects.all()

        company_name = self.kwargs.get('company_name')
        if company_name:
            queryset = queryset.filter(company__icontains=company_name)

        location_name = self.kwargs.get('location_name')
        if location_name:
            search_term = location_name.replace('-', ' ')
            queryset = queryset.filter(location__icontains=search_term)

        return queryset

    def list(self, request, *args, **kwargs):
        """
        Override to add custom response metadata.
        Shows total count and filtering info.
        """
        queryset = self.filter_queryset(self.get_queryset())

        # Get pagination info
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)

            # Add extra metadata
            response.data['meta'] = {
                'total_jobs': queryset.count(),
                'filters_applied': self._get_applied_filters(),
                'generated_at': timezone.now().isoformat()
            }
            return response
        
        # None paginated response
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'count': len(serializer.data),
            'meta': {
                'filters_applied': self._get_applied_filters(),
                'generated_at': timezone.now().isoformat()
            }
        })
    
    def _get_applied_filters(self):
        """Helper to show what filters were applied"""
        filters = {}

        # URL path parameters
        if self.kwargs.get('company_name'):
            filters['company_from_url'] = self.kwargs.get('company_name')
        if self.kwargs.get('location_name'):
            filters['location_from_url'] = self.kwargs.get('location_name').replace('-', ' ')

        # Query parameters
        params = self.request.query_params
        if params.get('search'):
            filters['search'] = params.get('search')
        if params.get('company'):
            filters['company'] = params.get('company')
        if params.get('location'):
            filters['location'] = params.get('location')
        if params.get('days_since'):
            filters['days_since'] = params.get('days_since')
        if params.get('ordering'):
            filters['ordering'] = params.get('ordering')
        
        return filters


class JobDetailView(generics.RetrieveAPIView):
    """
    GET /api/jobs/{id}/
    
    Get detailed information about a specific job.
    Uses full JobSerializer with all fields including description.
    """
    queryset = Job.objects.all()
    serializer_class = JobSerializer

    def retrieve(self, request, *args, **kwargs):
        """
        Override to add related data (mappings, raw postings)
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance)

         
        # Get related raw postings for this job
        mappings = JobMapping.objects.filter(canonical_job=instance).select_related('raw_posting')
        raw_postings = [mapping.raw_posting for mapping in mappings]
        
        response_data = serializer.data
        response_data['related_raw_postings'] = RawJobPostingSerializer(raw_postings, many=True).data
        response_data['mapping_count'] = len(mappings)
        
        return Response(response_data)
    
# =============================================================================
# Raw Data and Processing Views  
# =============================================================================

class RawJobPostingListView(generics.ListAPIView):
    """
    GET /api/raw-jobs/
    
    Access to raw scraped data. Useful for debugging and data quality analysis.
    """
    queryset = RawJobPosting.objects.all().order_by('-scraped_at')
    serializer_class = RawJobPostingSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = RawJobPostingFilter
    
    
class ScrapingSessionListView(generics.ListAPIView):
    """
    GET /api/scraping-sessions/
    
    Monitor scraping operations. Shows recent scraping runs and their performance.
    """
    
    queryset = ScrapingSession.objects.all().order_by('-started_at')
    serializer_class = ScrapingSessionSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ScrapingSessionFilter
    pagination_class = CustomPagination

class OrchestrationView(APIView):
    """
    POST /api/orchestrate/

    Starts a new scraping orchestration session in the background.
    """
    serializer_class = OrchestrationTaskSerializer

    @extend_schema(
        request=OrchestrationTaskSerializer,
        responses={202: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        """
        Trigger a new scraping session.
        """
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        # Create OrchestrationConfig
        config = OrchestrationConfig()

        # Automatically inject delays if more than one search term is passed
        if len(validated_data['searches']) > 1:
            # Override defaults with more conservative values for API calls
            config.delay_between_searches = 15 # seconds
            config.delay_between_sites = 45 # seconds
            config.max_concurrent_tasks = 3 # conservative concurrency for API

        # Create scraping tasks from the validated data
        tasks = []
        priority = 1
        for search in validated_data['searches']:
            for site in validated_data['sites']:
                task = ScrapingTask(
                    site=site,
                    search_term=search['search_term'],
                    location=search.get('location'),
                    max_jobs=validated_data['max_jobs'],
                    priority=priority
                )
                tasks.append(task)
            priority += 1
        
        # Run the orchestration in a background thread
        orchestrator = JobScrapingOrchestrator(config=config) # Pass the config
        thread = threading.Thread(target=orchestrator.run_scraping_session, args=(tasks,))
        thread.daemon = True # Allows main process to exit even if thread is running
        thread.start()

        return Response(
            {"message": f"Scraping session started for {len(tasks)} tasks in the background."},
            status=status.HTTP_202_ACCEPTED
        )

# =============================================================================
# Market Intelligence / Analytics Views
# =============================================================================
    
class TrendsView(APIView):
    """
    GET /api/trends/
    
    Market intelligence endpoint. Provides aggregated analytics about the job market.
    """
    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        """
        Return various market insights based on query parameters.
        
        Query Parameters:
        - metric: 'companies', 'locations', 'activity', 'all'
        - days: Analysis time window (default 30)
        - limit: Number of results to return (default 10)
        """

        # Parse parameters
        metric = request.query_params.get('metric', 'all')
        days = int(request.query_params.get('days', 30))
        limit = int(request.query_params.get('limit', 10))

        # Calculate date range
        cutoff_date = timezone.now() - timedelta(days=days)
    
        response_data = {
            'analysis_period': f'{days} days',
            'generated_at': timezone.now().isoformat(),
        }

        # Company statistics
        if metric in ['companies', 'all']:
            company_stats = self._get_company_statistics(cutoff_date, limit)
            response_data['top_companies'] = company_stats

        # Location statistics
        if metric in ['locations', 'all']:
            location_stats = self._get_location_statistics(cutoff_date, limit)
            response_data['top_locations'] = location_stats
        
        # Activity trends
        if metric in ['activity', 'all']:
            activity_stats = self._get_activity_statistics(cutoff_date)
            response_data['activity_trends'] = activity_stats
        
        # Overall market summary
        if metric == 'all':
            summary = self._get_market_summary(cutoff_date)
            response_data['market_summary'] = summary
        
        return Response(response_data)
    
    def _get_company_statistics(self, cutoff_date, limit):
        """Get top companies by job posting volume"""
        companies_qs = Job.objects.filter(
            first_seen__gte=cutoff_date
        ).values('company').annotate(
            job_count=Count('id'),
            latest_posting=Max('first_seen'),
            avg_duration=Avg(F('last_seen') - F('first_seen'))
        ).order_by('-job_count')[:limit]

        company_stats = []
        for company in companies_qs:
            avg_days = 0
            if company['avg_duration']:
                avg_days = company['avg_duration'].total_seconds() / (24 * 3600)

            company_stats.append({
                'company': company['company'],
                'job_count': company['job_count'],
                'latest_posting': company['latest_posting'],
                'avg_days_active': round(avg_days, 2)
            })

        return CompanyStatsSerializer(company_stats, many=True).data

    def _get_location_statistics(self, cutoff_date, limit):
        """Get top locations by job volume"""
        locations = Job.objects.filter(
            first_seen__gte=cutoff_date
        ).values('location').annotate(
            job_count=Count('id')
        ).order_by('-job_count')[:limit]

        # Enrich with top companies per location
        enriched_locations = []
        for loc in locations:
            top_companies = Job.objects.filter(
                location=loc['location'],
                first_seen__gte=cutoff_date
            ).values('company').annotate(
                count=Count('id')
            ).order_by('-count')[:3]

            enriched_locations.append({
                'location': loc['location'],
                'job_count': loc['job_count'],
                'top_companies': [c['company'] for c in top_companies]
            })

        return LocationStatsSerializer(enriched_locations, many=True).data
    
    def _get_activity_statistics(self, cutoff_date):
        """Get daily job posting activity"""
        total_jobs = Job.objects.filter(first_seen__gte=cutoff_date).count()
        days_in_period = (timezone.now() - cutoff_date).days
        avg_jobs_per_day = total_jobs / days_in_period if days_in_period > 0 else 0
        
        return {
            'total_jobs': total_jobs,
            'avg_jobs_per_day': round(avg_jobs_per_day, 2),
            'days_analyzed': days_in_period
        }
    
    def _get_market_summary(self, cutoff_date):
        """High-level market metrics"""
        # Get the newest job object
        newest_job_obj = Job.objects.filter(first_seen__gte=cutoff_date).order_by('-first_seen').first()
        
        # Serialize the object before adding it to the response
        serialized_newest_job = None
        if newest_job_obj:
            # We pass the request into the serializer's context so it can build full URLs
            serialized_newest_job = JobSummarySerializer(newest_job_obj, context={'request': self.request}).data

        return {
            'unique_companies': Job.objects.filter(first_seen__gte=cutoff_date).values('company').distinct().count(),
            'unique_locations': Job.objects.filter(first_seen__gte=cutoff_date).values('location').distinct().count(),
            'total_active_jobs': Job.objects.filter(last_seen__gte=timezone.now() - timedelta(days=7)).count(),
            'newest_job': serialized_newest_job
        }

class SkillTrendsView(APIView):
    """
    GET /api/trends/skills/
    
    Provides aggregated data on skill demand from job descriptions.
    """
    # A predefined list of skills to search for. This could be expanded or moved to a model.
    SKILL_KEYWORDS = [
        'Python', 'JavaScript', 'Java', 'C#', 'C++', 'Go', 'Rust', 'PHP', 'TypeScript', 'Communication',
        'Problem Solving', 'Presentation', 'React', 'Angular', 'Vue', 'Node.js', 'Django', 'Flask', 'Spring', '.NET', 'SpringBoot', 'FastAPI',
        'SQL', 'PostgreSQL', 'MySQL', 'MongoDB', 'Redis', 'Cassandra',
        'AWS', 'Azure', 'Google Cloud', 'GCP', 'Docker', 'Kubernetes', 'Terraform',
        'Linux', 'Git', 'CI/CD', 'Agile', 'Scrum',
        'Machine Learning', 'Data Science', 'Pandas', 'NumPy', 'TensorFlow', 'PyTorch',
        'AI', 'Big Data', 'Spark', 'Hadoop',
    ]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='days', description='Analysis time window (default 30)', type=OpenApiTypes.INT),
            OpenApiParameter(name='limit', description='Number of top skills to return (default 15)', type=OpenApiTypes.INT),
        ],
        responses=SkillStatsSerializer(many=True)
    )
    def get(self, request):
        """
        Analyzes job descriptions for skill keywords and returns top N skills.
        """
        days = int(request.query_params.get('days', 30))
        limit = int(request.query_params.get('limit', 15))
        cutoff_date = timezone.now() - timedelta(days=days)

        # Get all relevant job descriptions in one query
        descriptions = Job.objects.filter(
            last_seen__gte=cutoff_date
        ).values_list('description', flat=True)

        # Perform the counting in memory
        skill_counts = Counter()
        for desc in descriptions:
            desc_lower = desc.lower()
            for skill in self.SKILL_KEYWORDS:
                # Use word boundaries to avoid matching substrings (e.g., 'react' in 'proactive')
                if re.search(r'\b' + re.escape(skill.lower()) + r'\b', desc_lower):
                    skill_counts[skill] += 1
        
        # Get the most common skills
        top_skills = skill_counts.most_common(limit)

        # Format the data for the serializer
        serializer_data = [{'skill': skill, 'count': count} for skill, count in top_skills]
        serializer = SkillStatsSerializer(serializer_data, many=True)
        
        return Response(serializer.data)


# =============================================================================
# System Health and Monitoring
# =============================================================================

class HealthCheckView(APIView):
    """
    GET /api/health/

    System health endpoint. Shows scraping performance, processing status, etc.
    Essential for production monitoring!
    """
    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        """Return comprehensive health metrics"""

        orchestrator = JobScrapingOrchestrator()
        health_data = {}
        try:
            health_data = orchestrator.get_system_health()
        except Exception as e:
            logger.error(f"Error getting system health from orchestrator: {e}")
            health_data['orchestrator_error'] = str(e)
            health_data['overall_status'] = 'degraded'

        # --- FIX: Serialize the nested ScrapingSession object ---
        for site in health_data.get('site_health', {}):
            last_session = health_data['site_health'][site].get('last_successful')
            if last_session:
                health_data['site_health'][site]['last_successful'] = ScrapingSessionSerializer(last_session).data
        # --- END FIX ---

        # Determine overall status
        overall_status = 'healthy'
        if health_data.get('orchestrator_error') or health_data.get('failed_processing', 0) > 0:
            overall_status = 'degraded'
        else:
            for site, stats in health_data.get('site_health', {}).items():
                if stats.get('success_rate', 100) < 70: # Threshold for degraded status
                    overall_status = 'degraded'
                    break
        health_data['overall_status'] = overall_status

        # Add some additional API-specific health checks
        health_data['api_status'] = 'healthy'
        health_data['database_connection'] = self._check_database_health()
        health_data['recent_api_activity'] = self._get_recent_activity_summary()


        try:
            serializer = SystemHealthSerializer(health_data)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error serializing system health data: {e}")
            return Response({"error": "Failed to serialize health data", "details": str(e)}, status=500)

    def _check_database_health(self):
        try:
            Job.objects.count()
            return 'connected'
        except Exception as e:
            return f'error: {str(e)}'
    
    def _get_recent_activity_summary(self):
        """Summary of recent API/scraping activity"""
        last_24h = timezone.now() - timedelta(hours=24)
        
        return {
            'jobs_added_24h': Job.objects.filter(created_at__gte=last_24h).count(),
            'raw_postings_24h': RawJobPosting.objects.filter(scraped_at__gte=last_24h).count(),
            'successful_sessions_24h': ScrapingSession.objects.filter(
                started_at__gte=last_24h,
                status='completed'
            ).count()
        }

# =============================================================================
# Quick Stats Endpoint (for dashboard)
# =============================================================================

@api_view(['GET'])
def quick_stats(request):
    """
    GET /api/quick-stats/
    
    Fast endpoint for dashboard widgets. Returns key metrics without complex queries.
    """

    stats = {
        'total_jobs': Job.objects.count(),
        'jobs_this_week': Job.objects.filter(
            first_seen__gte=timezone.now() - timedelta(days=7)
        ).count(),
        'pending_processing': RawJobPosting.objects.filter(
            processing_status='pending'
        ).count(),
        'active_companies': Job.objects.values('company').distinct().count(),
        'last_successful_scrape': ScrapingSession.objects.filter(
            status='completed'
        ).order_by('-finished_at').first(),
        'generated_at': timezone.now().isoformat()
    }

    # Serialize the last successful scrape session if it exists
    if stats['last_successful_scrape']:
        stats['last_successful_scrape'] = ScrapingSessionSerializer(
            stats['last_successful_scrape']
        ).data
    
    return Response(stats)