from django.urls import path
from . import views
app_name = 'questions'
urlpatterns = [
    path('', views.feed, name='feed'),
    path('ask/', views.create, name='create'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/read/', views.read_notifications, name='read_notifications'),
    path('<int:pk>/', views.detail, name='detail'),
    path('<int:pk>/edit/', views.edit, name='edit'),
    path('<int:pk>/delete/', views.delete, name='delete'),
    path('<int:pk>/like/', views.toggle_question_like, name='like'),
    path('<int:pk>/comment/', views.comment, name='comment'),
    path('comments/<int:pk>/like/', views.toggle_comment_like, name='comment_like'),
    path('comments/<int:pk>/accept/', views.accept, name='accept'),
    path('comments/<int:pk>/delete/', views.delete_comment, name='delete_comment'),
]
