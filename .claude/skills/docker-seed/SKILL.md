---
name: docker-seed
description: Rebuild the Django Docker image, restart the container, and seed the database with test data
disable-model-invocation: true
allowed-tools: Bash
---

Run the following commands in sequence:

```bash
docker compose build django nginx && docker compose up -d django nginx && docker compose exec django poetry run python manage.py seed_test_data --clear --settings=config.settings.docker_dev
```

Report when seeding is complete.
