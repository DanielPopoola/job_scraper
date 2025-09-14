from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('jobs/', views.job_explorer_view, name='job-explorer'),
    path('system/', views.system_monitor_view, name='system-monitor'),
    path('insights/', views.market_insights_view, name='market-insights'),
    path('quality/', views.data_quality_view, name='data-quality'),
    path('orchestrate/', views.orchestration_view, name='orchestrate'),
]