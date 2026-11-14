"""Homepage routing for CodeView."""

from django.shortcuts import redirect


def home(request):
    """
    Control what developers see when they visit CodeView.
    """

    # Already logged in? Go to Groups.
    if request.user.is_authenticated:
        return redirect("groups")

    # Not logged in? Show the new Signup page.
    return redirect("register")