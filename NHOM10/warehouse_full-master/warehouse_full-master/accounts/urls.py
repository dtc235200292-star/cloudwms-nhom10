from django.urls import path
from django.contrib.auth import views as auth_views
from .views import register, google_login, google_callback

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", register, name="register"),
    path("google/login/", google_login, name="google_login"),
    path("google/login/callback/", google_callback, name="google_callback"),
]
