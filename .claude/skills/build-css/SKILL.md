---
name: build-css
description: Build Tailwind CSS; pass 'dev' for watch mode, otherwise builds minified production CSS
argument-hint: [dev]
disable-model-invocation: true
allowed-tools: Bash
---

If $ARGUMENTS is "dev", run:

```bash
npm run dev
```

Otherwise, run the production build:

```bash
npm run build
```

Report when the build is complete and where the output file was written (`src/apps/static/css/dist/styles.css`).
