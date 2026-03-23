from django.urls import path

from .views import DevelopersView
from .views import LeaveCreateView
from .views import LeaveDeleteView
from .views import LeaveView
from .views import ObserversView
from .views import PhaseCreateView
from .views import PhaseDeleteView
from .views import PlanningView
from .views import ProjectsView
from .views import ScheduleView

app_name = "planning"

urlpatterns = [
    path("developers/", DevelopersView.as_view(), name="developers"),
    path("observers/", ObserversView.as_view(), name="observers"),
    path("projects/", ProjectsView.as_view(), name="projects"),
    path("leave/", LeaveView.as_view(), name="leave"),
    path("leave/add/", LeaveCreateView.as_view(), name="leave_add"),
    path("leave/<int:pk>/delete/", LeaveDeleteView.as_view(), name="leave_delete"),
    path("planning/", PlanningView.as_view(), name="planning"),
    path("schedule/", ScheduleView.as_view(), name="schedule"),
    path("phase/add/", PhaseCreateView.as_view(), name="phase_add"),
    path("phase/<int:pk>/delete/", PhaseDeleteView.as_view(), name="phase_delete"),
]
