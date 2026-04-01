---
name: docker-up
description: Start all Docker Compose services (Django, MySQL, nginx, mailpit, cron)
disable-model-invocation: true
allowed-tools: Bash
---

Start all services in detached mode:

```bash
docker compose up -d
```

Report which services are running.
