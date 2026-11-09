"""Main URL configuration for CodeView."""

# Access Django project settings.
from django.conf import settings

from community import github_oauth

# Helper for serving uploaded files during development.
from django.conf.urls.static import static

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from home.views import home


# Django looks for this exact variable name: urlpatterns.
urlpatterns = [

    # Django admin panel.
    path("admin/", admin.site.urls),

    # Homepage.
    path("", home, name="home"),

    # Registration and login.
    path("", include("users.urls")),

    # Project Groups.
    path("groups/", include("community.urls")),

    # Redirect old Community URLs to Groups.
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

    # Start GitHub authorization for a private development group.
    path(
        "github/authorize/<int:group_id>/",
        github_oauth.start_github_authorization,
        name="start_github_authorization",
    ),

    # GitHub redirects developers here after authorization.
    path(
        "github/callback/",
        github_oauth.github_oauth_callback,
        name="github_oauth_callback",
    ),

]


# ========================================
# SERVE UPLOADED FILES DURING DEVELOPMENT
# ========================================

# Only serve uploaded files this way in development.
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )