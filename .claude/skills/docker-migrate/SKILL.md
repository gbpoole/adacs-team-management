---
name: docker-migrate
description: Run Django database migrations inside the Docker container
disable-model-invocation: true
allowed-tools: Bash
---

Run migrations inside the running Django container:

```bash
docker compose exec django poetry run python manage.py migrate
```

Report on the migrations that were applied.
