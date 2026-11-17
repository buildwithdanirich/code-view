"""Authenticated user-facing support, reporting, and follow endpoints."""

from django.apps import apps
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from community.permissions import can_view_group
from colabverse_admin.models import ContentReport, SupportTicket

from .forms import ReportForm, TicketForm
from .models import Follow


# =========================================================
# HELP & SUPPORT
# =========================================================

@login_required
def support_home(request):
    """Display support tickets belonging to the current developer."""

    tickets = SupportTicket.objects.filter(
        requester=request.user
    ).order_by("-created_at", "-pk")

    return render(
        request,
        "colabverse_social/support_home.html",
        {
            "page": Paginator(tickets, 20).get_page(
                request.GET.get("page")
            ),
        },
    )


@login_required
def ticket_create(request):
    """Allow a developer to submit a support ticket."""

    form = TicketForm(request.POST or None)

    if request.method == "POST" and form.is_valid():

        ticket = form.save(commit=False)

        ticket.requester = request.user

        # Developers cannot assign themselves high priority.
        ticket.priority = "normal"

        ticket.save()

        messages.success(
            request,
            "Your support request was submitted.",
        )

        return redirect(
            "colabverse_social:ticket_detail",
            ticket_id=ticket.pk,
        )

    return render(
        request,
        "colabverse_social/ticket_form.html",
        {
            "form": form,
        },
    )


@login_required
def ticket_detail(request, ticket_id):
    """Display a support ticket owned by the current developer."""

    ticket = get_object_or_404(
        SupportTicket,
        pk=ticket_id,
        requester=request.user,
    )

    return render(
        request,
        "colabverse_social/ticket_detail.html",
        {
            "ticket": ticket,
        },
    )


# =========================================================
# CONTENT REPORTING
# =========================================================

# Supported content types and their Django models.
REPORT_TARGETS = {
    "question": "questions.Question",
    "comment": "questions.Comment",
    "group": "community.ProjectGroup",
}


def valid_report_target(kind, object_id):
    """
    Check whether a reporting target exists.

    This helper only checks existence.

    Permission checks are handled separately before
    displaying the reporting form or accepting a report.
    """

    label = REPORT_TARGETS.get(kind)

    if label is None:
        return False

    try:
        model = apps.get_model(label)

    except LookupError:
        return False

    return model._default_manager.filter(
        pk=object_id
    ).exists()


def get_report_target(kind, object_id, user):
    """
    Find the content being reported and verify access.

    Questions:
        The question must exist.

    Comments:
        The comment and its parent question must exist.

    Groups:
        The developer must be allowed to view the group.

    Return the target object if accessible.

    Raise Http404 if the content is unavailable or
    the developer does not have permission to view it.
    """

    label = REPORT_TARGETS.get(kind)

    # Reject unsupported reporting categories.
    if label is None:
        raise Http404("Unsupported report type.")

    try:
        model = apps.get_model(label)

    except LookupError:
        raise Http404("Reporting target is unavailable.")

    # Find the selected content.
    target = get_object_or_404(
        model._default_manager,
        pk=object_id,
    )

    # -----------------------------------------------------
    # GROUP ACCESS CHECK
    # -----------------------------------------------------

    if kind == "group":

        # Reuse the existing group permission system.
        if not can_view_group(target, user):
            raise Http404("Group is unavailable.")

    # -----------------------------------------------------
    # COMMENT ACCESS CHECK
    # -----------------------------------------------------

    elif kind == "comment":

        # Comments must belong to an existing question.
        # The ForeignKey relationship identifies that question.
        if not target.question_id:
            raise Http404("Comment is unavailable.")

        question_model = apps.get_model("questions", "Question")

        if not question_model._default_manager.filter(
            pk=target.question_id
        ).exists():
            raise Http404("Question is unavailable.")

    return target


@login_required
def report_create(request, kind=None, object_id=None):
    """
    Allow developers to report specific content.

    The content type and object ID come from the URL,
    not from fields entered in the reporting form.

    Example:
        /reports/question/15/

    The developer only provides a reporting reason.

    The backend:
        1. Validates the reporting target.
        2. Checks access permissions.
        3. Validates the reason.
        4. Prevents repeated pending reports.
        5. Saves the report for admin review.
    """

    # -----------------------------------------------------
    # LEGACY REPORT URL
    # -----------------------------------------------------

    # The old /reports/new/ URL does not identify content.
    # Redirect it to report history instead of accepting
    # a manually entered content ID.
    if kind is None or object_id is None:

        if request.method == "POST":
            return HttpResponseBadRequest(
                "Select Report directly from the content."
            )

        messages.info(
            request,
            "To report content, open the question, comment, "
            "or group and select Report.",
        )

        return redirect(
            "colabverse_social:report_history"
        )

    # -----------------------------------------------------
    # VALIDATE CONTENT AND PERMISSIONS
    # -----------------------------------------------------

    # This check runs for GET and POST requests.
    # Users cannot bypass it by submitting a form directly.
    target = get_report_target(
        kind=kind,
        object_id=object_id,
        user=request.user,
    )

    # -----------------------------------------------------
    # CREATE REPORT FORM
    # -----------------------------------------------------

    form = ReportForm(
        request.POST or None
    )

    # -----------------------------------------------------
    # HANDLE REPORT SUBMISSION
    # -----------------------------------------------------

    if request.method == "POST" and form.is_valid():

        # The developer only supplies the reason.
        reason = form.cleaned_data["reason"].strip()

        # Check for an existing pending report.
        existing_report = ContentReport.objects.filter(
            reporter=request.user,
            kind=kind,
            object_id=target.pk,
            status__in=("open", "reviewing"),
        ).exists()

        if existing_report:

            messages.info(
                request,
                "You already have a pending report for this item.",
            )

        else:

            # Store the report using the verified target.
            ContentReport.objects.create(
                reporter=request.user,
                kind=kind,
                object_id=target.pk,
                reason=reason,
            )

            messages.success(
                request,
                "Your report was submitted for review.",
            )

        return redirect(
            "colabverse_social:report_history"
        )

    # -----------------------------------------------------
    # DISPLAY REPORT FORM
    # -----------------------------------------------------

    return render(
        request,
        "colabverse_social/report_form.html",
        {
            "form": form,
            "report_kind": kind,
            "report_target": target,
        },
    )


@login_required
def report_history(request):
    """Display reports submitted by the current developer."""

    reports = ContentReport.objects.filter(
        reporter=request.user
    ).order_by("-created_at", "-pk")

    return render(
        request,
        "colabverse_social/report_history.html",
        {
            "page": Paginator(reports, 20).get_page(
                request.GET.get("page")
            ),
        },
    )


# =========================================================
# FIND DEVELOPERS
# =========================================================

@login_required
def developer_list(request):
    """
    Search active ColabVerse developers by username or name.

    Also identify developers already followed by the current user.
    """

    User = get_user_model()

    # Read and limit the search term.
    term = request.GET.get("q", "").strip()[:80]

    # Exclude the currently logged-in developer.
    users = (
        User._default_manager
        .filter(is_active=True)
        .exclude(pk=request.user.pk)
    )

    if term:

        # Search usernames, first names, and last names.
        search_query = (
            Q(**{f"{User.USERNAME_FIELD}__icontains": term})
            | Q(first_name__icontains=term)
            | Q(last_name__icontains=term)
        )

        # Support full-name searches such as "Daniel Akpa".
        name_parts = term.split()

        if len(name_parts) >= 2:

            first_name = name_parts[0]
            last_name = " ".join(name_parts[1:])

            search_query |= (
                Q(first_name__icontains=first_name)
                & Q(last_name__icontains=last_name)
            )

        users = users.filter(search_query)

    # Keep results stable for pagination.
    users = users.order_by("pk")

    # Display 20 developers per page.
    page = Paginator(users, 20).get_page(
        request.GET.get("page")
    )

    # Identify which displayed developers the visitor follows.
    ids = [
        user.pk
        for user in page.object_list
    ]

    following_ids = set(
        Follow.objects.filter(
            follower=request.user,
            following_id__in=ids,
        ).values_list(
            "following_id",
            flat=True,
        )
    )

    return render(
        request,
        "colabverse_social/developers.html",
        {
            "page": page,
            "term": term,
            "following_ids": following_ids,
        },
    )


# =========================================================
# DEVELOPER SOCIAL PROFILE
# =========================================================

@login_required
def follow_profile(request, username):
    """Display a developer's follower and following counts."""

    User = get_user_model()

    target = get_object_or_404(
        User,
        **{
            User.USERNAME_FIELD: username,
            "is_active": True,
        },
    )

    followers = Follow.objects.filter(
        following=target
    ).count()

    following = Follow.objects.filter(
        follower=target
    ).count()

    is_following = Follow.objects.filter(
        follower=request.user,
        following=target,
    ).exists()

    return render(
        request,
        "colabverse_social/follow_profile.html",
        {
            "target": target,
            "followers": followers,
            "following": following,
            "is_following": is_following,
        },
    )


# =========================================================
# FOLLOW / UNFOLLOW
# =========================================================

@require_POST
@login_required
def follow_toggle(request, user_id):
    """
    Follow or unfollow a developer.

    After updating the relationship, return the developer
    to the page where they clicked the button.
    """

    User = get_user_model()

    # Find the developer being followed or unfollowed.
    target = get_object_or_404(
        User,
        pk=user_id,
        is_active=True,
    )

    # Developers cannot follow themselves.
    if target.pk == request.user.pk:

        return HttpResponseBadRequest(
            "You cannot follow yourself."
        )

    # Read the requested action.
    action = request.POST.get("action")

    if action == "follow":

        try:

            # Ensure duplicate follows cannot be created.
            with transaction.atomic():

                Follow.objects.get_or_create(
                    follower=request.user,
                    following=target,
                )

        except IntegrityError:

            # A concurrent request may have already created
            # the relationship.
            pass

    elif action == "unfollow":

        # Remove the relationship if it exists.
        Follow.objects.filter(
            follower=request.user,
            following=target,
        ).delete()

    else:

        return HttpResponseBadRequest(
            "Invalid action."
        )

    # Read the return URL submitted by the form.
    return_to = request.POST.get("next", "")

    # Redirect only to URLs belonging to this website.
    if return_to and url_has_allowed_host_and_scheme(
        url=return_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):

        return redirect(return_to)

    # Default: return to the developer's main profile.
    return redirect(
        "public_profile",
        username=getattr(
            target,
            User.USERNAME_FIELD,
        ),
    )


# =========================================================
# FOLLOWERS / FOLLOWING LIST
# =========================================================

@login_required
def follow_list(request, username, relation):
    """
    Display the followers or following list for a developer.

    Also identify which developers the logged-in user
    already follows so the correct button can be displayed.
    """

    User = get_user_model()

    # Find the developer whose followers/following we want to view.
    target = get_object_or_404(
        User,
        **{
            User.USERNAME_FIELD: username,
            "is_active": True,
        },
    )

    # Get the appropriate relationship records.
    if relation == "followers":

        # Developers following the target.
        qs = Follow.objects.filter(
            following=target,
        ).select_related(
            "follower",
            "follower__developer_profile",
        )

    elif relation == "following":

        # Developers the target follows.
        qs = Follow.objects.filter(
            follower=target,
        ).select_related(
            "following",
            "following__developer_profile",
        )

    else:

        raise Http404(
            "Unknown relationship"
        )

    # Paginate the relationships.
    page = Paginator(qs, 20).get_page(
        request.GET.get("page")
    )

    # Collect user IDs from the current page.
    if relation == "followers":

        developer_ids = [
            item.follower_id
            for item in page.object_list
        ]

    else:

        developer_ids = [
            item.following_id
            for item in page.object_list
        ]

    # Find which displayed developers the visitor follows.
    following_ids = set(
        Follow.objects.filter(
            follower=request.user,
            following_id__in=developer_ids,
        ).values_list(
            "following_id",
            flat=True,
        )
    )

    return render(
        request,
        "colabverse_social/follow_list.html",
        {
            "target": target,
            "relation": relation,
            "page": page,
            "following_ids": following_ids,
        },
    )