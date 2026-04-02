from django.urls import path

from .views import DeveloperCreateView
from .views import DeveloperUploadView
from .views import DevelopersView
from .views import LeaveCreateView
from .views import LeaveDeleteView
from .views import LeaveUpdateView
from .views import LeaveView
from .views import ObserverCreateView
from .views import ObserversView
from .views import PhaseCreateView
from .views import PhaseDeleteView
from .views import PhaseEditView
from .views import PhaseUpdateView
from .views import PlanningView
from .views import ProjectCreateView
from .views import ProjectUploadView
from .views import ProjectsView
from .views import ScheduleView

app_name = "planning"

urlpatterns = [
    path("developers/", DevelopersView.as_view(), name="developers"),
    path("developers/add/", DeveloperCreateView.as_view(), name="developer_add"),
    path("developers/upload/", DeveloperUploadView.as_view(), name="developer_upload"),
    path("observers/", ObserversView.as_view(), name="observers"),
    path("observers/add/", ObserverCreateView.as_view(), name="observer_add"),
    path("projects/", ProjectsView.as_view(), name="projects"),
    path("projects/add/", ProjectCreateView.as_view(), name="project_add"),
    path("projects/upload/", ProjectUploadView.as_view(), name="project_upload"),
    path("leave/", LeaveView.as_view(), name="leave"),
    path("leave/add/", LeaveCreateView.as_view(), name="leave_add"),
    path("leave/<int:pk>/delete/", LeaveDeleteView.as_view(), name="leave_delete"),
    path("leave/<int:pk>/update/", LeaveUpdateView.as_view(), name="leave_update"),
    path("planning/", PlanningView.as_view(), name="planning"),
    path("schedule/", ScheduleView.as_view(), name="schedule"),
    path("phase/add/", PhaseCreateView.as_view(), name="phase_add"),
    path("phase/<int:pk>/delete/", PhaseDeleteView.as_view(), name="phase_delete"),
    path("phase/<int:pk>/update/", PhaseUpdateView.as_view(), name="phase_update"),
    path("phase/<int:pk>/edit/", PhaseEditView.as_view(), name="phase_edit"),
]
