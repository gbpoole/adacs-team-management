from django.contrib import admin

from .models import DeveloperProfile
from .models import Leave
from .models import ObserverProfile
from .models import Phase
from .models import Project
from .models import ProjectAllocation
from .models import ProjectSemesterName
from .models import Semester
from .models import SemesterDeveloper
from .models import Stream
from .models import Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "colour"]
    search_fields = ["name"]


@admin.register(Stream)
class StreamAdmin(admin.ModelAdmin):
    list_display = ["name", "colour"]
    search_fields = ["name"]


@admin.register(DeveloperProfile)
class DeveloperProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "colour"]
    filter_horizontal = ["tags"]
    search_fields = ["user__email", "user__name"]


@admin.register(ObserverProfile)
class ObserverProfileAdmin(admin.ModelAdmin):
    list_display = ["user"]
    filter_horizontal = ["project_access"]
    search_fields = ["user__email", "user__name"]


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ["code", "year", "semester_type", "start_date", "end_date"]
    ordering = ["-year", "-semester_type"]


class ProjectSemesterNameInline(admin.TabularInline):
    model = ProjectSemesterName
    extra = 1


class ProjectAllocationInline(admin.TabularInline):
    model = ProjectAllocation
    extra = 1


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["__str__", "colour"]
    list_filter = ["streams", "tags"]
    filter_horizontal = ["streams", "tags"]
    inlines = [ProjectSemesterNameInline, ProjectAllocationInline]
    search_fields = ["semester_names__name"]


@admin.register(SemesterDeveloper)
class SemesterDeveloperAdmin(admin.ModelAdmin):
    list_display = ["developer", "semester", "effort_available"]
    list_filter = ["semester"]
    search_fields = ["developer__user__email", "developer__user__name"]


@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ["developer", "start_date", "end_date"]
    list_filter = ["developer"]
    search_fields = ["developer__user__email", "developer__user__name"]


@admin.register(Phase)
class PhaseAdmin(admin.ModelAdmin):
    list_display = ["developer", "project", "semester", "start_date", "end_date", "effort_multiplier"]
    list_filter = ["semester", "project"]
    search_fields = ["developer__user__email", "developer__user__name"]
