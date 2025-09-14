from urllib.parse import urlparse

import requests
from django.contrib import messages
from django.shortcuts import render
from django.urls import reverse


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
    Handles search queries and filtering from user input by calling the API.
    """
    # Get all filter parameters from the request
    page = request.GET.get('page', '1')
    api_params = request.GET.copy()
    api_params['page'] = page

    # Fetch job data from the API
    jobs_data = call_dashboard_api(request, 'job-list', api_params)

    # Prepare pagination URLs and info
    if jobs_data:
        jobs_data['number'] = int(page)
        page_size = 20
        jobs_data['num_pages'] = (jobs_data.get('count', 0) + page_size - 1) // page_size
        if jobs_data.get('next'):
            jobs_data['next_page_query'] = urlparse(jobs_data['next']).query
        if jobs_data.get('previous'):
            jobs_data['previous_page_query'] = urlparse(jobs_data['previous']).query

    # Fetch data for filter dropdowns
    companies_data = call_dashboard_api(request, 'trends', {'metric': 'companies', 'limit': 50})
    locations_data = call_dashboard_api(request, 'trends', {'metric': 'locations', 'limit': 50})

    context = {
        'jobs': jobs_data,
        'available_companies': companies_data.get('top_companies', []) if companies_data else [],
        'available_locations': locations_data.get('top_locations', []) if locations_data else [],
        'search_query': request.GET.get('search', ''),
        'company_filter': request.GET.get('company', ''),
        'location_filter': request.GET.get('location', ''),
        'days_filter': request.GET.get('posted_within_days', ''),
        'status_filter': request.GET.get('status', ''),
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

def orchestration_view(request):
    """
    Renders the page for triggering and monitoring scraping orchestration.
    """
    context = {
        'page_title': 'Scraping Orchestrator'
    }
    return render(request, 'dashboard/orchestrate.html', context)