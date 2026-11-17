"""URL routes for ColabVerse social, support, and reporting features."""

from django.urls import path

from . import views


app_name = "colabverse_social"


urlpatterns = [

    # =====================================================
    # HELP & SUPPORT
    # =====================================================

    # Display the Help & Support page.
    path(
        "support/",
        views.support_home,
        name="support_home",
    ),

    # Allow developers to create support tickets.
    path(
        "support/new/",
        views.ticket_create,
        name="ticket_create",
    ),

    # Display an individual support ticket.
    path(
        "support/tickets/<int:ticket_id>/",
        views.ticket_detail,
        name="ticket_detail",
    ),

    # =====================================================
    # CONTENT REPORTING
    # =====================================================

    # Display reports submitted by the current developer.
    path(
        "reports/",
        views.report_history,
        name="report_history",
    ),

    # Report a specific question, comment, or group.
    #
    # The developer clicks Report directly on the content.
    #
    # Django automatically passes the content type (kind)
    # and its database ID (object_id) to the reporting view.
    #
    # Developers do not manually enter an Object ID.
    path(
        "reports/<str:kind>/<int:object_id>/",
        views.report_create,
        name="report_content",
    ),

    # =====================================================
    # FIND DEVELOPERS
    # =====================================================

    # Display the searchable developer directory.
    path(
        "developers/",
        views.developer_list,
        name="developer_list",
    ),

    # Display a developer's social profile.
    path(
        "developers/<str:username>/",
        views.follow_profile,
        name="follow_profile",
    ),

    # Display a developer's followers or following list.
    path(
        "developers/<str:username>/<str:relation>/",
        views.follow_list,
        name="follow_list",
    ),

    # =====================================================
    # FOLLOW / UNFOLLOW
    # =====================================================

    # Follow or unfollow another developer.
    path(
        "follow/<int:user_id>/",
        views.follow_toggle,
        name="follow_toggle",
    ),

]