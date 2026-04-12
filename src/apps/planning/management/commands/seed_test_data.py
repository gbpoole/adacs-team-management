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

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from apps.planning.models import AllocationType
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
from apps.planning.views._csv_import import _validate_developer_rows
from apps.planning.views._csv_import import _validate_observer_rows
from apps.planning.views._csv_import import _validate_project_rows
from apps.users.models import Role

User = get_user_model()

# src/data/seed/ relative to this file (src/apps/planning/management/commands/)
DATA_DIR = Path(__file__).parents[4] / "data" / "seed"

# ── Seed constants ────────────────────────────────────────────────────────────
DEFAULT_EFFORT_WEEKS = 26
ALLOCATION_WEEK_OPTIONS = [10, 15, 20, 25, 30]
MAX_LEAVE_DEVELOPERS = 6
MAX_PHASE_PROJECTS = 10
PHASES_PER_DEVELOPER_RANGE = (2, 5)
PHASE_OFFSET_WEEKS_RANGE = (0, 10)
PHASE_DURATION_WEEKS_RANGE = (3, 10)
EFFORT_MULTIPLIER_WEIGHTS = [0.5, 1.0, 1.0, 1.0]


def _read_tsv(path):
    """Return a list of dicts from a tab-separated file with a header row."""
    return list(csv.DictReader(io.StringIO(Path(path).read_text(encoding="utf-8-sig")), delimiter="\t"))


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

    @transaction.atomic
    def handle(self, *args, **options):
        # ── Validate all files before touching the DB ─────────────────────────
        dev_rows = _read_tsv(DATA_DIR / "developers.tsv")
        proj_rows = _read_tsv(DATA_DIR / "projects.tsv")
        obs_rows = _read_tsv(DATA_DIR / "observers.tsv")

        # Build the set of project names from the projects file for observer validation.
        proj_names = {r.get("name", "").strip() for r in proj_rows if r.get("name", "").strip()}
        all_errors = (
            [f"developers.tsv — {e}" for e in _validate_developer_rows(dev_rows)]
            + [f"projects.tsv — {e}" for e in _validate_project_rows(proj_rows)]
            + [f"observers.tsv — {e}" for e in _validate_observer_rows(obs_rows, proj_names)]
        )
        if all_errors:
            raise CommandError("Seed data validation failed:\n" + "\n".join(f"  • {e}" for e in all_errors))

        if options["clear"]:
            self.stdout.write("Clearing existing planning data...")
            Phase.objects.all().delete()
            Leave.objects.all().delete()
            SemesterDeveloper.objects.all().delete()
            ProjectAllocation.objects.all().delete()
            ProjectSemesterName.objects.all().delete()
            ObserverProfile.objects.all().delete()
            DeveloperProfile.objects.all().delete()
            Project.objects.all().delete()
            Stream.objects.all().delete()
            Tag.objects.all().delete()
            Semester.objects.all().delete()
            User.objects.filter(role__in=[Role.DEVELOPER, Role.OBSERVER]).delete()

        self.stdout.write("Creating fixed seed accounts...")
        self._create_seed_account("pm@adacs.org.au", "PM User", Role.PM, "pm1234", is_staff=True, is_superuser=True)
        self._create_seed_account("pm2@adacs.org.au", "PM User 2", Role.PM, "pm1234")
        self._create_seed_account("developer@adacs.org.au", "Developer User", Role.DEVELOPER, "developer1234")

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
                    "role": Role.DEVELOPER,
                    "organisation": row.get("organisation", "").strip(),
                },
            )
            if created:
                user.set_password("testpass123")
                user.save()
            profile, _ = DeveloperProfile.objects.get_or_create(user=user)
            tag_names = [t.strip() for t in (row.get("tags") or "").split(",") if t.strip()]
            if tag_names:
                profile.tags.set(_get_or_create_tags(tag_names))
            effort_str = row.get("effort_available", "").strip()
            effort = float(effort_str) if effort_str else DEFAULT_EFFORT_WEEKS
            for sem in [sem_a, sem_b]:
                SemesterDeveloper.objects.get_or_create(
                    developer=profile, semester=sem,
                    defaults={"effort_available": effort},
                )
            dev_profiles.append(profile)
        self.stdout.write(f"  {len(dev_profiles)} developers loaded.")

        # ── Projects ──────────────────────────────────────────────────────────
        self.stdout.write(f"Loading projects from {DATA_DIR / 'projects.tsv'} ...")
        projects = []
        for row in proj_rows:
            name = row.get("name", "").strip()
            if not name:
                continue
            existing = ProjectSemesterName.objects.filter(name=name, semester__in=[sem_a, sem_b]).first()
            if existing:
                project = existing.project
            else:
                project = Project()
                project.save()
                ProjectSemesterName.objects.get_or_create(project=project, semester=sem_a, defaults={"name": name})
                ProjectSemesterName.objects.get_or_create(project=project, semester=sem_b, defaults={"name": name})
            stream_names = [s.strip() for s in (row.get("streams") or "").split(",") if s.strip()]
            project.streams.set(_get_or_create_streams(stream_names))
            tag_names = [t.strip() for t in (row.get("tags") or "").split(",") if t.strip()]
            if tag_names:
                project.tags.set(_get_or_create_tags(tag_names))
            for sem in [sem_a, sem_b]:
                ProjectAllocation.objects.get_or_create(
                    project=project, semester=sem,
                    defaults={
                        "allocation_type": AllocationType.FIXED,
                        "weeks_new": random.choice(ALLOCATION_WEEK_OPTIONS),
                        "weeks_carryover": 0,
                    },
                )
            projects.append(project)
        self.stdout.write(f"  {len(projects)} projects loaded.")

        # ── Observers ─────────────────────────────────────────────────────────
        self.stdout.write(f"Loading observers from {DATA_DIR / 'observers.tsv'} ...")
        obs_count = 0
        # Build a name→project lookup for project_access resolution
        project_by_name = {}
        for p in projects:
            for psn in p.semester_names.filter(semester__in=[sem_a, sem_b]):
                project_by_name[psn.name] = p

        for row in obs_rows:
            email = row.get("email", "").strip()
            if not email:
                continue
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "name": row.get("name", "").strip(),
                    "role": Role.OBSERVER,
                    "organisation": row.get("organisation", "").strip(),
                },
            )
            if created:
                user.set_password("testpass123")
                user.save()
            obs, _ = ObserverProfile.objects.get_or_create(user=user)
            access_names = [n.strip() for n in row.get("project_access", "").split(",") if n.strip()]
            access_projects = [project_by_name[n] for n in access_names if n in project_by_name]
            if access_projects:
                obs.project_access.set(access_projects)
            obs_count += 1
        self.stdout.write(f"  {obs_count} observers loaded.")

        # ── Leave ─────────────────────────────────────────────────────────────
        self.stdout.write("Generating leave periods...")
        leave_count = 0
        for profile in random.sample(dev_profiles, k=min(MAX_LEAVE_DEVELOPERS, len(dev_profiles))):
            start = datetime.date(2026, random.randint(1, 10), random.choice([1, 8, 15, 22]))
            end = start + datetime.timedelta(days=random.choice([4, 7, 9, 14]))
            Leave.objects.get_or_create(developer=profile, start_date=start, defaults={"end_date": end})
            leave_count += 1

        # ── Phases ────────────────────────────────────────────────────────────
        self.stdout.write("Generating phases...")
        phase_count = 0
        sem_project_pairs = []
        for sem in [sem_a, sem_b]:
            for project in random.sample(projects, k=min(MAX_PHASE_PROJECTS, len(projects))):
                sem_project_pairs.append((sem, project))

        for profile in dev_profiles:
            pairs = random.sample(sem_project_pairs, k=random.randint(*PHASES_PER_DEVELOPER_RANGE))
            for sem, project in pairs:
                offset_weeks = random.randint(*PHASE_OFFSET_WEEKS_RANGE)
                duration_weeks = random.randint(*PHASE_DURATION_WEEKS_RANGE)
                start = sem.start_date + datetime.timedelta(weeks=offset_weeks)
                end = min(start + datetime.timedelta(weeks=duration_weeks) - datetime.timedelta(days=1), sem.end_date)
                multiplier = random.choice(EFFORT_MULTIPLIER_WEIGHTS)
                Phase.objects.get_or_create(
                    developer=profile, project=project, semester=sem, start_date=start,
                    defaults={"end_date": end, "effort_multiplier": multiplier},
                )
                phase_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done: {len(dev_profiles)} developers, {len(projects)} projects, "
            f"{obs_count} observers, 2 semesters, {leave_count} leave periods, {phase_count} phases."
        ))

    def _create_seed_account(self, email, name, role, password, is_staff=False, is_superuser=False):
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
            user=user, email=email,
            defaults={"primary": True, "verified": True},
        )
        self.stdout.write(f"  {role} account: {email} / {password}")
        return user

    def _get_or_create_semester(self, year, semester_type):
        sem, created = Semester.objects.get_or_create(year=year, semester_type=semester_type)
        if created:
            self.stdout.write(f"  Created {sem}")
        return sem
