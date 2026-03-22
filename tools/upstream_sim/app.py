from __future__ import annotations

import asyncio

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

app = FastAPI(title="Upstream Simulator")
app.state.flaky_failures = {}


@app.get("/ok")
async def ok(name: str = "world") -> dict[str, str]:
    return {"message": f"hello {name}"}


@app.get("/slow")
async def slow(delay: float = Query(default=2.0, ge=0.0, le=10.0)) -> dict[str, float | str]:
    await asyncio.sleep(delay)
    return {"status": "ok", "delay": delay}


@app.get("/err500")
async def err500() -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "simulated_500"})


@app.get("/err429")
async def err429() -> JSONResponse:
    return JSONResponse(
        status_code=429,
        headers={"Retry-After": "30"},
        content={"detail": "simulated_429"},
    )


@app.get("/flaky")
async def flaky(
    key: str = "default",
    failures: int = Query(default=1, ge=0, le=10),
) -> JSONResponse | dict[str, str]:
    remaining = app.state.flaky_failures.get(key)
    if remaining is None:
        remaining = failures
    if remaining > 0:
        app.state.flaky_failures[key] = remaining - 1
        return JSONResponse(
            status_code=500,
            content={"detail": "simulated_flaky_failure", "remaining_failures": remaining - 1},
        )
    return {"status": "ok", "key": key}
