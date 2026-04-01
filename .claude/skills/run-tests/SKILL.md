---
name: run-tests
description: Run the Django test suite; optionally pass a test path as an argument
argument-hint: [test.path.optional]
allowed-tools: Bash
---

Run the test suite with:

```bash
cd src && DJANGO_SETTINGS_MODULE=config.settings.test poetry run python manage.py test $ARGUMENTS
```

If no argument is provided ($ARGUMENTS is empty), default to `apps.planning tests`.

Report the test results including pass/fail counts and any errors.
