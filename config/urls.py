from django.contrib import admin
from django.urls import path, include

from roleflix.views import RecuperarSenhaView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/password/reset/", RecuperarSenhaView.as_view(), name="account_reset_password"),
    path("accounts/", include("allauth.urls")),
    path("", include("roleflix.urls")),
]
