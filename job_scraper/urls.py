from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView


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
        'documentation': {
            'swagger': '/api/v1/schema/swagger-ui/',
            'redoc': '/api/v1/schema/redoc/'
        }
    })

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include(('api.urls', 'api'), namespace='api')),
    path('', api_info, name='root'),
    path('api/', RedirectView.as_view(url='/api/v1/', permanent=False)),
    path('api-auth/', include('rest_framework.urls')),
]

urlpatterns += [
    # Schema
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    # Swagger UI
    path("api/v1/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # ReDoc
    path("api/v1/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
