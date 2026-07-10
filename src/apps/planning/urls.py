from django.urls import path

from .views import DeveloperCreateView
from .views import DeveloperDeleteView
from .views import DeveloperDownloadView
from .views import DeveloperMigrateView
from .views import DevelopersView
from .views import DeveloperUpdateView
from .views import LeaveCreateView
from .views import LeaveDeleteView
from .views import LeaveUpdateView
from .views import LeaveView
from .views import ObserverCreateView
from .views import ObserverDeleteView
from .views import ObserversView
from .views import ObserverUpdateView
from .views import PeopleView
from .views import PersonUpdateView
from .views import PhaseCreateView
from .views import PhaseDeleteView
from .views import PhaseEditView
from .views import PhaseUpdateView
from .views import PlanningView
from .views import ProjectCreateView
from .views import ProjectDeleteView
from .views import ProjectDownloadView
from .views import ProjectMigrateView
from .views import ProjectsView
from .views import ProjectTimeEntryCreateView
from .views import ProjectTimeEntryDeleteView
from .views import ProjectUpdateView
from .views import ScheduleView
from .views import SemesterCreateView
from .views import SemesterSwitchView
from .views import StreamCreateView
from .views import StreamDeleteView
from .views import StreamsView
from .views import StreamUpdateView
from .views import TagCreateView
from .views import TagDeleteView
from .views import TagsView
from .views import TagUpdateView

app_name = "planning"

urlpatterns = [
    path("developers/", DevelopersView.as_view(), name="developers"),
    path("developers/add/", DeveloperCreateView.as_view(), name="developer_add"),
    path(
        "developers/download/",
        DeveloperDownloadView.as_view(),
        name="developer_download",
    ),
    path(
        "developers/migrate/", DeveloperMigrateView.as_view(), name="developer_migrate"
    ),
    path(
        "developers/<int:pk>/edit/",
        DeveloperUpdateView.as_view(),
        name="developer_edit",
    ),
    path(
        "developers/<int:pk>/delete/",
        DeveloperDeleteView.as_view(),
        name="developer_delete",
    ),
    path("observers/", ObserversView.as_view(), name="observers"),
    path("observers/add/", ObserverCreateView.as_view(), name="observer_add"),
    path(
        "observers/<int:pk>/edit/", ObserverUpdateView.as_view(), name="observer_edit"
    ),
    path(
        "observers/<int:pk>/delete/",
        ObserverDeleteView.as_view(),
        name="observer_delete",
    ),
    path("projects/", ProjectsView.as_view(), name="projects"),
    path("projects/add/", ProjectCreateView.as_view(), name="project_add"),
    path("projects/download/", ProjectDownloadView.as_view(), name="project_download"),
    path("projects/migrate/", ProjectMigrateView.as_view(), name="project_migrate"),
    path("projects/<int:pk>/edit/", ProjectUpdateView.as_view(), name="project_edit"),
    path(
        "projects/<int:pk>/delete/", ProjectDeleteView.as_view(), name="project_delete"
    ),
    path(
        "projects/<int:pk>/time-entries/add/",
        ProjectTimeEntryCreateView.as_view(),
        name="project_time_entry_add",
    ),
    path(
        "projects/time-entries/<int:pk>/delete/",
        ProjectTimeEntryDeleteView.as_view(),
        name="project_time_entry_delete",
    ),
    path("leave/", LeaveView.as_view(), name="leave"),
    path("leave/add/", LeaveCreateView.as_view(), name="leave_add"),
    path("leave/<int:pk>/delete/", LeaveDeleteView.as_view(), name="leave_delete"),
    path("leave/<int:pk>/update/", LeaveUpdateView.as_view(), name="leave_update"),
    path("people/", PeopleView.as_view(), name="people"),
    path("people/<int:pk>/edit/", PersonUpdateView.as_view(), name="person_edit"),
    path("semester/switch/", SemesterSwitchView.as_view(), name="semester_switch"),
    path("semester/add/", SemesterCreateView.as_view(), name="semester_add"),
    path("planning/", PlanningView.as_view(), name="planning"),
    path("schedule/", ScheduleView.as_view(), name="schedule"),
    path("phase/add/", PhaseCreateView.as_view(), name="phase_add"),
    path("phase/<int:pk>/delete/", PhaseDeleteView.as_view(), name="phase_delete"),
    path("phase/<int:pk>/update/", PhaseUpdateView.as_view(), name="phase_update"),
    path("phase/<int:pk>/edit/", PhaseEditView.as_view(), name="phase_edit"),
    path("tags/", TagsView.as_view(), name="tags"),
    path("tags/add/", TagCreateView.as_view(), name="tag_add"),
    path("tags/<int:pk>/edit/", TagUpdateView.as_view(), name="tag_edit"),
    path("tags/<int:pk>/delete/", TagDeleteView.as_view(), name="tag_delete"),
    path("streams/", StreamsView.as_view(), name="streams"),
    path("streams/add/", StreamCreateView.as_view(), name="stream_add"),
    path("streams/<int:pk>/edit/", StreamUpdateView.as_view(), name="stream_edit"),
    path("streams/<int:pk>/delete/", StreamDeleteView.as_view(), name="stream_delete"),
]
