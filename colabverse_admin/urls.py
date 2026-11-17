"""URL routes for the ColabVerse administration dashboard."""

from django.urls import path

from . import views


app_name = "colabverse_admin"


urlpatterns = [
    # Main administration dashboard.
    path(
        "",
        views.dashboard,
        name="dashboard",
    ),

    # User management.
    path(
        "users/",
        views.users,
        name="users",
    ),

    # Activate or deactivate user accounts.
    path(
        "users/<int:user_id>/toggle-active/",
        views.toggle_user_active,
        name="toggle_user_active",
    ),

    # Community and private development group management.
    path(
        "groups/",
        views.groups,
        name="groups",
    ),

    # User-submitted reports.
    path(
        "reports/",
        views.reports,
        name="reports",
    ),

    # Update the status of a report.
    path(
        "reports/<int:report_id>/status/",
        views.report_status,
        name="report_status",
    ),

    # Help and support tickets.
    path(
        "support/",
        views.support,
        name="support",
    ),

    # Update support tickets.
    path(
        "support/<int:ticket_id>/update/",
        views.support_update,
        name="support_update",
    ),

    # Security monitoring.
    path(
        "security/",
        views.security,
        name="security",
    ),

    # Project health monitoring.
    path(
        "health/",
        views.health,
        name="health",
    ),

    # Health status endpoint.
    path(
        "health/status/",
        views.health_status,
        name="health_status",
    ),
]