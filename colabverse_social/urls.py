from django.urls import path
from . import views

app_name = "colabverse_social"

urlpatterns = [
    path("support/", views.support_home, name="support_home"),
    path("support/new/", views.ticket_create, name="ticket_create"),
    path("support/tickets/<int:ticket_id>/", views.ticket_detail, name="ticket_detail"),
    path("reports/", views.report_history, name="report_history"),
    path("reports/new/", views.report_create, name="report_create"),
    path("developers/", views.developer_list, name="developer_list"),
    path("developers/<str:username>/", views.follow_profile, name="follow_profile"),
    path("developers/<str:username>/<str:relation>/", views.follow_list, name="follow_list"),
    path("follow/<int:user_id>/", views.follow_toggle, name="follow_toggle"),
]
