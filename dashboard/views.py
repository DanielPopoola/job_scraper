import requests
from django.shortcuts import render
from django.urls import reverse
from django.contrib import messages


def call_dashboard_api(request, endpoint_name, params=None):
    """
    Helper function to call our own APIs from dashboard views.
    Handles errors gracefully and returns None if API fails.
    """
    try:
        api_url = request.build_absolute_uri(reverse(f'api:{endpoint_name}'))
        if params:
            response = requests.get(api_url, params=params)
        else:
            response = requests.get(api_url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        messages.error(request, f'Unable to load {endpoint_name} data: {str(e)}')
        return None 


def _get_site_status(site_data):
    if not site_data:
        return 'unknown'
    if site_data.get('success_rate', 0) < 70 or not site_data.get('last_successful'):
        return 'degraded'
    return 'healthy'

def dashboard_view(request):
    context = {}

    # Fetch data from various API endpoints
    quick_stats_data = call_dashboard_api(request, 'quick-stats')
    trends_data = call_dashboard_api(request, 'trends', params={'metric': 'all', 'days': 30, 'limit': 5})
    health_data = call_dashboard_api(request, 'health-check')
    skill_trends_data = call_dashboard_api(request, 'skill-trends', params={'days': 30, 'limit': 10})
    scraping_sessions_data = call_dashboard_api(request, 'scraping-session-list', params={'limit': 5, 'ordering': '-started_at'})

    if quick_stats_data:
        context['total_jobs'] = quick_stats_data.get('total_jobs', 0)
        context['companies_tracked'] = quick_stats_data.get('active_companies', 0)
        context['locations_monitored'] = trends_data.get('market_summary', {}).get('unique_locations', 0)
        context['avg_posting_duration'] = "N/A" # Placeholder for now

    if trends_data:
        context['top_companies'] = trends_data.get('top_companies', [])
        context['top_locations'] = trends_data.get('top_locations', [])
        context['activity_trends'] = trends_data.get('activity_trends', {})
        context['market_summary'] = trends_data.get('market_summary', {})

    if skill_trends_data:
        context['top_skills'] = skill_trends_data

    if scraping_sessions_data:
        context['recent_scraping_sessions'] = scraping_sessions_data.get('results', [])

    if health_data:
        context['system_health'] = health_data
        context['overall_status'] = health_data.get('overall_status', 'unknown')
        
        linkedin_site_health = health_data.get('site_health', {}).get('linkedin', {})
        context['linkedin_scraper_status'] = _get_site_status(linkedin_site_health)
        
        indeed_site_health = health_data.get('site_health', {}).get('indeed', {})
        context['indeed_scraper_status'] = _get_site_status(indeed_site_health)

        context['database_status'] = health_data.get('database_connection', 'unknown')
        context['api_status'] = health_data.get('api_status', 'unknown')

    return render(request, 'dashboard/index.html', context)


def job_explorer_view(request):
    """
    Job search and browsing interface.
    Handles search queries and filtering from user input.
    """
    # Get search parameters from user
    search_query = request.GET.get('search', '')
    company_filter = request.GET.get('company', '')
    days_filter = request.GET.get('days', '')
    page = request.GET.get('page', '1')
    
    # Build parameters for jobs API
    api_params = {}
    if search_query:
        api_params['search'] = search_query
    if company_filter:
        api_params['company_exact'] = company_filter
    if days_filter:
        api_params['posted_within_days'] = days_filter
    api_params['page'] = page
    api_params['ordering'] = '-first_seen'
    
    # Get job data
    jobs_data = call_dashboard_api(request, 'job-list', api_params)
    
    # Get company list for filter dropdown
    trends_data = call_dashboard_api(request, 'trends', {'metric': 'companies', 'limit': 20})
    
    context = {
        'jobs': jobs_data,
        'trends': trends_data,
        'search_query': search_query,
        'company_filter': company_filter,
        'days_filter': days_filter,
        'page_title': 'Job Explorer'
    }
    
    return render(request, 'dashboard/jobs.html', context)

def system_monitor_view(request):
    """
    System health and performance monitoring.
    Combines data from multiple monitoring endpoints.
    """
    # Get comprehensive system data
    health_data = call_dashboard_api(request, 'health-check')
    stats_data = call_dashboard_api(request, 'quick-stats')
    sessions_data = call_dashboard_api(request, 'scraping-session-list', {'within_days': 7})
    
    context = {
        'health': health_data,
        'stats': stats_data, 
        'recent_sessions': sessions_data,
        'page_title': 'System Monitor'
    }
    
    return render(request, 'dashboard/system.html', context)

def market_insights_view(request):
    """
    Deep market intelligence with trend comparisons.
    Shows multiple time periods for trend analysis.
    """
    # Get trends for different time periods
    trends_30d = call_dashboard_api(request, 'trends', {'days': 30, 'limit': 10})
    trends_7d = call_dashboard_api(request, 'trends', {'days': 7, 'limit': 10})
    trends_90d = call_dashboard_api(request, 'trends', {'days': 90, 'limit': 10})
    
    context = {
        'trends_monthly': trends_30d,
        'trends_weekly': trends_7d, 
        'trends_quarterly': trends_90d,
        'page_title': 'Market Intelligence'
    }
    
    return render(request, 'dashboard/insights.html', context)

def data_quality_view(request):
    """
    Data processing and quality monitoring.
    Shows raw data processing status and errors.
    """
    # Get raw data processing info
    pending_jobs = call_dashboard_api(request, 'raw-job-list', {'status': 'pending'})
    failed_jobs = call_dashboard_api(request, 'raw-job-list', {'status': 'failed', 'limit': 10})
    recent_sessions = call_dashboard_api(request, 'scraping-session-list', {'within_days': 3})
    
    context = {
        'pending_jobs': pending_jobs,
        'failed_jobs': failed_jobs,
        'recent_sessions': recent_sessions,
        'page_title': 'Data Quality Monitor'
    }
    
    return render(request, 'dashboard/quality.html', context)