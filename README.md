# Fast Crews

FastAPI that serves a purpose to be a gateway to multiagent AI flows orchestrated by notorious CrewAI

## List of Crews
- **Poets crew**. Consists of several poets agents competing for critic agent choice.

### TechStack
- Python FastAPI
- Postgres
- Redis
- ARQ
- CrewAI
- OpenAI
- Openrouter
- LLMS

### Install

`uv sync`

PostgreSQL must have the `pgvector` extension available before running migrations; the
poet workflow enables it with `CREATE EXTENSION IF NOT EXISTS vector`.

### Run

`uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`

### Based on - Benavlabs FastAPI Boilerplate
(https://github.com/benavlabs/fastapi-boilerplate)
