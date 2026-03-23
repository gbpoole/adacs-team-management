from django.urls import path

from .views import DevelopersView
from .views import ObserversView
from .views import ProjectsView

app_name = "planning"

urlpatterns = [
    path("developers/", DevelopersView.as_view(), name="developers"),
    path("observers/", ObserversView.as_view(), name="observers"),
    path("projects/", ProjectsView.as_view(), name="projects"),
]
