---
name: docker-logs
description: Tail the Django container logs
disable-model-invocation: true
allowed-tools: Bash
---

Stream the Django container logs:

```bash
docker compose logs -f django
```
