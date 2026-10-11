from django.contrib import admin
from django.urls import path

from tests.testapp import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("guarded/", views.guarded, name="guarded"),
    path("guarded-redirect/", views.guarded_with_redirect, name="guarded-redirect"),
    path("old/", views.old, name="old"),
    path("rendered/", views.rendered, name="rendered"),
]
