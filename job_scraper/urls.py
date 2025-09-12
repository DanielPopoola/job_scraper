"""
URL configuration for job_scraper project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.views.generic import RedirectView

def api_info(request):
    """
    Simple endpoint that provides API information at the root level.
    Useful for API discovery and health checks.
    """
    return JsonResponse({
        'service': 'Job Market Intelligence API',
        'version': 'v1.0',
        'status': 'operational',
        'api_endpoints': {
            'api_root': '/api/v1/',
            'jobs': '/api/v1/jobs/',
            'trends': '/api/v1/trends/',
            'health': '/api/v1/health/',
            'admin': '/admin/',
            'dashboard': '/dashboard/'
        },
        'documentation': 'Visit /api/v1/ for detailed endpoint information'
    })

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('api.urls')),
    path('', api_info, name='root'),
    path('api/', RedirectView.as_view(url='/api/v1/', permanent=False)),
    path('api-auth/', include('rest_framework.urls')),
]
