"""Secure GitHub App authentication and API requests."""

import time
from pathlib import Path

import httpx
import jwt

from django.conf import settings


GITHUB_API_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


class GitHubAuthError(Exception):
    """Raised when GitHub authentication or an API request fails."""


def generate_github_app_jwt():
    """
    Generate a signed JWT to authenticate CodeView's GitHub App.

    This token identifies the GitHub App, not an individual user.
    """

    # Read the GitHub App ID from Django settings.
    app_id = getattr(settings, "GITHUB_APP_ID", None)

    # Read the location of the GitHub App private key.
    private_key_path = getattr(
        settings,
        "GITHUB_APP_PRIVATE_KEY_PATH",
        None,
    )

    # Stop if either configuration value is missing.
    if not app_id or not private_key_path:
        raise GitHubAuthError(
            "GitHub App credentials are not configured."
        )

    # Locate the private key on the server.
    key_path = Path(private_key_path).expanduser()

    try:
        # Read the private key without displaying its contents.
        private_key = key_path.read_bytes()

    except OSError as exc:
        raise GitHubAuthError(
            "Unable to read the GitHub App private key."
        ) from exc

    # Get the current Unix timestamp.
    now = int(time.time())

    # GitHub App JWTs must have a short lifetime.
    payload = {
        "iat": now - 60,
        "exp": now + 540,
        "iss": str(app_id),
    }

    try:
        # Sign the JWT using the GitHub App private key.
        return jwt.encode(
            payload,
            private_key,
            algorithm="RS256",
        )

    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise GitHubAuthError(
            "Unable to generate the GitHub App JWT."
        ) from exc


def github_api_request(
    method,
    endpoint,
    *,
    token,
    json_data=None,
):
    """
    Send an authenticated request to the GitHub REST API.

    The token is never included in an error message.
    """

    # Only allow GitHub API paths, not arbitrary external URLs.
    if not endpoint.startswith("/") or endpoint.startswith("//"):
        raise GitHubAuthError("Invalid GitHub API endpoint.")

    # Prevent endpoint values from overriding the GitHub API host.
    if "\\" in endpoint or "://" in endpoint:
        raise GitHubAuthError("Invalid GitHub API endpoint.")

    # Only permit the HTTP methods we need.
    if method.upper() not in {"GET", "POST"}:
        raise GitHubAuthError("Unsupported GitHub API method.")

    # Require an authentication token.
    if not token:
        raise GitHubAuthError("GitHub authentication token is missing.")

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "CodeView",
    }

    try:
        # Send the request to GitHub.
        with httpx.Client(
            base_url=GITHUB_API_URL,
            timeout=10.0,
            follow_redirects=False,
            trust_env=False,
        ) as client:

            response = client.request(
                method.upper(),
                endpoint,
                headers=headers,
                json=json_data,
            )

            # Raise an exception for unsuccessful responses.
            response.raise_for_status()

            # Convert GitHub's JSON response into a Python object.
            return response.json()

    except (httpx.HTTPError, ValueError) as exc:
        raise GitHubAuthError(
            "GitHub API request failed."
        ) from exc


def get_installation_access_token(installation_id):
    """
    Request a temporary token for a GitHub App installation.

    The installation must be independently verified and authorized
    before this function is called.
    """

    # Reject missing, invalid, or non-positive installation IDs.
    if (
        isinstance(installation_id, bool)
        or not str(installation_id).isdecimal()
        or int(installation_id) <= 0
    ):
        raise GitHubAuthError("Invalid GitHub installation ID.")

    # Authenticate CodeView as its GitHub App.
    app_jwt = generate_github_app_jwt()

    # Ask GitHub to create an installation access token.
    result = github_api_request(
        "POST",
        f"/app/installations/{int(installation_id)}/access_tokens",
        token=app_jwt,
    )

    # Extract the temporary access token.
    access_token = result.get("token")

    if not access_token:
        raise GitHubAuthError(
            "GitHub did not return an installation access token."
        )

    return access_token