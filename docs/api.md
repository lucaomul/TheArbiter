# API Guide

## Overview

The Arbiter API is a FastAPI layer around the same orchestration engine used by the Streamlit product surface. It is intentionally thin: the service does not invent a second execution path.

Base local URL:

```text
http://localhost:8000
```

Swagger UI:

```text
http://localhost:8000/docs
```

ReDoc:

```text
http://localhost:8000/redoc
```

## Auth Model

Protected routes use `require_api_key`.

Behavior:
- local/dev mode: requests are allowed without an API key
- production mode: if `ARBITER_ENV=production`, protected routes require a valid `x-api-key`

Environment variables:

```env
ARBITER_ENV=production
API_KEY=changeme
```

Header:

```text
x-api-key: <your key>
```

If `ARBITER_ENV=production` and `API_KEY` is missing or invalid, protected routes fail closed.

## Rate-Limit Headers

The API includes groundwork headers for future rate limiting:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

These are currently informational groundwork rather than full enforcement.

## Routes

### GET /api/v1/health

Returns basic service health.

Example:

```bash
curl http://localhost:8000/api/v1/health
```

Example response:

```json
{
  "status": "ok",
  "service": "The Arbiter API",
  "database_enabled": false,
  "detail": "DB dependencies not installed."
}
```

### GET /api/v1/ready

Returns readiness state for accepting runs.

Example response:

```json
{
  "status": "ready",
  "service": "The Arbiter API",
  "database_enabled": true,
  "detail": "Service is ready to accept runs."
}
```

### GET /api/v1/models

Lists currently known models from the plugin registry.

Example:

```bash
curl http://localhost:8000/api/v1/models
```

Example response:

```json
{
  "count": 2,
  "models": [
    {
      "model_id": "gpt-4o",
      "provider": "openai",
      "roles": ["Architect"],
      "quality_tier": "high",
      "cost": 0.02,
      "enabled": true,
      "availability": "available",
      "source": "static",
      "display_name": "GPT-4o"
    }
  ]
}
```

### POST /api/v1/runs

Runs the orchestration loop.

Example request:

```bash
curl -X POST http://localhost:8000/api/v1/runs \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "Create a 30-day GTM plan for a niche B2B SaaS product.",
    "task_mode": "Marketing & Growth",
    "max_iterations": 3,
    "target_score": 8.0,
    "clarification": "",
    "manual_override": "",
    "stable_mode": false
  }'
```

Request fields:

```json
{
  "user_input": "string",
  "task_mode": "Software & IT",
  "max_iterations": 3,
  "target_score": 8.0,
  "clarification": "",
  "manual_override": "",
  "stable_mode": false
}
```

Possible `status` values:
- `completed`
- `needs_clarification`
- `blocked`

Example response:

```json
{
  "run_id": "api-123456789abc",
  "status": "completed",
  "best_score": 8.1,
  "best_solution": "Final answer text...",
  "iteration_count": 2,
  "iterations": [
    {
      "iteration": 1,
      "tech_score": 7,
      "logic_score": 8,
      "avg_score": 7.6,
      "ship_readiness": "CLOSE",
      "verification_status": "CAUTION"
    }
  ],
  "total_cost_usd": 0.0142,
  "needs_clarification": false,
  "clarification_questions": []
}
```

### GET /api/v1/runs/{run_id}

Returns a persisted run when database persistence is enabled.

If persistence is unavailable, the route returns `503`.

If the run does not exist, the route returns `404`.

## Error Behavior

Common response shapes:

### 401 / 403

Returned when production auth is enabled and the request is unauthenticated or invalid.

### 404

Returned when a requested persisted run does not exist.

### 422

Returned for FastAPI/Pydantic request validation errors.

### 500

Returned when orchestration fails before the API can build a normal response.

Example:

```json
{
  "detail": "The Arbiter run failed before completion."
}
```

## Local Development Notes

- the API is safe to run without auth in local/dev mode
- persistence is optional
- missing optional dependencies degrade gracefully instead of crashing the whole product

Run the API locally with:

```bash
python arbiter/api/run_server.py
```
