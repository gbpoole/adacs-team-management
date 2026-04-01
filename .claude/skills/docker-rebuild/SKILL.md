---
name: docker-rebuild
description: Rebuild the Django Docker image and restart the container after source code changes
disable-model-invocation: true
allowed-tools: Bash
---

Run the following commands to rebuild both the Django and Nginx Docker images and restart them:

```bash
docker compose build django nginx && docker compose up -d django nginx
```

Both services must be rebuilt together: `django` runs the app and `nginx` serves the compiled static files (CSS/JS). Rebuilding only `django` leaves nginx serving a stale CSS file with a different content hash, causing all styles to 404.

Report when the containers are back up.
