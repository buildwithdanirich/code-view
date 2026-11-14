from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth import authenticate, login, logout
from .forms import RegisterForm
from django.views.decorators.http import require_POST


def register(request):
    # Check whether the user submitted the registration form.
    if request.method == "POST":
        form = RegisterForm(request.POST)

        if form.is_valid():
            # Create the user account in PostgreSQL.
            user = form.save()

            # Automatically log the new user in.
            login(request, user)

            # Redirect directly to the Community page.
            return redirect("groups")

    else:
        # Display an empty registration form.
        form = RegisterForm()

    # Show the form again if registration fails.
    return render(request, "users/register.html", {"form": form})

def user_login(request):
    # Check whether the user submitted the login form.
    if request.method == "POST":

        # Collect the username and password.
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        # Check whether the login details are correct.
        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            # Log the user into CodeView.
            login(request, user)

            # Send the user directly to the Community page.
            return redirect("groups")

        # Display an error if login fails.
        return render(
            request,
            "users/login.html",
            {"error": "Incorrect username or password. Please try again."}
        )

    # Display the login page when someone first visits.
    return render(request, "users/login.html")


@require_POST
def user_logout(request):
    # Log the user out.
    logout(request)

    # Redirect to the homepage.
    return redirect("home")