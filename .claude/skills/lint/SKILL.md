---
name: lint
description: Run the ruff linter over the planning app source code
allowed-tools: Bash
---

Run ruff:

```bash
poetry run ruff check src/apps/
```

Report any linting errors found.
