# Ops console

Minimal React console (calls, eval reports, feedback). Paste an admin token
(mint via `POST /v1/admin/tokens` with `X-Admin-Key`) to load data.
API base is same-origin `/v1` (proxied to `vaani-app:8080` in Docker).

```bash
cd ops-console && npm install && npm run test:run && npm run build
```
