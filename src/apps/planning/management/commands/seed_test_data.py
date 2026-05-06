"""
Management command to populate the database with realistic test data.

Seed data is driven by TSV files in src/data/seed/:
  developers.tsv  — columns: email, name, organisation, effort_available, tags
  projects.tsv    — columns: name, streams (comma-sep), tags
  observers.tsv   — columns: email, name, organisation, project_access (comma-sep project names)

Random phases and leave periods are generated on top of that fixed data.

Usage:
    python manage.py seed_test_data
    python manage.py seed_test_data --clear  # wipe planning data first
"""

import csv
import datetime
import io
import random
from pathlib import Path

from django.conf import settings

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from apps.planning.models import DeveloperProfile
from apps.planning.models import Leave
from apps.planning.models import Phase
from apps.planning.models import Project
from apps.planning.models import ProjectAllocation
from apps.planning.models import Semester
from apps.planning.models import SemesterDeveloper
from apps.planning.models import SemesterObserver
from apps.planning.models import SemesterType
from apps.planning.models import Stream
from apps.planning.models import Tag
from apps.planning.models import UserProjectAccess
from apps.planning.views._csv_import import _validate_developer_rows
from apps.planning.views._csv_import import _validate_observer_rows
from apps.planning.views._csv_import import _validate_project_rows
from apps.users.models import Role

User = get_user_model()

# src/data/seed/ relative to this file (src/apps/planning/management/commands/)
DATA_DIR = Path(__file__).parents[4] / "data" / "seed"

# ── Seed constants ────────────────────────────────────────────────────────────
DEFAULT_EFFORT_WEEKS = 20
ALLOCATION_WEEK_OPTIONS = [10, 15, 20, 25, 30]
MAX_LEAVE_DEVELOPERS = 6
MAX_PHASE_PROJECTS = 10
PHASES_PER_DEVELOPER_RANGE = (2, 5)
PHASE_OFFSET_WEEKS_RANGE = (0, 10)
PHASE_DURATION_WEEKS_RANGE = (3, 10)
EFFORT_MULTIPLIER_WEIGHTS = [0.5, 1.0, 1.0, 1.0]


def _read_tsv(path):
    """Return a list of dicts from a tab-separated file with a header row."""
    return list(
        csv.DictReader(
            io.StringIO(Path(path).read_text(encoding="utf-8-sig")), delimiter="\t",
        ),
    )


def _get_or_create_tags(names):
    return [Tag.objects.get_or_create(name=n)[0] for n in names if n.strip()]


def _get_or_create_streams(names):
    return [Stream.objects.get_or_create(name=n)[0] for n in names if n.strip()]


class Command(BaseCommand):
    help = "Seed the database with test data for development"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing planning data before seeding",
        )

    def handle(self, *args, **options):
        if not getattr(settings, "SEED_DATA_ALLOWED", False):
            raise CommandError(
                "seed_test_data refuses to run unless SEED_DATA_ALLOWED = True "
                "in settings. This command is for development and testing only."
            )
        with transaction.atomic():
            self._seed(*args, **options)

    def _seed(self, *args, **options):
        # ── Validate all files before touching the DB ─────────────────────────
        dev_rows = _read_tsv(DATA_DIR / "developers.tsv")
        proj_rows = _read_tsv(DATA_DIR / "projects.tsv")
        obs_rows = _read_tsv(DATA_DIR / "observers.tsv")

        # Build the set of project names from the projects file for observer validation.
        proj_names = {
            r.get("name", "").strip() for r in proj_rows if r.get("name", "").strip()
        }
        all_errors = (
            [f"developers.tsv — {e}" for e in _validate_developer_rows(dev_rows)]
            + [f"projects.tsv — {e}" for e in _validate_project_rows(proj_rows)]
            + [
                f"observers.tsv — {e}"
                for e in _validate_observer_rows(obs_rows, proj_names)
            ]
        )
        if all_errors:
            raise CommandError(
                "Seed data validation failed:\n"
                + "\n".join(f"  • {e}" for e in all_errors),
            )

        if options["clear"]:
            self.stdout.write("Clearing existing planning data...")
            Phase.objects.all().delete()
            Leave.objects.all().delete()
            SemesterDeveloper.objects.all().delete()
            ProjectAllocation.objects.all().delete()
            SemesterObserver.objects.all().delete()
            UserProjectAccess.objects.all().delete()
            DeveloperProfile.objects.all().delete()
            Project.objects.all().delete()
            Stream.objects.all().delete()
            Tag.objects.all().delete()
            Semester.objects.all().delete()
            User.objects.filter(role__in=[Role.USER, Role.PM]).delete()

        self.stdout.write("Creating fixed seed accounts...")
        self._create_seed_account(
            "pm@adacs.org.au",
            "PM User",
            Role.PM,
            "testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self._create_seed_account(
            "developer@adacs.org.au", "Developer User", Role.USER, "testpass123",
        )
        observer_user = self._create_seed_account(
            "observer@adacs.org.au", "Observer User", Role.USER, "testpass123",
        )

        self.stdout.write("Creating semesters...")
        seed_year = datetime.date.today().year
        sem_a = self._get_or_create_semester(seed_year, SemesterType.A)
        sem_b = self._get_or_create_semester(seed_year, SemesterType.B)

        # ── Developers ────────────────────────────────────────────────────────
        self.stdout.write(f"Loading developers from {DATA_DIR / 'developers.tsv'} ...")
        dev_profiles = []
        for row in dev_rows:
            email = row.get("email", "").strip()
            if not email:
                continue
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "name": row.get("name", "").strip(),
                    "role": Role.USER,
                    "organisation": row.get("organisation", "").strip(),
                },
            )
            if created:
                user.set_password("testpass123")
                user.save()
            profile, _ = DeveloperProfile.objects.get_or_create(user=user)
            tag_names = [
                t.strip() for t in (row.get("tags") or "").split("||") if t.strip()
            ]
            if tag_names:
                profile.tags.set(_get_or_create_tags(tag_names))
            effort_str = row.get("effort_available", "").strip()
            effort = float(effort_str) if effort_str else DEFAULT_EFFORT_WEEKS
            profile.base_effort_weeks = effort
            profile.save()
            base_tags = list(profile.tags.all())
            for i, sem in enumerate([sem_a, sem_b]):
                sd, _ = SemesterDeveloper.objects.get_or_create(
                    developer=profile,
                    semester=sem,
                    defaults={"effort_available": effort},
                )
                if i == 0:
                    # sem_a: exact copy of base tags
                    sd.tags.set(base_tags)
                else:
                    # sem_b: slight variation — maybe drop one, maybe add one
                    sem_tags = list(base_tags)
                    if len(sem_tags) > 1 and random.random() < 0.5:
                        sem_tags.remove(random.choice(sem_tags))
                    extras = [t for t in Tag.objects.all() if t not in sem_tags]
                    if extras and random.random() < 0.5:
                        sem_tags.append(random.choice(extras))
                    sd.tags.set(sem_tags)
            dev_profiles.append(profile)
        self.stdout.write(f"  {len(dev_profiles)} developers loaded.")

        # ── Projects ──────────────────────────────────────────────────────────
        # Each project row creates two independent Project instances (one per semester),
        # linked via continuation_of so sem_b continues from sem_a.
        self.stdout.write(f"Loading projects from {DATA_DIR / 'projects.tsv'} ...")
        projects_by_sem = {sem_a: [], sem_b: []}
        for row in proj_rows:
            name = row.get("name", "").strip()
            if not name:
                continue
            stream_names = [
                s.strip() for s in (row.get("streams") or "").split("||") if s.strip()
            ]
            tag_names = [
                t.strip() for t in (row.get("tags") or "").split("||") if t.strip()
            ]
            streams = _get_or_create_streams(stream_names)
            tags = _get_or_create_tags(tag_names)

            proj_a, created_a = Project.objects.get_or_create(
                name=name, semester=sem_a,
            )
            proj_a.streams.set(streams)
            if tags:
                proj_a.tags.set(tags)
            ProjectAllocation.objects.get_or_create(
                project=proj_a,
                semester=sem_a,
                defaults={
                    "weeks_new": random.choice(ALLOCATION_WEEK_OPTIONS),
                    "weeks_carryover": 0,
                },
            )
            projects_by_sem[sem_a].append(proj_a)

            proj_b, created_b = Project.objects.get_or_create(
                name=name, semester=sem_b,
                defaults={"continuation_of": proj_a},
            )
            if not proj_b.continuation_of:
                proj_b.continuation_of = proj_a
                proj_b.save(update_fields=["continuation_of"])
            proj_b.streams.set(streams)
            if tags:
                proj_b.tags.set(tags)
            ProjectAllocation.objects.get_or_create(
                project=proj_b,
                semester=sem_b,
                defaults={
                    "weeks_new": random.choice(ALLOCATION_WEEK_OPTIONS),
                    "weeks_carryover": 0,
                },
            )
            projects_by_sem[sem_b].append(proj_b)

        projects = projects_by_sem[sem_a] + projects_by_sem[sem_b]
        self.stdout.write(f"  {len(projects_by_sem[sem_a])} projects loaded (x2 semesters).")

        # Give the fixed observer account access to the first few sem_a projects
        if projects_by_sem[sem_a]:
            observer_access, _ = UserProjectAccess.objects.get_or_create(user=observer_user)
            observer_access.project_access.set(projects_by_sem[sem_a][:3])

        # ── Observers ─────────────────────────────────────────────────────────
        self.stdout.write(f"Loading observers from {DATA_DIR / 'observers.tsv'} ...")
        obs_count = 0
        # Build a name→project lookup for project_access resolution (use sem_a instances)
        project_by_name = {p.name: p for p in projects_by_sem[sem_a]}

        for row in obs_rows:
            email = row.get("email", "").strip()
            if not email:
                continue
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "name": row.get("name", "").strip(),
                    "role": Role.USER,
                    "organisation": row.get("organisation", "").strip(),
                },
            )
            if created:
                user.set_password("testpass123")
                user.save()
            access_names = [
                n.strip() for n in row.get("project_access", "").split("||") if n.strip()
            ]
            access_projects = [
                project_by_name[n] for n in access_names if n in project_by_name
            ]
            stream_names = [
                n.strip()
                for n in (row.get("stream_access") or "").split("||")
                if n.strip()
            ]
            access_streams = list(Stream.objects.filter(name__in=stream_names))
            access, _ = UserProjectAccess.objects.get_or_create(user=user)
            if access_projects:
                access.project_access.set(access_projects)
            if access_streams:
                access.stream_access.set(access_streams)
            obs_count += 1
        self.stdout.write(f"  {obs_count} observers loaded.")

        # ── Leave ─────────────────────────────────────────────────────────────
        self.stdout.write("Generating leave periods...")
        leave_count = 0
        for profile in random.sample(
            dev_profiles, k=min(MAX_LEAVE_DEVELOPERS, len(dev_profiles)),
        ):
            start = datetime.date(
                2026, random.randint(1, 10), random.choice([1, 8, 15, 22]),
            )
            end = start + datetime.timedelta(days=random.choice([4, 7, 9, 14]))
            Leave.objects.get_or_create(
                developer=profile, start_date=start, defaults={"end_date": end},
            )
            leave_count += 1

        # ── Phases ────────────────────────────────────────────────────────────
        self.stdout.write("Generating phases...")
        phase_count = 0
        sem_project_pairs = []
        for sem, sem_projects in [(sem_a, projects_by_sem[sem_a]), (sem_b, projects_by_sem[sem_b])]:
            for project in random.sample(
                sem_projects, k=min(MAX_PHASE_PROJECTS, len(sem_projects)),
            ):
                sem_project_pairs.append((sem, project))

        for profile in dev_profiles:
            pairs = random.sample(
                sem_project_pairs, k=random.randint(*PHASES_PER_DEVELOPER_RANGE),
            )
            for sem, project in pairs:
                offset_weeks = random.randint(*PHASE_OFFSET_WEEKS_RANGE)
                duration_weeks = random.randint(*PHASE_DURATION_WEEKS_RANGE)
                start = sem.start_date + datetime.timedelta(weeks=offset_weeks)
                end = min(
                    start
                    + datetime.timedelta(weeks=duration_weeks)
                    - datetime.timedelta(days=1),
                    sem.end_date,
                )
                multiplier = random.choice(EFFORT_MULTIPLIER_WEIGHTS)
                Phase.objects.get_or_create(
                    developer=profile,
                    project=project,
                    semester=sem,
                    start_date=start,
                    defaults={"end_date": end, "effort_multiplier": multiplier},
                )
                phase_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {len(dev_profiles)} developers, {len(projects)} projects, "
                f"{obs_count} observers, 2 semesters, {leave_count} leave periods, {phase_count} phases.",
            ),
        )

    def _create_seed_account(
        self, email, name, role, password, is_staff=False, is_superuser=False,
    ):
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "name": name,
                "role": role,
                "organisation": "ADACS",
                "is_staff": is_staff,
                "is_superuser": is_superuser,
            },
        )
        if created:
            user.set_password(password)
            user.save()
        EmailAddress.objects.get_or_create(
            user=user,
            email=email,
            defaults={"primary": True, "verified": True},
        )
        self.stdout.write(f"  {role} account: {email} / {password}")
        return user

    def _get_or_create_semester(self, year, semester_type):
        sem, created = Semester.objects.get_or_create(
            year=year, semester_type=semester_type,
        )
        if created:
            self.stdout.write(f"  Created {sem}")
        return sem
