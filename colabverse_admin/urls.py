from django.urls import path
from . import views

app_name = 'colabverse_admin'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('users/', views.users, name='users'),
    path('users/<int:user_id>/toggle-active/', views.toggle_user_active, name='toggle_user_active'),
    path('groups/', views.groups, name='groups'),
    path('questions/', views.questions, name='questions'),
    path('answers/', views.answers, name='answers'),
    path('content/<str:kind>/<int:object_id>/delete/', views.delete_content, name='delete_content'),
    path('meetings/', views.meetings, name='meetings'),
    path('reports/', views.reports, name='reports'),
    path('reports/<int:report_id>/status/', views.report_status, name='report_status'),
    path('support/', views.support, name='support'),
    path('support/<int:ticket_id>/update/', views.support_update, name='support_update'),
    path('security/', views.security, name='security'),
    path('health/', views.health, name='health'),
    path('health/status/', views.health_status, name='health_status'),
]
