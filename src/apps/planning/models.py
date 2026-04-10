import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Max
from django.utils.translation import gettext_lazy as _

from apps.users.models import Role

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

COLOUR_PALETTE = [
    ("#4E79A7", "Steel Blue"),
    ("#F28E2B", "Orange"),
    ("#E15759", "Brick Red"),
    ("#76B7B2", "Teal"),
    ("#59A14F", "Green"),
    ("#EDC948", "Yellow"),
    ("#B07AA1", "Purple"),
    ("#FF9DA7", "Pink"),
    ("#9C755F", "Brown"),
    ("#BAB0AC", "Grey"),
]

COLOUR_CHOICES = [(hex_val, name) for hex_val, name in COLOUR_PALETTE]

# Month at which semester A ends (inclusive); B starts at SEMESTER_A_END_MONTH + 1
SEMESTER_A_END_MONTH = 6


def _next_colour(used_colours: set[str]) -> str:
    """Return the first palette colour not already in ``used_colours``."""
    for hex_val, _name in COLOUR_PALETTE:
        if hex_val not in used_colours:
            return hex_val
    # All used — cycle from the start
    return COLOUR_PALETTE[0][0]


def _assign_colour_if_blank(instance, model_class) -> None:
    """Auto-assign the next unused palette colour if instance.colour is empty.
    Once all palette colours are in use, cycles by count so every colour gets
    used equally rather than repeating the first colour indefinitely."""
    if not instance.colour:
        used = set(model_class.objects.exclude(pk=instance.pk).values_list("colour", flat=True))
        if len(used) < len(COLOUR_PALETTE):
            instance.colour = _next_colour(used)
        else:
            count = model_class.objects.exclude(pk=instance.pk).count()
            instance.colour = COLOUR_PALETTE[count % len(COLOUR_PALETTE)][0]


# ---------------------------------------------------------------------------
# Tag (shared between developers and projects)
# ---------------------------------------------------------------------------


class Tag(models.Model):
    name = models.CharField(_("name"), max_length=100, unique=True)
    colour = models.CharField(_("colour"), max_length=7, choices=COLOUR_CHOICES, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        _assign_colour_if_blank(self, Tag)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# DeveloperProfile  (FR-02 / FR-03)
# ---------------------------------------------------------------------------


class DeveloperProfile(models.Model):
    """Per-user developer metadata (colour, tags) linked via OneToOne to User."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="developer_profile",
        limit_choices_to={"role": Role.DEVELOPER},
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="developers")
    colour = models.CharField(
        _("colour"),
        max_length=7,
        choices=COLOUR_CHOICES,
        blank=True,
    )

    class Meta:
        verbose_name = _("Developer Profile")
        verbose_name_plural = _("Developer Profiles")

    def __str__(self):
        return self.user.email

    def save(self, *args, **kwargs):
        _assign_colour_if_blank(self, DeveloperProfile)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# ObserverProfile  (FR-02 / FR-11)
# ---------------------------------------------------------------------------


class ObserverProfile(models.Model):
    """Read-only observer linked via OneToOne to User; accesses specific projects."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="observer_profile",
        limit_choices_to={"role": Role.OBSERVER},
    )

    class Meta:
        verbose_name = _("Observer Profile")
        verbose_name_plural = _("Observer Profiles")

    def __str__(self):
        return self.user.email


# ---------------------------------------------------------------------------
# Semester  (FR-06)
# ---------------------------------------------------------------------------


class SemesterType(models.TextChoices):
    A = "A", _("A (Jan-Jun)")
    B = "B", _("B (Jul-Dec)")


class Semester(models.Model):
    year = models.PositiveSmallIntegerField(_("year"))
    semester_type = models.CharField(
        _("semester"),
        max_length=1,
        choices=SemesterType.choices,
    )

    class Meta:
        unique_together = [("year", "semester_type")]
        ordering = ["year", "semester_type"]

    def __str__(self):
        return f"{self.year}{self.semester_type}"

    @property
    def code(self):
        return str(self)

    @property
    def start_date(self):
        if self.semester_type == SemesterType.A:
            return datetime.date(self.year, 1, 1)
        return datetime.date(self.year, 7, 1)

    @property
    def end_date(self):
        if self.semester_type == SemesterType.A:
            return datetime.date(self.year, 6, 30)
        return datetime.date(self.year, 12, 31)

    @classmethod
    def get_current(cls):
        today = datetime.date.today()  # noqa: DTZ011
        is_a = today.month <= SEMESTER_A_END_MONTH
        s_type = SemesterType.A if is_a else SemesterType.B
        obj, _ = cls.objects.get_or_create(year=today.year, semester_type=s_type)
        return obj


# ---------------------------------------------------------------------------
# Stream  (FR-07)
# ---------------------------------------------------------------------------


class Stream(models.Model):
    """Named stream (work category) for grouping projects."""

    name = models.CharField(_("name"), max_length=100, unique=True)
    colour = models.CharField(_("colour"), max_length=7, choices=COLOUR_CHOICES, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        _assign_colour_if_blank(self, Stream)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Project  (FR-07 / FR-08)
# ---------------------------------------------------------------------------


class Project(models.Model):
    tags = models.ManyToManyField(Tag, blank=True, related_name="projects")
    streams = models.ManyToManyField(Stream, blank=True, related_name="projects")
    colour = models.CharField(
        _("colour"),
        max_length=7,
        choices=COLOUR_CHOICES,
        blank=True,
    )

    class Meta:
        verbose_name = _("Project")
        verbose_name_plural = _("Projects")
        ordering = ["id"]

    def __str__(self):
        return f"Project #{self.pk}"

    def save(self, *args, **kwargs):
        _assign_colour_if_blank(self, Project)
        super().save(*args, **kwargs)

    def name_for_semester(self, semester):
        override = self.semester_names.filter(semester=semester).first()
        if override:
            return override.name
        fallback = (
            self.semester_names.filter(
                models.Q(semester__year__lt=semester.year)
                | models.Q(
                    semester__year=semester.year,
                    semester__semester_type__lte=semester.semester_type,
                ),
            )
            .order_by("-semester__year", "-semester__semester_type")
            .first()
        )
        return fallback.name if fallback else f"Project #{self.pk}"


class ProjectSemesterName(models.Model):
    """Stores the name of a project for a given semester (FR-08)."""

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="semester_names",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.CASCADE, related_name="project_names",
    )
    name = models.CharField(_("name"), max_length=255)

    class Meta:
        unique_together = [("project", "semester")]
        ordering = ["semester__year", "semester__semester_type"]

    def __str__(self):
        return f"{self.name} ({self.semester})"


# ---------------------------------------------------------------------------
# Project allocation  (FR-07)
# ---------------------------------------------------------------------------


class AllocationType(models.TextChoices):
    FIXED = "fixed", _("Fixed (specified semesters)")
    INDEFINITE = "indefinite", _("Indefinite (ongoing)")


class ProjectAllocation(models.Model):
    """Tracks how many weeks a project is allocated for a specific semester."""

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="allocations",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.CASCADE, related_name="project_allocations",
    )
    allocation_type = models.CharField(
        _("allocation type"),
        max_length=20,
        choices=AllocationType.choices,
        default=AllocationType.FIXED,
    )
    weeks_new = models.DecimalField(
        _("new weeks allocated"), max_digits=6, decimal_places=2, default=0,
    )
    weeks_carryover = models.DecimalField(
        _("weeks carried over"), max_digits=6, decimal_places=2, default=0,
    )

    class Meta:
        unique_together = [("project", "semester")]
        ordering = ["semester__year", "semester__semester_type"]

    def __str__(self):
        return f"{self.project} - {self.semester} ({self.total_weeks} wks)"

    @property
    def total_weeks(self):
        return self.weeks_new + self.weeks_carryover


# ---------------------------------------------------------------------------
# Observer project access  (FR-11)
# ---------------------------------------------------------------------------

ObserverProfile.add_to_class(
    "project_access",
    models.ManyToManyField(
        Project,
        blank=True,
        related_name="observer_access",
        help_text=_(
            "Projects this observer can view. Leave empty for no access.",
        ),
    ),
)

ObserverProfile.add_to_class(
    "stream_access",
    models.ManyToManyField(
        Stream,
        blank=True,
        related_name="observer_access",
        help_text=_(
            "Streams this observer can view. All projects in these streams are accessible.",
        ),
    ),
)


# ---------------------------------------------------------------------------
# SemesterDeveloper — effort available per developer per semester  (FR-09)
# ---------------------------------------------------------------------------


class SemesterDeveloper(models.Model):
    developer = models.ForeignKey(
        DeveloperProfile,
        on_delete=models.CASCADE,
        related_name="semester_records",
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.CASCADE,
        related_name="developer_records",
    )
    effort_available = models.DecimalField(
        _("effort available (weeks)"),
        max_digits=6,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        unique_together = [("developer", "semester")]
        ordering = ["semester__year", "semester__semester_type"]

    def __str__(self):
        return f"{self.developer} - {self.semester} ({self.effort_available} wks)"


# ---------------------------------------------------------------------------
# Leave  (FR-13)
# ---------------------------------------------------------------------------


class Leave(models.Model):
    developer = models.ForeignKey(
        DeveloperProfile,
        on_delete=models.CASCADE,
        related_name="leave_periods",
    )
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ["start_date"]

    def clean(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": _("End date must not be before start date.")})

    def duration_weeks(self) -> float:
        """Number of working days (Mon–Fri) in the leave period, expressed as weeks (÷5)."""
        work_days = 0
        day = self.start_date
        while day <= self.end_date:
            if day.weekday() < 5:
                work_days += 1
            day += datetime.timedelta(days=1)
        return round(work_days / 5, 2)

    def __str__(self):
        return f"{self.developer} {self.start_date}\u2013{self.end_date}"


# ---------------------------------------------------------------------------
# DeveloperLane — explicit row for a developer in a semester  (FR-15)
# ---------------------------------------------------------------------------


class DeveloperLane(models.Model):
    developer = models.ForeignKey(
        DeveloperProfile,
        on_delete=models.CASCADE,
        related_name="lanes",
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.CASCADE,
        related_name="lanes",
    )
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]
        unique_together = [["developer", "semester", "order"]]

    def __str__(self):
        return f"{self.developer} lane {self.order} ({self.semester})"


# ---------------------------------------------------------------------------
# Phase  (FR-15)
# ---------------------------------------------------------------------------


class Phase(models.Model):
    developer = models.ForeignKey(
        DeveloperProfile,
        on_delete=models.CASCADE,
        related_name="phases",
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="phases",
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.CASCADE,
        related_name="phases",
    )
    lane = models.ForeignKey(
        DeveloperLane,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="phases",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    effort_multiplier = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )

    class Meta:
        ordering = ["start_date"]
        indexes = [
            models.Index(fields=["developer", "semester"]),
            models.Index(fields=["start_date", "end_date"]),
            models.Index(fields=["lane", "start_date", "end_date"]),
        ]

    def clean(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": _("End date must not be before start date.")})

    def save(self, *args, **kwargs):
        """Auto-assign a non-overlapping DeveloperLane if lane_id is not yet set."""
        if self.lane_id is None and self.developer_id and self.semester_id and self.start_date and self.end_date:
            preferred, _ = DeveloperLane.objects.get_or_create(
                developer_id=self.developer_id,
                semester_id=self.semester_id,
                order=0,
            )
            self.lane = _find_or_create_non_overlapping_lane(
                self.developer,
                self.semester,
                self.start_date,
                self.end_date,
                preferred,
                exclude_phase_pk=self.pk or None,
            )
        super().save(*args, **kwargs)

    def effort_weeks(self) -> float:
        """Effort in weeks, excluding developer leave days (5 work days = 1 week)."""
        work_days = 0
        day = self.start_date
        while day <= self.end_date:
            if day.weekday() < 5:  # Mon-Fri
                work_days += 1
            day += datetime.timedelta(days=1)
        for leave in self.developer.leave_periods.filter(
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        ):
            day = max(leave.start_date, self.start_date)
            end = min(leave.end_date, self.end_date)
            while day <= end:
                if day.weekday() < 5:
                    work_days -= 1
                day += datetime.timedelta(days=1)
        return round(max(0, work_days) / 5 * self.effort_multiplier, 2)

    def __str__(self):
        return f"{self.developer} on {self.project} ({self.semester})"


# ---------------------------------------------------------------------------
# Lane-management helpers  (used by Phase.save() and views)
# ---------------------------------------------------------------------------


def _next_lane_order(developer: DeveloperProfile, semester: Semester) -> int:
    max_order = DeveloperLane.objects.filter(
        developer=developer, semester=semester,
    ).aggregate(Max("order"))["order__max"]
    return (max_order + 1) if max_order is not None else 0


def _find_or_create_non_overlapping_lane(
    developer: DeveloperProfile,
    semester: Semester,
    start_date: datetime.date,
    end_date: datetime.date,
    preferred_lane: DeveloperLane,
    exclude_phase_pk=None,
) -> DeveloperLane:
    """Return ``preferred_lane`` if no phase in it overlaps [start_date, end_date].
    Otherwise try each of the developer's lanes in order; if all overlap, create
    a new lane at max_order+1.
    """
    def has_overlap(lane):
        qs = Phase.objects.filter(
            lane=lane, start_date__lte=end_date, end_date__gte=start_date,
        )
        if exclude_phase_pk:
            qs = qs.exclude(pk=exclude_phase_pk)
        return qs.exists()

    if not has_overlap(preferred_lane):
        return preferred_lane

    for lane in DeveloperLane.objects.filter(
        developer=developer, semester=semester,
    ).exclude(pk=preferred_lane.pk).order_by("order", "pk"):
        if not has_overlap(lane):
            return lane

    return DeveloperLane.objects.create(
        developer=developer, semester=semester, order=_next_lane_order(developer, semester),
    )


def _create_next_lane(developer: DeveloperProfile, semester: Semester) -> DeveloperLane:
    """Create a new DeveloperLane with order = max_order + 1."""
    return DeveloperLane.objects.create(
        developer=developer, semester=semester, order=_next_lane_order(developer, semester),
    )


def _delete_empty_lane(lane):
    """Delete the lane if it now has no phases."""
    if lane is None:
        return
    if not lane.phases.exists():
        lane.delete()
