from django.shortcuts import render


def home(request):
    # Display the CodeView homepage.
    return render(request, "home_page/home.html")