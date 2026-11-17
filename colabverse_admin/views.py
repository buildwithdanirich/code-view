"""Views for the ColabVerse administration dashboard."""

from django.apps import apps
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import (
    AdminAuditLog,
    ContentReport,
    SupportTicket,
)

from .services import (
    get_counts,
    health_report,
)


# ---------------------------------------------------------
# ADMIN AUTHENTICATION AND PERMISSIONS
# ---------------------------------------------------------

def is_admin(user):
    """
    Check whether a user can access the admin dashboard.

    Only authenticated, active staff members are allowed.
    """
    return (
        user.is_authenticated
        and user.is_active
        and user.is_staff
    )


# Protect administration views.
admin_required = user_passes_test(
    is_admin,
    login_url="/login/",
)


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def model_for(label):
    """
    Retrieve a Django model using its application label.

    Return None when the model is unavailable.
    """
    try:
        return apps.get_model(label)

    except LookupError:
        return None


def page_for(request, queryset):
    """
    Paginate database records.

    Display 20 records per page to avoid loading
    large amounts of data into the dashboard.
    """
    paginator = Paginator(
        queryset,
        20,
    )

    return paginator.get_page(
        request.GET.get("page")
    )


def log_action(request, action, target):
    """
    Record an administrative action.

    This allows administrators to review important
    changes made through the dashboard.
    """
    AdminAuditLog.objects.create(
        actor=request.user,
        action=action,
        target=str(target)[:180],
    )


# ---------------------------------------------------------
# DASHBOARD OVERVIEW
# ---------------------------------------------------------

@never_cache
@admin_required
def dashboard(request):
    """
    Display ColabVerse platform statistics.

    Includes:
        - Total users
        - Active users
        - Communities and groups
        - Memberships
        - Open reports
        - Unresolved support tickets
        - Recent administrative activity

    Questions, answers, and meetings are not
    displayed in the administration dashboard.
    """

    # Retrieve existing platform statistics.
    counts = get_counts(
        get_user_model()
    )

    # Remove unwanted statistics from the dashboard.
    # This also protects against future changes to get_counts().
    for key in (
        "questions",
        "comments",
        "answers",
        "meetings",
    ):
        counts.pop(key, None)

    # Count reports awaiting review.
    counts["reports"] = ContentReport.objects.filter(
        status="open"
    ).count()

    # Count support tickets that are not resolved.
    counts["support"] = SupportTicket.objects.exclude(
        status="resolved"
    ).count()

    # Retrieve the eight most recent administrative actions.
    recent_audit = (
        AdminAuditLog.objects
        .select_related("actor")
        .order_by("-created_at")[:8]
    )

    context = {
        "counts": counts,
        "recent_audit": recent_audit,
    }

    return render(
        request,
        "colabverse_admin/dashboard.html",
        context,
    )


# ---------------------------------------------------------
# USER MANAGEMENT
# ---------------------------------------------------------

@never_cache
@admin_required
def users(request):
    """
    Display registered ColabVerse users.

    Administrators can search users by:
        - Username
        - Email
        - First name
        - Last name
    """

    model = get_user_model()

    # Retrieve users, newest first.
    queryset = (
        model._default_manager
        .all()
        .order_by("-pk")
    )

    # Read and limit the search term.
    term = request.GET.get(
        "q",
        "",
    ).strip()[:100]

    if term:

        search = Q()

        searchable_fields = (
            model.USERNAME_FIELD,
            "email",
            "first_name",
            "last_name",
        )

        available_fields = {
            field.name
            for field in model._meta.fields
        }

        for field in searchable_fields:

            if field in available_fields:

                search |= Q(
                    **{
                        f"{field}__icontains": term
                    }
                )

        queryset = queryset.filter(
            search
        )

    context = {
        "page": page_for(
            request,
            queryset,
        ),
        "term": term,
    }

    return render(
        request,
        "colabverse_admin/users.html",
        context,
    )


@require_POST
@admin_required
def toggle_user_active(request, user_id):
    """
    Activate or deactivate a user account.

    Only superusers can perform this action.

    Administrators cannot:
        - Deactivate themselves
        - Change another superuser's account status
    """

    if not request.user.is_superuser:

        return HttpResponseForbidden(
            "Only superusers can change account status."
        )

    target = get_object_or_404(
        get_user_model(),
        pk=user_id,
    )

    # Protect administrator accounts.
    if (
        target.pk == request.user.pk
        or target.is_superuser
    ):

        messages.error(
            request,
            "You cannot change your own account "
            "or another superuser.",
        )

    else:

        # Toggle account status.
        target.is_active = not target.is_active

        target.save(
            update_fields=["is_active"]
        )

        # Record the administrative action.
        log_action(
            request,
            "user.toggle_active",
            target.pk,
        )

        messages.success(
            request,
            "Account status updated.",
        )

    return redirect(
        "colabverse_admin:users"
    )


# ---------------------------------------------------------
# COMMUNITY AND GROUP MANAGEMENT
# ---------------------------------------------------------

@never_cache
@admin_required
def groups(request):
    """
    Display ColabVerse communities and development groups.

    The existing community.ProjectGroup model is used.

    This view does not modify group memberships,
    invitations, or group permissions.
    """

    model = model_for(
        "community.ProjectGroup"
    )

    # Handle projects without the expected group model.
    if model is None:

        return render(
            request,
            "colabverse_admin/records.html",
            {
                "heading": "Communities & groups",
                "unavailable": True,
            },
        )

    queryset = (
        model.objects
        .all()
        .order_by("-pk")
    )

    # Optional group-name search.
    term = request.GET.get(
        "q",
        "",
    ).strip()[:100]

    if term:

        queryset = queryset.filter(
            name__icontains=term
        )

    context = {
        "page": page_for(
            request,
            queryset,
        ),
        "term": term,
    }

    return render(
        request,
        "colabverse_admin/groups.html",
        context,
    )


# ---------------------------------------------------------
# CONTENT REPORTS
# ---------------------------------------------------------

@never_cache
@admin_required
def reports(request):
    """
    Display user-submitted content reports.

    Reports help administrators investigate
    inappropriate content or user behavior.
    """

    queryset = (
        ContentReport.objects
        .select_related("reporter")
        .order_by("-created_at")
    )

    context = {
        "page": page_for(
            request,
            queryset,
        ),
    }

    return render(
        request,
        "colabverse_admin/reports.html",
        context,
    )


@require_POST
@admin_required
def report_status(request, report_id):
    """
    Update the status of a content report.

    Only superusers can perform this action.
    """

    if not request.user.is_superuser:

        return HttpResponseForbidden(
            "Only superusers can resolve reports."
        )

    report = get_object_or_404(
        ContentReport,
        pk=report_id,
    )

    status = request.POST.get(
        "status"
    )

    # Validate the requested status.
    if status not in dict(
        ContentReport.STATUS_CHOICES
    ):

        return HttpResponseForbidden(
            "Invalid status"
        )

    # Update report status.
    report.status = status

    report.reviewed_at = timezone.now()

    report.save(
        update_fields=[
            "status",
            "reviewed_at",
        ]
    )

    # Record the administrative action.
    log_action(
        request,
        "report.status",
        f"{report.pk}:{status}",
    )

    messages.success(
        request,
        "Report status updated.",
    )

    return redirect(
        "colabverse_admin:reports"
    )


# ---------------------------------------------------------
# HELP AND SUPPORT
# ---------------------------------------------------------

@never_cache
@admin_required
def support(request):
    """
    Display user support tickets.

    Administrators can review issues submitted
    by ColabVerse users.
    """

    queryset = (
        SupportTicket.objects
        .select_related("requester")
        .order_by("-created_at")
    )

    context = {
        "page": page_for(
            request,
            queryset,
        ),
    }

    return render(
        request,
        "colabverse_admin/support.html",
        context,
    )


@require_POST
@admin_required
def support_update(request, ticket_id):
    """
    Update a support ticket.

    Superusers can:
        - Change ticket status
        - Write an administrative response
    """

    if not request.user.is_superuser:

        return HttpResponseForbidden(
            "Only superusers can update tickets."
        )

    ticket = get_object_or_404(
        SupportTicket,
        pk=ticket_id,
    )

    status = request.POST.get(
        "status"
    )

    # Validate ticket status.
    if status not in dict(
        SupportTicket.STATUS_CHOICES
    ):

        return HttpResponseForbidden(
            "Invalid status"
        )

    # Update the ticket.
    ticket.status = status

    ticket.admin_reply = request.POST.get(
        "admin_reply",
        "",
    )[:10000]

    ticket.save(
        update_fields=[
            "status",
            "admin_reply",
            "updated_at",
        ]
    )

    # Record the administrative action.
    log_action(
        request,
        "support.update",
        ticket.pk,
    )

    messages.success(
        request,
        "Ticket updated.",
    )

    return redirect(
        "colabverse_admin:support"
    )


# ---------------------------------------------------------
# SECURITY AND AUDIT LOGS
# ---------------------------------------------------------

@never_cache
@admin_required
def security(request):
    """
    Display administrative activity logs.

    The audit log helps administrators investigate
    account changes, report reviews, and support updates.
    """

    queryset = (
        AdminAuditLog.objects
        .select_related("actor")
        .all()
        .order_by("-created_at")
    )

    context = {
        "page": page_for(
            request,
            queryset,
        ),
    }

    return render(
        request,
        "colabverse_admin/security.html",
        context,
    )


# ---------------------------------------------------------
# PROJECT HEALTH MONITORING
# ---------------------------------------------------------

@never_cache
@admin_required
def health(request):
    """
    Display the ColabVerse project health dashboard.

    Health information is collected through
    the existing health_report() service.
    """

    context = {
        "report": health_report(),
    }

    return render(
        request,
        "colabverse_admin/health.html",
        context,
    )


@never_cache
@admin_required
def health_status(request):
    """
    Return project health information as JSON.

    This endpoint is protected by admin authentication.

    It is intended for the administration dashboard,
    not as a public health-check endpoint.
    """

    return JsonResponse(
        health_report(),
        headers={
            "Cache-Control": "no-store",
        },
    )