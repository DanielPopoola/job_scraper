from django.urls import path

from . import views

app_name = 'api'

urlpatterns = [
    # =============================================================================
    # Core Job Endpoints
    # =============================================================================
    
    # Job listings with filtering and search
    # GET /api/v1/jobs/
    # Query params: ?search=python&company=Google&location=Houston&days_since=7&ordering=-first_seen
    path(
        'jobs/', 
        views.JobListView.as_view(), 
        name='job-list'
    ),
    
    # Individual job details
    # GET /api/v1/jobs/123/
    path(
        'jobs/<int:pk>/', 
        views.JobDetailView.as_view(), 
        name='job-detail'
    ),
    
    # =============================================================================
    # Raw Data & Processing Endpoints
    # =============================================================================
    
    # Raw scraped job postings (for debugging/analysis)
    # GET /api/v1/raw-jobs/
    # Query params: ?status=pending&site=linkedin&days_ago=1
    path(
        'raw-jobs/', 
        views.RawJobPostingListView.as_view(), 
        name='raw-job-list'
    ),
    
    # Scraping session monitoring
    # GET /api/v1/scraping-sessions/
    # Query params: ?site=linkedin&status=completed&days=7
    path(
        'scraping-sessions/', 
        views.ScrapingSessionListView.as_view(), 
        name='scraping-session-list'
    ),
    
    # =============================================================================
    # Market Intelligence Endpoints
    # =============================================================================
    
    # Business intelligence and market trends
    # GET /api/v1/trends/
    # Query params: ?metric=companies&days=30&limit=10
    # Returns: Top companies, locations, activity trends
    path(
        'trends/', 
        views.TrendsView.as_view(), 
        name='trends'
    ),
    path(
        'trends/skills/',
        views.SkillTrendsView.as_view(),
        name='skill-trends'
    ),
    
    # =============================================================================
    # System Monitoring Endpoints
    # =============================================================================
    
    # System health check
    # GET /api/v1/health/
    # Returns: Database status, processing queues, recent activity
    path(
        'health/', 
        views.HealthCheckView.as_view(), 
        name='health-check'
    ),
    
    # Quick stats for dashboard widgets
    # GET /api/v1/quick-stats/
    # Returns: Essential metrics optimized for speed
    path(
        'quick-stats/', 
        views.quick_stats, 
        name='quick-stats'
    ),

    # =============================================================================
    # Actions & Triggers
    # =============================================================================

    # Trigger a new scraping orchestration session
    # POST /api/v1/orchestrate/
    path(
        'orchestrate/',
        views.OrchestrationView.as_view(),
        name='orchestrate'
    ),
    
    # =============================================================================
    # Alternative URL Patterns (RESTful variations)
    # =============================================================================
    
    # Alternative endpoint groupings for different use cases
    
    # Company-specific job listings
    # GET /api/v1/companies/Google/jobs/
    path(
        'companies/<str:company_name>/jobs/',
        views.JobListView.as_view(),
        name='company-jobs',
    ),
    
    # Locatdsion-specific job listings  
    # GET /api/v1/locations/New-York/jobs/
    path(
        'locations/<str:location_name>/jobs/',
        views.JobListView.as_view(), 
        name='location-jobs',
    ),
    
    # =============================================================================
    # API Documentation & Discovery
    # =============================================================================
    
    # API root endpoint (shows available endpoints)
    # GET /api/v1/
    path(
        '', 
        views.APIRootView.as_view(), 
        name='api-root'
    ),
]