from django.contrib import admin

from .models import DeveloperProfile
from .models import Leave
from .models import Phase
from .models import Project
from .models import ProjectAllocation
from .models import ProjectTimeEntry
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


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ["code", "year", "semester_type", "start_date", "end_date"]
    ordering = ["-year", "-semester_type"]


class ProjectAllocationInline(admin.TabularInline):
    model = ProjectAllocation
    extra = 1


class ProjectTimeEntryInline(admin.TabularInline):
    model = ProjectTimeEntry
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["name", "semester", "colour"]
    list_filter = ["semester", "streams", "tags"]
    filter_horizontal = ["streams", "tags"]
    inlines = [ProjectAllocationInline, ProjectTimeEntryInline]
    search_fields = ["name"]


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
    list_display = [
        "developer",
        "project",
        "semester",
        "start_date",
        "end_date",
        "effort_multiplier",
    ]
    list_filter = ["semester", "project"]
    search_fields = ["developer__user__email", "developer__user__name"]
