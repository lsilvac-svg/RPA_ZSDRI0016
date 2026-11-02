from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.PanelView.as_view(), name="panel"),
]
