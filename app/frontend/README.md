# ScanScribe web UI (React)

Production UI is bundled with Vite and served by FastAPI at **`/app/`** (see `app/main.py`). Client router basename: **`/app`**.

## Develop

```bash
cd app/frontend
npm ci
npm run dev
```

Vite proxies `/api` to `http://localhost:8000` — run the API separately.

## Production build (embedded in Docker / local uvicorn)

```bash
cd app/frontend
npm ci
npm run build
```

Output: `app/frontend/dist/`. If `index.html` is missing, `/app/*` returns **503** with a build hint.

## Quality

```bash
npm run typecheck
npm run lint
npm run test
```

Legacy Jinja + static file UI lives under **`archive/legacy-ui/`** (not deployed).
