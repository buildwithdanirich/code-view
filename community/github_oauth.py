"""
GitHub OAuth authorization for CodeView.

Responsibilities:
1. Check group repository connection permissions.
2. Validate the selected repository URL.
3. Start GitHub OAuth authorization.
4. Verify the developer's GitHub identity.
5. Verify access to the selected private repository.
6. Verify the CodeView GitHub App installation.
7. Save the repository and consume member approval atomically.

Security:
- Never store GitHub access tokens in Django sessions.
- Never trust an installation ID supplied by the browser.
- Never replace an existing repository before verification succeeds.
- Recheck membership and approval before saving.
"""

import hmac
import secrets
import time

from urllib.parse import quote, urlencode

import httpx

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import (
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import GroupRepositoryForm

from .github_auth import (
    GitHubAuthError,
    generate_github_app_jwt,
    get_installation_access_token,
    github_api_request,
)

from .models import (
    GroupMember,
    GroupRepository,
    ProjectGroup,
    RepositoryConnectionRequest,
)


# Allow five minutes to complete GitHub authorization.
OAUTH_MAX_AGE_SECONDS = 300


def get_valid_repository_approval(group, user):
    """
    Find the developer's current approved repository request.

    Old approvals are not valid after membership or ownership changes.
    """

    membership = GroupMember.objects.filter(
        group=group,
        user=user,
    ).first()

    if membership is None:
        return None

    return RepositoryConnectionRequest.objects.filter(
        group=group,
        requested_by=user,
        status="approved",
        membership_generation=membership.membership_generation,
        owner_membership_generation=group.owner_membership_generation,
    ).first()


def has_repository_connection_permission(group, user):
    """
    Determine whether a developer may connect a repository.

    Owners are allowed directly.
    Members require a current approved request.
    """

    if not group.is_private:
        return False

    if group.owner_id == user.id:
        return True

    return get_valid_repository_approval(group, user) is not None


def clear_github_oauth_session(request):
    """
    Remove unfinished OAuth information from the session.

    Never store GitHub access tokens in these values.
    """

    keys = (
        "github_oauth_state",
        "github_oauth_group_id",
        "github_oauth_owner",
        "github_oauth_repository",
        "github_oauth_owner_generation",
        "github_oauth_user_id",
        "github_oauth_membership_generation",
        "github_oauth_approval_id",
        "github_oauth_started_at",
        "github_verified_user_id",
        "github_verified_username",
        "github_verified_group_id",
        "github_verified_repository_owner",
        "github_verified_repository_name",
    )

    for key in keys:
        request.session.pop(key, None)


@login_required
@require_POST
def start_github_authorization(request, group_id):
    """
    Start GitHub OAuth for a selected repository.

    This endpoint is intended for repositories requiring authorization.

    Public repositories should use the direct connection endpoint.
    """

    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
        is_private=True,
    )

    # Check CodeView group permissions first.
    if not has_repository_connection_permission(
        group,
        request.user,
    ):
        return HttpResponseForbidden(
            "You do not have permission to connect repositories."
        )

    # Validate the repository URL using the existing form.
    form = GroupRepositoryForm(request.POST)

    if not form.is_valid():
        messages.error(
            request,
            "Enter a valid GitHub repository URL.",
        )

        return redirect(
            "meeting_room",
            group_id=group.id,
        )

    # Check GitHub OAuth configuration.
    if not (
        getattr(settings, "GITHUB_CLIENT_ID", None)
        and getattr(settings, "GITHUB_CLIENT_SECRET", None)
        and getattr(settings, "GITHUB_OAUTH_CALLBACK_URL", None)
    ):
        messages.error(
            request,
            "GitHub OAuth is not configured.",
        )

        return redirect(
            "meeting_room",
            group_id=group.id,
        )

    github_owner = form.cleaned_data["github_owner"]
    repository_name = form.cleaned_data["repository_name"]

    # Save the exact approval that authorized this attempt.
    approval = None
    membership_generation = None

    if group.owner_id != request.user.id:
        approval = get_valid_repository_approval(
            group,
            request.user,
        )

        if approval is None:
            return HttpResponseForbidden(
                "Your repository approval is no longer valid."
            )

        membership_generation = str(
            approval.membership_generation
        )

    # Remove information from previous unfinished attempts.
    clear_github_oauth_session(request)

    # Generate an unpredictable OAuth state.
    state = secrets.token_urlsafe(32)

    # Bind the authorization to this user, group and repository.
    request.session["github_oauth_state"] = state
    request.session["github_oauth_group_id"] = group.id

    request.session["github_oauth_owner"] = github_owner
    request.session["github_oauth_repository"] = repository_name

    request.session["github_oauth_user_id"] = request.user.id

    request.session["github_oauth_owner_generation"] = str(
        group.owner_membership_generation
    )

    request.session["github_oauth_membership_generation"] = (
        membership_generation
    )

    request.session["github_oauth_approval_id"] = (
        approval.id if approval else None
    )

    request.session["github_oauth_started_at"] = int(time.time())

    # Redirect the developer to GitHub.
    parameters = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_OAUTH_CALLBACK_URL,
        "state": state,
    }

    authorization_url = (
        "https://github.com/login/oauth/authorize"
    )

    return redirect(
        f"{authorization_url}?{urlencode(parameters)}"
    )


def get_github_user_access_token(authorization_code):
    """
    Exchange a GitHub authorization code for a user access token.

    The token stays on the server and is never saved in a session.
    """

    with httpx.Client(
        timeout=10.0,
        follow_redirects=False,
        trust_env=False,
    ) as client:

        response = client.post(
            "https://github.com/login/oauth/access_token",
            headers={
                "Accept": "application/json",
                "User-Agent": "CodeView",
            },
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": authorization_code,
                "redirect_uri": settings.GITHUB_OAUTH_CALLBACK_URL,
            },
        )

        response.raise_for_status()
        data = response.json()

    access_token = data.get("access_token")

    if not access_token:
        raise GitHubAuthError(
            "GitHub did not provide an access token."
        )

    return access_token


def verify_private_repository(
    github_owner,
    repository_name,
    user_access_token,
):
    """
    Verify a private repository using two identities.

    1. The developer's GitHub user token must have repository access.
    2. CodeView's GitHub App installation must access the same repository.

    Return verified repository information.
    """

    # URL components have already passed GroupRepositoryForm.
    owner = quote(github_owner, safe="")
    name = quote(repository_name, safe="")

    endpoint = f"/repos/{owner}/{name}"

    # --------------------------------------------------------
    # 1. VERIFY THE DEVELOPER'S REPOSITORY ACCESS
    # --------------------------------------------------------

    repository_data = github_api_request(
        "GET",
        endpoint,
        token=user_access_token,
    )

    if not isinstance(repository_data, dict):
        raise GitHubAuthError(
            "GitHub returned invalid repository information."
        )

    # This OAuth path is for private repositories.
    if repository_data.get("private") is not True:
        raise GitHubAuthError(
            "The selected repository is not private."
        )

    # Require permission to push to the repository.
    permissions = repository_data.get("permissions") or {}

    if not (
        permissions.get("push") is True
        or permissions.get("admin") is True
    ):
        raise GitHubAuthError(
            "Your GitHub account needs write access to this repository."
        )

    repository_id = repository_data.get("id")
    verified_owner = (
        repository_data.get("owner") or {}
    ).get("login")

    verified_name = repository_data.get("name")
    default_branch = repository_data.get("default_branch")

    if not all(
        (
            repository_id,
            verified_owner,
            verified_name,
            default_branch,
        )
    ):
        raise GitHubAuthError(
            "GitHub returned incomplete repository information."
        )

    # --------------------------------------------------------
    # 2. FIND THE GITHUB APP INSTALLATION
    # --------------------------------------------------------

    # Authenticate as CodeView's GitHub App.
    app_jwt = generate_github_app_jwt()

    # GitHub identifies the installation associated with this repo.
    installation_data = github_api_request(
        "GET",
        f"{endpoint}/installation",
        token=app_jwt,
    )

    installation_id = installation_data.get("id")

    if not installation_id:
        raise GitHubAuthError(
            "The CodeView GitHub App is not installed for this repository."
        )

    # --------------------------------------------------------
    # 3. VERIFY INSTALLATION ACCESS TO THIS EXACT REPOSITORY
    # --------------------------------------------------------

    installation_token = get_installation_access_token(
        installation_id
    )

    installed_repository = github_api_request(
        "GET",
        endpoint,
        token=installation_token,
    )

    # Compare GitHub's stable repository IDs.
    if installed_repository.get("id") != repository_id:
        raise GitHubAuthError(
            "The GitHub App installation cannot access this repository."
        )

    # Confirm that the installation has contents read permission.
    installation_permissions = (
        installation_data.get("permissions") or {}
    )

    if installation_permissions.get("contents") not in (
        "read",
        "write",
    ):
        raise GitHubAuthError(
            "The GitHub App requires repository contents access."
        )

    return {
        "github_owner": verified_owner,
        "repository_name": verified_name,
        "default_branch": default_branch,
        "github_repository_id": repository_id,
        "github_installation_id": installation_id,
        "is_private": True,
    }


@login_required
@require_GET
def github_oauth_callback(request):
    """
    Complete GitHub OAuth and connect the verified private repository.

    The repository is saved only after:
    - OAuth state validation
    - User authentication
    - Repository permission verification
    - GitHub App installation verification
    - Current group approval verification
    """

    # --------------------------------------------------------
    # 1. READ AND CONSUME OAUTH SESSION INFORMATION
    # --------------------------------------------------------

    expected_state = request.session.get(
        "github_oauth_state"
    )

    group_id = request.session.get(
        "github_oauth_group_id"
    )

    github_owner = request.session.get(
        "github_oauth_owner"
    )

    repository_name = request.session.get(
        "github_oauth_repository"
    )

    owner_generation = request.session.get(
        "github_oauth_owner_generation"
    )

    oauth_user_id = request.session.get(
        "github_oauth_user_id"
    )

    membership_generation = request.session.get(
        "github_oauth_membership_generation"
    )

    approval_id = request.session.get(
        "github_oauth_approval_id"
    )

    started_at = request.session.get(
        "github_oauth_started_at"
    )

    received_state = request.GET.get("state", "")

    # Clear session context immediately to prevent reuse.
    clear_github_oauth_session(request)

    if (
        not expected_state
        or not received_state
        or not hmac.compare_digest(
            expected_state,
            received_state,
        )
    ):
        return HttpResponseBadRequest(
            "Invalid or expired GitHub authorization state."
        )

    if not all(
        (
            group_id,
            github_owner,
            repository_name,
            owner_generation,
            oauth_user_id,
            started_at,
        )
    ):
        return HttpResponseBadRequest(
            "GitHub authorization context is incomplete."
        )

    # Reject authorization attempts started by another user.
    if oauth_user_id != request.user.id:
        return HttpResponseForbidden(
            "GitHub authorization belongs to another developer."
        )

    # Reject expired authorization attempts.
    if (
        isinstance(started_at, bool)
        or not isinstance(started_at, int)
        or time.time() - started_at > OAUTH_MAX_AGE_SECONDS
        or started_at > time.time() + 60
    ):
        return HttpResponseBadRequest(
            "GitHub authorization expired. Please try again."
        )

    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
        is_private=True,
    )

    # Check whether the group owner changed during authorization.
    if str(group.owner_membership_generation) != owner_generation:
        return HttpResponseForbidden(
            "Group ownership changed during authorization."
        )

    # Check the current developer's permission.
    if not has_repository_connection_permission(
        group,
        request.user,
    ):
        return HttpResponseForbidden(
            "Repository connection permission is no longer valid."
        )

    # --------------------------------------------------------
    # 2. HANDLE GITHUB AUTHORIZATION CANCELLATION
    # --------------------------------------------------------

    if request.GET.get("error"):
        messages.error(
            request,
            "GitHub authorization was cancelled or denied.",
        )

        return redirect(
            "meeting_room",
            group_id=group.id,
        )

    authorization_code = request.GET.get("code")

    if not authorization_code:
        return HttpResponseBadRequest(
            "GitHub did not return an authorization code."
        )

    # --------------------------------------------------------
    # 3. VERIFY THE DEVELOPER AND PRIVATE REPOSITORY
    # --------------------------------------------------------

    try:
        user_access_token = get_github_user_access_token(
            authorization_code
        )

        github_user = github_api_request(
            "GET",
            "/user",
            token=user_access_token,
        )

        if not (
            github_user.get("id")
            and github_user.get("login")
        ):
            raise GitHubAuthError(
                "GitHub returned incomplete account information."
            )

        # Verify repository access before any database changes.
        verified_repository = verify_private_repository(
            github_owner,
            repository_name,
            user_access_token,
        )

    except (
        GitHubAuthError,
        httpx.HTTPError,
        ValueError,
        TypeError,
    ):
        messages.error(
            request,
            (
                "GitHub could not verify this private repository. "
                "Check your repository permissions and confirm "
                "that the CodeView GitHub App is installed."
            ),
        )

        return redirect(
            "meeting_room",
            group_id=group.id,
        )

    # --------------------------------------------------------
    # 4. SAVE THE VERIFIED REPOSITORY ATOMICALLY
    # --------------------------------------------------------

    with transaction.atomic():

        # Lock the group to serialize repository replacements.
        locked_group = (
            ProjectGroup.objects
            .select_for_update()
            .get(id=group.id)
        )

        # Reject ownership changes during the OAuth process.
        if (
            str(locked_group.owner_membership_generation)
            != owner_generation
        ):
            return HttpResponseForbidden(
                "Group ownership changed during authorization."
            )

        if not locked_group.is_private:
            return HttpResponseForbidden(
                "This group no longer supports repository connections."
            )

        # Owners do not need a repository approval.
        is_owner = locked_group.owner_id == request.user.id

        if not is_owner:

            # Lock the current membership.
            membership = (
                GroupMember.objects
                .select_for_update()
                .filter(
                    group=locked_group,
                    user=request.user,
                )
                .first()
            )

            if membership is None:
                return HttpResponseForbidden(
                    "You are no longer a group member."
                )

            if (
                str(membership.membership_generation)
                != membership_generation
            ):
                return HttpResponseForbidden(
                    "Your group membership changed during authorization."
                )

            # Lock the exact approval used to start OAuth.
            approval = (
                RepositoryConnectionRequest.objects
                .select_for_update()
                .filter(
                    id=approval_id,
                    group=locked_group,
                    requested_by=request.user,
                    status="approved",
                    membership_generation=(
                        membership.membership_generation
                    ),
                    owner_membership_generation=(
                        locked_group.owner_membership_generation
                    ),
                )
                .first()
            )

            if approval is None:
                return HttpResponseForbidden(
                    "Your repository approval is no longer valid."
                )

        # Save or replace the group's single repository.
        GroupRepository.objects.update_or_create(
            group=locked_group,
            defaults=verified_repository,
        )

        # Consume member approval in the same transaction.
        if not is_owner:
            RepositoryConnectionRequest.objects.filter(
                id=approval.id,
                status="approved",
            ).update(
                status="used",
                used_at=timezone.now(),
            )

    messages.success(
        request,
        (
            "Private GitHub repository connected successfully! "
            f"Authorized using @{github_user['login']}."
        ),
    )

    return redirect(
        "meeting_room",
        group_id=group.id,
    )