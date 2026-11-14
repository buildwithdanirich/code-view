"""Preserve existing URL names for CodeView's other apps."""
from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.user_login, name="login"),
    path("logout/", views.user_logout, name="logout"),
    path("verify-email/<str:uidb64>/<str:token>/", views.verify_email, name="verify_email"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("reset-password/<str:uidb64>/<str:token>/", views.password_reset_confirm, name="password_reset_confirm"),
]
