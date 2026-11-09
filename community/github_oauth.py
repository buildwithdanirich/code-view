"""
GitHub OAuth authorization for CodeView.

This module will:
1. Verify that a developer can initiate a repository connection.
2. Generate a secure OAuth state value.
3. Redirect the developer to GitHub.
4. Later, handle GitHub's authorization callback.
"""

import secrets

from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .models import (
    ProjectGroup,
    GroupMember,
    RepositoryConnectionRequest,
)

import hmac
import httpx

from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.views.decorators.http import require_GET




@login_required
@require_POST
def start_github_authorization(request, group_id):
    """
    Start GitHub authorization for a group repository.

    Group owners can start directly.

    Other members must have a valid, approved request.
    """

    # Find the private development group.
    group = get_object_or_404(
        ProjectGroup,
        id=group_id,
        is_private=True,
    )

    # Check whether the current developer owns the group.
    is_owner = group.owner_id == request.user.id

    if not is_owner:

        # Find the developer's current group membership.
        membership = GroupMember.objects.filter(
            group=group,
            user=request.user,
        ).first()

        if membership is None:
            return HttpResponseForbidden(
                "You must belong to this group."
            )

        # Check for a valid owner-approved request.
        approval_exists = RepositoryConnectionRequest.objects.filter(
            group=group,
            requested_by=request.user,
            status="approved",
            membership_generation=membership.membership_generation,
            owner_membership_generation=group.owner_membership_generation,
        ).exists()

        if not approval_exists:
            return HttpResponseForbidden(
                "The group owner must approve your request first."
            )

    # Confirm that GitHub OAuth is configured.
    if not settings.GITHUB_CLIENT_ID:
        return HttpResponseForbidden(
            "GitHub OAuth is not configured."
        )

    # Generate a cryptographically secure random state value.
    state = secrets.token_urlsafe(32)

    # Store the state and group in the developer's session.
    # The callback will verify these values.
    request.session["github_oauth_state"] = state
    request.session["github_oauth_group_id"] = group.id

    # GitHub App OAuth authorization endpoint.
    authorization_url = "https://github.com/login/oauth/authorize"

    # Parameters sent to GitHub.
    parameters = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_OAUTH_CALLBACK_URL,
        "state": state,
    }

    # Redirect the developer to GitHub.
    return redirect(
        f"{authorization_url}?{urlencode(parameters)}"
    )

@login_required
@require_GET
def github_oauth_callback(request):
    """
    Handle GitHub's OAuth authorization response.

    Security:
    - Validate the OAuth state.
    - Exchange the code securely on the server.
    - Verify the GitHub user.
    - Do not expose access tokens to the browser.
    - Do not connect repositories before permission checks.
    """

    # ========================================================
    # 1. READ AND REMOVE THE OAUTH SESSION STATE
    # ========================================================

    expected_state = request.session.pop(
        "github_oauth_state",
        None,
    )

    group_id = request.session.pop(
        "github_oauth_group_id",
        None,
    )

    received_state = request.GET.get("state", "")

    # Reject callbacks without a valid matching state.
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

    # ========================================================
    # 2. HANDLE GITHUB AUTHORIZATION ERRORS
    # ========================================================

    if request.GET.get("error"):
        messages.error(
            request,
            "GitHub authorization was cancelled or denied.",
        )

        return redirect(
            "meeting_room",
            group_id=group_id,
        )

    # ========================================================
    # 3. GET THE AUTHORIZATION CODE
    # ========================================================

    authorization_code = request.GET.get("code")

    if not authorization_code:
        return HttpResponseBadRequest(
            "GitHub did not provide an authorization code."
        )

    # ========================================================
    # 4. EXCHANGE CODE FOR USER ACCESS TOKEN
    # ========================================================

    try:
        with httpx.Client(
            timeout=10.0,
            follow_redirects=False,
            trust_env=False,
        ) as client:

            token_response = client.post(
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

            token_response.raise_for_status()

            token_data = token_response.json()

    except (httpx.HTTPError, ValueError):
        messages.error(
            request,
            "Unable to complete GitHub authorization.",
        )

        return redirect(
            "meeting_room",
            group_id=group_id,
        )

    access_token = token_data.get("access_token")

    if not access_token:
        messages.error(
            request,
            "GitHub did not return an access token.",
        )

        return redirect(
            "meeting_room",
            group_id=group_id,
        )

    # ========================================================
    # 5. VERIFY THE GITHUB USER
    # ========================================================

    try:
        with httpx.Client(
            timeout=10.0,
            follow_redirects=False,
            trust_env=False,
        ) as client:

            user_response = client.get(
                "https://api.github.com/user",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent": "CodeView",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            user_response.raise_for_status()

            github_user = user_response.json()

    except (httpx.HTTPError, ValueError):
        messages.error(
            request,
            "Unable to verify your GitHub account.",
        )

        return redirect(
            "meeting_room",
            group_id=group_id,
        )

    github_user_id = github_user.get("id")
    github_username = github_user.get("login")

    if not github_user_id or not github_username:
        return HttpResponseBadRequest(
            "GitHub returned incomplete account information."
        )

    # ========================================================
    # 6. STORE TEMPORARY AUTHORIZATION CONTEXT
    # ========================================================

    # Store only the verified GitHub identity.
    # Do not put the access token in the Django session.
    request.session["github_verified_user_id"] = github_user_id
    request.session["github_verified_username"] = github_username
    request.session["github_verified_group_id"] = group_id

    messages.success(
        request,
        (
            f"GitHub account @{github_username} verified. "
            "Repository authorization is not complete yet."
        ),
    )

    return redirect(
        "meeting_room",
        group_id=group_id,
    )