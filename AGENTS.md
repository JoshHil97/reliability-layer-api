# AGENTS.md — Reliability Layer API

## Working Agreements
- Prefer small, reviewable milestones and keep tests close to the behavior they prove.
- Always run `ruff check .` and `python -m pytest -q` after code changes.
- Keep the FastAPI app async and reuse a single shared `httpx.AsyncClient`.
- All outbound calls must use explicit connect/read/write/pool timeouts and bounded retries.
- Do not turn the proxy into an open proxy. Only configured upstreams are reachable.

## Commands
- Dev stack: `docker compose -f deployments/docker/docker-compose.yml up --build`
- Tests: `python -m pytest -q`
- Lint: `ruff check .`
- Format check: `ruff format --check .`

## Definition Of Done
- Requested files exist and the app starts locally.
- Unit tests cover new core logic.
- Integration tests cover externally visible behavior changes.
- `ruff check .` and `python -m pytest -q` pass.

