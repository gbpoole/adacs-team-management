import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.planning.models import DeveloperProfile
from apps.planning.models import Leave
from apps.planning.models import Phase
from apps.planning.models import Project
from apps.planning.models import SemesterDeveloper
from apps.users.models import Role

from ._mixins import _has_restricted_view_access
from ._mixins import _is_semester_developer
from ._mixins import _visible_project_ids_for_user
from ._semester import get_selected_semester


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "pages/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        semester = get_selected_semester(self.request)
        ctx["semester"] = semester
        today = datetime.date.today()
        in_30_days = today + datetime.timedelta(days=30)
        role = user.role

        if role == Role.PM or user.is_superuser:
            ctx["dev_count"] = DeveloperProfile.objects.count()
            ctx["project_count"] = Project.objects.filter(semester=semester).count()
            records = SemesterDeveloper.objects.filter(semester=semester)
            ctx["total_effort_available"] = sum(r.effort_available for r in records)
            phases = list(
                Phase.objects.filter(semester=semester)
                .select_related("developer")
                .prefetch_related("developer__leave_periods"),
            )
            allocated: dict = {}
            for ph in phases:
                allocated[ph.developer_id] = (
                    allocated.get(ph.developer_id, 0) + ph.effort_weeks()
                )
            ctx["total_effort_allocated"] = round(sum(allocated.values()), 1)
            ctx["upcoming_leave"] = (
                Leave.objects.filter(end_date__gte=today, start_date__lte=in_30_days)
                .select_related("developer__user")
                .order_by("start_date")[:10]
            )

        if (
            _is_semester_developer(user, semester)
            and not user.is_superuser
            and role != Role.PM
        ):
            try:
                profile = user.developer_profile
                ctx["my_profile"] = profile
                sd = SemesterDeveloper.objects.filter(
                    developer=profile,
                    semester=semester,
                ).first()
                ctx["my_effort_available"] = sd.effort_available if sd else None
                my_phases = list(
                    Phase.objects.filter(developer=profile, semester=semester)
                    .select_related(
                        "project", "project__dev_lead", "project__science_lead"
                    )
                    .order_by("start_date"),
                )
                for ph in my_phases:
                    ph.display_name = ph.project.name
                    ph.is_dev_lead = ph.project.dev_lead_id == profile.pk
                    ph.is_science_lead = ph.project.science_lead_id == profile.pk
                ctx["my_effort_allocated"] = round(
                    sum(ph.effort_weeks() for ph in my_phases),
                    1,
                )
                ctx["my_phases"] = my_phases
                ctx["my_current_phases"] = [
                    ph for ph in my_phases if ph.start_date <= today <= ph.end_date
                ]
                ctx["my_next_phase"] = next(
                    (ph for ph in my_phases if ph.start_date > today),
                    None,
                )
                ctx["my_upcoming_leave"] = Leave.objects.filter(
                    developer=profile,
                    end_date__gte=today,
                ).order_by("start_date")[:5]
            except DeveloperProfile.DoesNotExist:
                pass

        if (
            _has_restricted_view_access(user, semester)
            and not user.is_superuser
            and role != Role.PM
        ):
            visible_project_ids = _visible_project_ids_for_user(user, semester)
            if visible_project_ids is None:
                ctx["my_project_count"] = Project.objects.filter(
                    semester=semester,
                ).count()
            else:
                ctx["my_project_count"] = len(visible_project_ids)

        return ctx
