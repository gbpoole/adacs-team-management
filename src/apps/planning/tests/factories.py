import datetime

import factory
from factory.django import DjangoModelFactory

from apps.planning.models import DeveloperLane
from apps.planning.models import DeveloperProfile
from apps.planning.models import Leave
from apps.planning.models import Phase
from apps.planning.models import Project
from apps.planning.models import ProjectAllocation
from apps.planning.models import ProjectTimeEntry
from apps.planning.models import Semester
from apps.planning.models import SemesterDeveloper
from apps.planning.models import SemesterObserver
from apps.planning.models import SemesterType
from apps.planning.models import Stream
from apps.planning.models import Tag
from apps.planning.models import UserProjectAccess
from apps.users.models import Role
from apps.users.models import User


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    name = factory.Faker("name")
    role = Role.USER
    organisation = "ADACS"
    password = factory.PostGenerationMethodCall("set_password", "testpassword")


class PMUserFactory(UserFactory):
    role = Role.PM


class TagFactory(DjangoModelFactory):
    class Meta:
        model = Tag

    name = factory.Sequence(lambda n: f"tag-{n}")


class StreamFactory(DjangoModelFactory):
    class Meta:
        model = Stream

    name = factory.Sequence(lambda n: f"stream-{n}")


class DeveloperProfileFactory(DjangoModelFactory):
    class Meta:
        model = DeveloperProfile

    user = factory.SubFactory(UserFactory)
    colour = ""  # triggers auto-assign in model.save()


class SemesterFactory(DjangoModelFactory):
    class Meta:
        model = Semester
        django_get_or_create = ("year", "semester_type")

    year = 2026
    semester_type = SemesterType.A


class ProjectFactory(DjangoModelFactory):
    class Meta:
        model = Project

    name = factory.Sequence(lambda n: f"Project {n}")
    semester = factory.SubFactory(SemesterFactory)
    colour = ""  # triggers auto-assign


class ProjectAllocationFactory(DjangoModelFactory):
    class Meta:
        model = ProjectAllocation

    project = factory.SubFactory(ProjectFactory)
    semester = factory.SubFactory(SemesterFactory)
    weeks_new = 10


class ProjectTimeEntryFactory(DjangoModelFactory):
    class Meta:
        model = ProjectTimeEntry

    project = factory.SubFactory(ProjectFactory)
    weeks = 1
    comment = ""


class SemesterObserverFactory(DjangoModelFactory):
    class Meta:
        model = SemesterObserver

    user = factory.SubFactory(UserFactory)
    semester = factory.SubFactory(SemesterFactory)


class UserProjectAccessFactory(DjangoModelFactory):
    class Meta:
        model = UserProjectAccess

    user = factory.SubFactory(UserFactory)


class PreRegAccessFactory(DjangoModelFactory):
    """Pre-registration access policy keyed to an unregistered DeveloperProfile."""

    class Meta:
        model = UserProjectAccess

    user = None
    developer_profile = factory.SubFactory(DeveloperProfileFactory, user=None)


class SemesterDeveloperFactory(DjangoModelFactory):
    class Meta:
        model = SemesterDeveloper

    developer = factory.SubFactory(DeveloperProfileFactory)
    semester = factory.SubFactory(SemesterFactory)
    effort_available = 26


class LeaveFactory(DjangoModelFactory):
    class Meta:
        model = Leave

    developer = factory.SubFactory(DeveloperProfileFactory)
    start_date = datetime.date(2026, 3, 1)
    end_date = datetime.date(2026, 3, 7)


class DeveloperLaneFactory(DjangoModelFactory):
    class Meta:
        model = DeveloperLane

    developer = factory.SubFactory(DeveloperProfileFactory)
    semester = factory.SubFactory(SemesterFactory)
    order = 0


class PhaseFactory(DjangoModelFactory):
    class Meta:
        model = Phase

    developer = factory.SubFactory(DeveloperProfileFactory)
    project = factory.SubFactory(ProjectFactory)
    semester = factory.SubFactory(SemesterFactory)
    start_date = datetime.date(2026, 1, 5)
    end_date = datetime.date(2026, 2, 2)
    effort_multiplier = 1.0


def make_semester_developer(semester=None):
    """Create a User + DeveloperProfile + SemesterDeveloper for the given semester."""
    sem = semester or Semester.get_current()
    profile = DeveloperProfileFactory()
    SemesterDeveloperFactory(developer=profile, semester=sem, effort_available=26)
    return profile


def make_restricted_access_user(semester=None):
    """Create a User + UserProjectAccess restriction record."""
    _ = semester or Semester.get_current()  # retained for call compatibility
    user = UserFactory()
    return UserProjectAccessFactory(user=user)


def make_semester_observer(semester=None):
    """Backward-compatible alias for make_restricted_access_user."""
    return make_restricted_access_user(semester=semester)
