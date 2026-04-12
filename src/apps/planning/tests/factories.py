import datetime

import factory
from factory.django import DjangoModelFactory

from apps.planning.models import DeveloperLane
from apps.planning.models import DeveloperProfile
from apps.planning.models import Leave
from apps.planning.models import ObserverProfile
from apps.planning.models import Phase
from apps.planning.models import Project
from apps.planning.models import ProjectAllocation
from apps.planning.models import ProjectSemesterName
from apps.planning.models import Semester
from apps.planning.models import SemesterDeveloper
from apps.planning.models import SemesterType
from apps.planning.models import Stream
from apps.planning.models import Tag
from apps.users.models import Role
from apps.users.models import User


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    name = factory.Faker("name")
    role = Role.DEVELOPER
    organisation = "ADACS"
    password = factory.PostGenerationMethodCall("set_password", "testpassword")


class PMUserFactory(UserFactory):
    role = Role.PM


class DeveloperUserFactory(UserFactory):
    role = Role.DEVELOPER


class ObserverUserFactory(UserFactory):
    role = Role.OBSERVER


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

    user = factory.SubFactory(DeveloperUserFactory)
    colour = ""  # triggers auto-assign in model.save()


class ObserverProfileFactory(DjangoModelFactory):
    class Meta:
        model = ObserverProfile

    user = factory.SubFactory(ObserverUserFactory)


class SemesterFactory(DjangoModelFactory):
    class Meta:
        model = Semester
        django_get_or_create = ("year", "semester_type")

    year = 2026
    semester_type = SemesterType.A


class ProjectFactory(DjangoModelFactory):
    class Meta:
        model = Project

    colour = ""  # triggers auto-assign


class ProjectSemesterNameFactory(DjangoModelFactory):
    class Meta:
        model = ProjectSemesterName

    project = factory.SubFactory(ProjectFactory)
    semester = factory.SubFactory(SemesterFactory)
    name = factory.Sequence(lambda n: f"Project {n}")


class ProjectAllocationFactory(DjangoModelFactory):
    class Meta:
        model = ProjectAllocation

    project = factory.SubFactory(ProjectFactory)
    semester = factory.SubFactory(SemesterFactory)
    weeks_new = 10
    weeks_carryover = 0


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
