from .developers import DeveloperCreateView
from .developers import DeveloperDeleteView
from .developers import DeveloperDownloadView
from .developers import DeveloperMigrateView
from .developers import DeveloperUpdateView
from .developers import DevelopersView
from .home import HomeView
from .leave import LeaveCreateView
from .leave import LeaveDeleteView
from .leave import LeaveUpdateView
from .leave import LeaveView
from .observers import ObserverCreateView
from .observers import ObserverDeleteView
from .observers import ObserversView
from .observers import ObserverUpdateView
from .people import PeopleView
from .people import PersonUpdateView
from .phases import PhaseCreateView
from .phases import PhaseDeleteView
from .phases import PhaseEditView
from .phases import PhaseUpdateView
from .planning import PlanningView
from .projects import ProjectCreateView
from .projects import ProjectDeleteView
from .projects import ProjectDownloadView
from .projects import ProjectMigrateView
from .projects import ProjectsView
from .projects import ProjectUpdateView
from .schedule import ScheduleView
from ._semester import SemesterCreateView
from ._semester import SemesterSwitchView
from .streams import StreamCreateView
from .streams import StreamDeleteView
from .streams import StreamsView
from .streams import StreamUpdateView
from .tags import TagCreateView
from .tags import TagDeleteView
from .tags import TagsView
from .tags import TagUpdateView

__all__ = [
    "DeveloperCreateView",
    "DeveloperDeleteView",
    "DeveloperDownloadView",
    "DeveloperMigrateView",
    "DeveloperUpdateView",
    "DevelopersView",
    "HomeView",
    "LeaveCreateView",
    "LeaveDeleteView",
    "LeaveUpdateView",
    "LeaveView",
    "ObserverCreateView",
    "ObserverDeleteView",
    "ObserverUpdateView",
    "ObserversView",
    "PhaseCreateView",
    "PhaseDeleteView",
    "PhaseEditView",
    "PhaseUpdateView",
    "PeopleView",
    "PersonUpdateView",
    "PlanningView",
    "ProjectCreateView",
    "ProjectDeleteView",
    "ProjectDownloadView",
    "ProjectMigrateView",
    "ProjectUpdateView",
    "ProjectsView",
    "ScheduleView",
    "SemesterCreateView",
    "SemesterSwitchView",
    "StreamCreateView",
    "StreamDeleteView",
    "StreamsView",
    "StreamUpdateView",
    "TagCreateView",
    "TagDeleteView",
    "TagsView",
    "TagUpdateView",
]
