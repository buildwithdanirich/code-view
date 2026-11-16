"""
Public landing page for ColabVerse.

Visitors see the landing page before registering or logging in.
Authenticated developers go directly to the community feed.
"""

from django.shortcuts import redirect, render


def home(request):
    """
    Handle the ColabVerse homepage.

    - Logged-in developers: redirect to the developer feed.
    - Visitors: display the public landing page.
    """

    # Developers who are already logged in
    # can continue using ColabVerse.
    if request.user.is_authenticated:
        return redirect("questions:feed")

    # Visitors can explore ColabVerse before creating an account.
    return render(
        request,
        "home_page/home.html",
    )