# Vercel deployment model

The demo is deployed as one FastAPI application.

- `index.py` is the Vercel entrypoint.
- `vercel.json` forces the `fastapi` framework preset.
- Vercel runs `npm ci && npm run build` before packaging the Python application.
- `backend/app/main.py` serves `/api/*`, compiled Vite assets and the React SPA fallback.
- No Vercel environment variable or dashboard build override is required.

This model deliberately avoids a separate Vite routing table and Python function route, which previously caused `/api/processings` to return a platform 404.
