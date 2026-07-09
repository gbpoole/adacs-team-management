"""Live per-project effort accounting.

Resourcing is computed live rather than stored: a project's resourced weeks
are its own newly-allocated weeks plus the carryover from the project it
continues (the parent's resourced minus allocated, which may be negative
when the parent is over-allocated). Allocated weeks combine developer phase
effort and non-developer time entries.

``Phase.effort_weeks()`` is a Python-side computation (working days minus
leave), so none of this can be a queryset annotation; everything is
bulk-fetched to avoid N+1 queries.
"""

from dataclasses import dataclass

from django.db.models import Sum

from apps.planning.models import Phase
from apps.planning.models import Project
from apps.planning.models import ProjectAllocation
from apps.planning.models import ProjectTimeEntry


@dataclass
class ProjectEffort:
    weeks_new: float = 0.0
    carryover: float = 0.0  # signed; negative when the parent is over-allocated
    resourced: float = 0.0  # weeks_new + carryover
    allocated: float = 0.0  # phase effort + time entries
    unallocated: float = 0.0  # resourced - allocated (signed)


def _ancestor_closure(project_pks) -> dict[int, int | None]:
    """Map every given project pk (and all continuation ancestors) to its parent pk."""
    all_pks: set[int] = set()
    frontier = {pk for pk in project_pks if pk is not None}
    while frontier:
        all_pks.update(frontier)
        parents = Project.objects.filter(pk__in=frontier).values_list(
            "pk",
            "continuation_of_id",
        )
        frontier = {
            parent_pk
            for _, parent_pk in parents
            if parent_pk is not None and parent_pk not in all_pks
        }
    if not all_pks:
        return {}
    return dict(
        Project.objects.filter(pk__in=all_pks).values_list(
            "pk",
            "continuation_of_id",
        ),
    )


def compute_project_effort(project_pks) -> dict[int, ProjectEffort]:
    """Compute live effort figures for the given projects and their ancestors.

    Returns a dict keyed by project pk covering the full continuation-ancestor
    closure of ``project_pks``. Continuation chains are walked with a visited
    set, so a (mis-configured) cycle terminates and contributes no carryover.
    """
    parent_map = _ancestor_closure(project_pks)
    all_pks = set(parent_map)
    if not all_pks:
        return {}

    weeks_new_map: dict[int, float] = {}
    for proj_pk, weeks_new in ProjectAllocation.objects.filter(
        project_id__in=all_pks,
    ).values_list("project_id", "weeks_new"):
        weeks_new_map[proj_pk] = weeks_new_map.get(proj_pk, 0.0) + float(weeks_new)

    allocated_map: dict[int, float] = {}
    for phase in (
        Phase.objects.filter(project_id__in=all_pks)
        .select_related("developer")
        .prefetch_related("developer__leave_periods")
    ):
        allocated_map[phase.project_id] = (
            allocated_map.get(phase.project_id, 0.0) + phase.effort_weeks()
        )
    for proj_pk, total in (
        ProjectTimeEntry.objects.filter(project_id__in=all_pks)
        .values_list("project_id")
        .annotate(total=Sum("weeks"))
        .values_list("project_id", "total")
    ):
        allocated_map[proj_pk] = allocated_map.get(proj_pk, 0.0) + float(total)

    resourced_memo: dict[int, float] = {}

    def resourced(pk: int, visited: set[int]) -> float:
        if pk in resourced_memo:
            return resourced_memo[pk]
        value = weeks_new_map.get(pk, 0.0) + carryover(pk, visited)
        resourced_memo[pk] = value
        return value

    def carryover(pk: int, visited: set[int]) -> float:
        parent = parent_map.get(pk)
        if parent is None or parent in visited:
            return 0.0
        visited.add(parent)
        return resourced(parent, visited) - allocated_map.get(parent, 0.0)

    result: dict[int, ProjectEffort] = {}
    for pk in all_pks:
        carry = round(carryover(pk, {pk}), 2)
        weeks_new = round(weeks_new_map.get(pk, 0.0), 2)
        res = round(weeks_new + carry, 2)
        alloc = round(allocated_map.get(pk, 0.0), 2)
        result[pk] = ProjectEffort(
            weeks_new=weeks_new,
            carryover=carry,
            resourced=res,
            allocated=alloc,
            unallocated=round(res - alloc, 2),
        )
    return result
