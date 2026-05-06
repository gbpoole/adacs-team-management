"""
Settings for local Docker development.
Extends prod settings but permits seed_test_data.
Never use this settings module in a real production deployment.
"""

from .prod import *  # noqa: F403

SEED_DATA_ALLOWED = True
