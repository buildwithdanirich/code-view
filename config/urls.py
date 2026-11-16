"""Main URL configuration for ColabVerse."""

# Access Django project settings.
from django.conf import settings

from django.contrib.auth.decorators import login_required

# Serve uploaded media files during development.
from django.conf.urls.static import static

# Django admin panel.
from django.contrib import admin

# URL routing utilities.
from django.urls import include, path

from home import views as home_views
# Redirect users to existing named routes.
from django.views.generic import RedirectView

# Existing GitHub authorization functionality.
from community import github_oauth


# Django reads this list to determine which view handles each URL.
urlpatterns = [

    # ============================================================
    # DJANGO ADMIN
    # ============================================================
path("admin/", include("colabverse_admin.urls")),
# ============================================================
# COLABVERSE HOMEPAGE
# ============================================================

# Public landing page for visitors.
# Logged-in developers are redirected to the questions feed.
path(
    "",
    home_views.home,
    name="home",
),

    # ============================================================
    # USER AUTHENTICATION
    # ============================================================

    # Preserve existing registration, login, logout,
    # email verification, and password reset URLs.
    path(
        "",
        include("users.urls"),
    ),

    # ============================================================
    # PRIVATE DEVELOPMENT GROUPS
    # ============================================================

    # All private group functionality remains in Community.
    path(
        "groups/",
        include("community.urls"),
    ),

    # Preserve the existing Community redirect.
    path(
        "community/",
        RedirectView.as_view(
            pattern_name="groups",
            permanent=False,
        ),
    ),

    # ============================================================
    # GITHUB OAUTH AUTHORIZATION
    # ============================================================

    # Start GitHub authorization for a private group.
    path(
        "github/authorize/<int:group_id>/",
        github_oauth.start_github_authorization,
        name="start_github_authorization",
    ),

    # GitHub authorization callback.
    path(
        "github/callback/",
        github_oauth.github_oauth_callback,
        name="github_oauth_callback",
    ),

    # ============================================================
    # THIRD-PARTY ACCOUNT AUTHENTICATION
    # ============================================================

    path(
        "accounts/",
        include("allauth.urls"),
    ),

    # ============================================================
    # QUESTIONS APP
    # ============================================================

    # Public questions feed, likes, comments, and notifications.
    path(
        "questions/",
        include("questions.urls"),
    ),

]


# ============================================================
# DEVELOPMENT MEDIA FILES
# ============================================================

# Django serves uploaded files directly only in development.
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )