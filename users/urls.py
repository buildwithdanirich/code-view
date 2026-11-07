from django.urls import path
from .views import register, user_login, user_logout

urlpatterns = [
    # New users create an account.
    path("register/", register, name="register"),

    # Existing users log in.
    path("login/", user_login, name="login"),

    path("logout/", user_logout, name="logout"),
]