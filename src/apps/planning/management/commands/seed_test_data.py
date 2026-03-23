"""
Management command to populate the database with realistic test data:
  - 13 developers
  - 27 projects
  - 2 observers
  - 2 semesters (2026A, 2026B) with allocations

Usage:
    python manage.py seed_test_data
    python manage.py seed_test_data --clear  # wipe planning data first
"""
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.planning.models import AllocationType
from apps.planning.models import DeveloperProfile
from apps.planning.models import ObserverProfile
from apps.planning.models import Project
from apps.planning.models import ProjectAllocation
from apps.planning.models import ProjectSemesterName
from apps.planning.models import Semester
from apps.planning.models import SemesterDeveloper
from apps.planning.models import SemesterType
from apps.planning.models import Stream
from apps.planning.models import Tag
from apps.users.models import Role

User = get_user_model()

DEVELOPER_DATA = [
    ("Alice Nguyen", "alice@adacs.org.au", "🐍"),
    ("Ben Carter", "ben@adacs.org.au", "🦀"),
    ("Carmen Silva", "carmen@adacs.org.au", "🌟"),
    ("David Kim", "david@adacs.org.au", "🔭"),
    ("Elena Vasquez", "elena@adacs.org.au", "🧪"),
    ("Finn O'Brien", "finn@adacs.org.au", "🌊"),
    ("Grace Liu", "grace@adacs.org.au", "🎯"),
    ("Hamid Rahimi", "hamid@adacs.org.au", "⚡"),
    ("Isla MacLeod", "isla@adacs.org.au", "🌿"),
    ("James Okafor", "james@adacs.org.au", "🚀"),
    ("Keiko Tanaka", "keiko@adacs.org.au", "🎌"),
    ("Luca Rossi", "luca@adacs.org.au", "🍕"),
    ("Maya Patel", "maya@adacs.org.au", "🧬"),
]

OBSERVER_DATA = [
    ("Prof. Sarah Chen", "sarah.chen@uni.edu.au", "Monash University"),
    ("Dr. Mark Williams", "mark.williams@anu.edu.au", "ANU"),
]

STREAMS = ["Astronomy", "Bioinformatics", "Climate Science", "Geoscience", "Physics"]

TAGS = [
    "python",
    "hpc",
    "data-pipeline",
    "visualisation",
    "gpu",
    "ml",
    "web",
    "devops",
    "database",
    "api",
]

PROJECT_NAMES = [
    "GALAH Stellar Spectra Pipeline",
    "SKA Precursor Data Processing",
    "OzGrav Gravitational Wave Analysis",
    "TAIPAN Survey Tools",
    "4MOST Targeting Software",
    "ASKAP Continuum Imaging",
    "MWA Calibration Framework",
    "NCI Data Portal",
    "Galaxy Zoo ML Classifier",
    "Exoplanet Transit Detector",
    "Microbiome Assembly Pipeline",
    "Protein Folding Database",
    "Climate Model Post-Processing",
    "BOM Data Ingestion Framework",
    "ACCESS Climate Portal",
    "Seismic Event Classifier",
    "Geodynamics Simulation Tools",
    "CubeSat Telemetry Dashboard",
    "Dark Matter Map Generator",
    "Radio Transient Finder",
    "Pulsar Timing Array Tools",
    "Next-Gen Spectrograph Control",
    "ATNF Catalogue Updater",
    "Biobank Data QC Pipeline",
    "Phylogenomics Workflow",
    "Coral Reef Monitoring Dashboard",
    "Antarctic Ice Core Analysis",
]


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
        if options["clear"]:
            self.stdout.write("Clearing existing planning data...")
            SemesterDeveloper.objects.all().delete()
            ProjectAllocation.objects.all().delete()
            ProjectSemesterName.objects.all().delete()
            ObserverProfile.objects.all().delete()
            DeveloperProfile.objects.all().delete()
            Project.objects.all().delete()
            Stream.objects.all().delete()
            Tag.objects.all().delete()
            Semester.objects.all().delete()
            User.objects.filter(
                role__in=[Role.DEVELOPER, Role.OBSERVER],
            ).delete()

        self.stdout.write("Creating semesters...")
        sem_a = self._get_or_create_semester(2026, SemesterType.A)
        sem_b = self._get_or_create_semester(2026, SemesterType.B)

        self.stdout.write("Creating tags...")
        tags = [Tag.objects.get_or_create(name=t)[0] for t in TAGS]

        self.stdout.write("Creating streams...")
        streams = [Stream.objects.get_or_create(name=s)[0] for s in STREAMS]

        self.stdout.write("Creating 13 developers...")
        dev_profiles = []
        for name, email, emoji in DEVELOPER_DATA:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "name": name,
                    "role": Role.DEVELOPER,
                    "organisation": "ADACS",
                    "emoji": emoji,
                },
            )
            if created:
                user.set_password("testpass123")
                user.save()
            profile, _ = DeveloperProfile.objects.get_or_create(user=user)
            # Assign 2-3 random tags
            profile.tags.set(random.sample(tags, k=random.randint(2, 3)))
            dev_profiles.append(profile)
            # Effort available: 26 weeks A semester, 26 weeks B semester
            SemesterDeveloper.objects.get_or_create(
                developer=profile,
                semester=sem_a,
                defaults={"effort_available": 26},
            )
            SemesterDeveloper.objects.get_or_create(
                developer=profile,
                semester=sem_b,
                defaults={"effort_available": 26},
            )

        self.stdout.write("Creating 27 projects...")
        projects = []
        for name in PROJECT_NAMES:
            project, _ = Project.objects.get_or_create(
                stream=random.choice(streams),
                defaults={},
            )
            # Set a unique name per semester
            ProjectSemesterName.objects.get_or_create(
                project=project,
                semester=sem_a,
                defaults={"name": name},
            )
            ProjectSemesterName.objects.get_or_create(
                project=project,
                semester=sem_b,
                defaults={"name": name},
            )
            # Assign 1-2 random tags
            project.tags.set(random.sample(tags, k=random.randint(1, 2)))
            # Allocation: 10-30 weeks each semester
            for sem in [sem_a, sem_b]:
                ProjectAllocation.objects.get_or_create(
                    project=project,
                    semester=sem,
                    defaults={
                        "allocation_type": AllocationType.FIXED,
                        "weeks_new": random.choice([10, 15, 20, 25, 30]),
                        "weeks_carryover": 0,
                    },
                )
            projects.append(project)

        self.stdout.write("Creating 2 observers...")
        for name, email, org in OBSERVER_DATA:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "name": name,
                    "role": Role.OBSERVER,
                    "organisation": org,
                },
            )
            if created:
                user.set_password("testpass123")
                user.save()
            obs, _ = ObserverProfile.objects.get_or_create(user=user)
            # Give each observer access to a random subset of projects
            obs.project_access.set(random.sample(projects, k=random.randint(3, 8)))

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {len(dev_profiles)} developers, {len(projects)} projects, "
                f"2 observers, 2 semesters.",
            ),
        )

    def _get_or_create_semester(self, year, semester_type):
        sem, created = Semester.objects.get_or_create(
            year=year, semester_type=semester_type,
        )
        if created:
            self.stdout.write(f"  Created {sem}")
        return sem
