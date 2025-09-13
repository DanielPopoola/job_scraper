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
    scraping_sessions_data = call_dashboard_api(request, 'scraping-sessions', params={'limit': 5, 'ordering': '-started_at'})

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
        context['system_uptime'] = health_data.get('system_uptime', 'N/A') # Still N/A as not provided by API

    return render(request, 'dashboard/index.html', context)