---
name: docker-rebuild
description: Rebuild the Django Docker image and restart the container after source code changes
disable-model-invocation: true
allowed-tools: Bash
---

Run the following command to rebuild the Django Docker image and restart it:

```bash
docker compose build django && docker compose up -d django
```

Report when the container is back up.
