import asyncio
from pathlib import Path
import random
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(
    title="Chaos Target Simulator",
    description="Mock target API for simulating real-world network and service anomalies",
    version="1.0.0",
)


@app.get("/health", status_code=status.HTTP_200_OK)
async def health(spike_ms: int = 0):
    """
    Sleeps 20-50ms and returns 200 OK.
    If spike_ms > 0, injects a controlled latency spike to test ML anomaly detection.
    """
    if spike_ms > 0:
        delay = spike_ms / 1000.0
    else:
        delay = random.uniform(0.02, 0.05)
    await asyncio.sleep(delay)
    return {
        "status": "healthy",
        "message": "Service is operating normally",
        "injected_spike": spike_ms > 0,
        "latency_ms": round(delay * 1000, 2),
    }


@app.get("/flaky")
async def flaky():
    """Returns 500 Internal Server Error 30% of the time, otherwise 200 OK."""
    if random.random() < 0.30:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Simulated internal server error (30% failure rate)",
        )
    return {"status": "ok", "message": "Flaky service call succeeded"}


@app.get("/latent-spike")
async def latent_spike():
    """
    Sleeps 400-800ms 40% of the time (simulating silent latency degradation while still returning 200 OK),
    otherwise 30-60ms.
    """
    if random.random() < 0.40:
        delay = random.uniform(0.40, 0.80)
        is_spike = True
    else:
        delay = random.uniform(0.03, 0.06)
        is_spike = False

    await asyncio.sleep(delay)
    return {
        "status": "ok",
        "latency_spike": is_spike,
        "latency_ms": round(delay * 1000, 2),
    }


@app.get("/rate-limited")
async def rate_limited():
    """Returns 429 Too Many Requests 50% of the time, otherwise 200 OK."""
    if random.random() < 0.50:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": "Too Many Requests",
                "message": "Simulated rate limit exceeded. Retry later.",
            },
            headers={"Retry-After": "60"},
        )
    return {"status": "ok", "message": "Request allowed within rate limit"}


@app.get("/down")
async def down():
    """Always returns 503 Service Unavailable simulating a hard service outage."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database connection pool exhausted",
    )


if __name__ == "__main__":
    target = "mock_server.main:app" if Path("mock_server").exists() else "main:app"
    uvicorn.run(target, host="0.0.0.0", port=9000, reload=True)

