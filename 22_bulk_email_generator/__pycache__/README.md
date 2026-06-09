# Bulk Email Subject Line Generator

A FastAPI-based async job queue system that generates catchy email subject lines for multiple products simultaneously using OpenAI's `gpt-4o-mini` and RQ (Redis Queue).

---

## What It Does

Instead of calling OpenAI sequentially (slow), this system enqueues each product as a **separate background job** and returns job IDs instantly. The user polls for results when ready.

**Without queue:** 10 products × ~2s per OpenAI call = ~20s wait
**With queue:** Enqueue all 10 → respond in <100ms → results ready in background

---

## Tech Stack

| Package | Role |
|---|---|
| `fastapi` | Web framework, exposes REST endpoints |
| `uvicorn` | ASGI server that runs FastAPI |
| `rq` | Redis Queue — manages background jobs |
| `redis` | Message broker; stores job state and results |
| `openai` | Calls `gpt-4o-mini` to generate subject lines |
| `python-dotenv` | Loads secrets from `.env` file |

---

## Folder Structure

```
email_subject_generator/
├── .env          ← API keys and config (never commit this)
├── config.py     ← Loads .env, exports clean variables
├── tasks.py      ← Core logic: calls OpenAI, returns subject line
├── worker.py     ← Starts RQ worker to process queued jobs
└── main.py       ← FastAPI app with /generate and /results
```

### File Creation Order (important)

```
1. .env       → secrets first, everything depends on this
2. tasks.py   → core logic, test in isolation before adding queue
3. worker.py  → needs tasks.py to exist
4. config.py  → centralizes all settings
5. main.py    → ties everything together last
```

---

## Architecture — How the Pieces Connect

```
USER                   FASTAPI (main.py)        REDIS            WORKER (worker.py)       OPENAI
 │                           │                    │                     │                    │
 │── POST /generate ────────►│                    │                     │                    │
 │   {products: [10 names]}  │                    │                     │                    │
 │                           │── enqueue 10 jobs─►│                     │                    │
 │◄── {job_ids: [10 ids]} ───│                    │                     │                    │
 │   (returns in <100ms)     │                    │◄── poll for jobs ───│                    │
 │                           │                    │──── job ───────────►│                    │
 │                           │                    │                     │── prompt ─────────►│
 │                           │                    │                     │◄── subject line ───│
 │                           │                    │◄─── store result ───│                    │
 │── GET /results ───────────►│                   │                     │                    │
 │   {job_ids: [...]}        │── fetch statuses ──►│                    │                    │
 │◄── {results: [...]} ──────│                    │                     │                    │
```

---

## The Three Actors

| Actor | File | Responsibility |
|---|---|---|
| **API Server** | `main.py` | Accepts requests, enqueues jobs, reports status. Never calls OpenAI directly. |
| **Redis / Valkey** | (external) | Shared message board. Stores job queue, state, and results. |
| **Worker** | `worker.py` + `tasks.py` | Watches Redis, picks up jobs, calls OpenAI, saves results back. |

---

## API Endpoints

### POST `/generate`
Accepts up to 10 product names. Enqueues one job per product. Returns job IDs immediately.

**Request:**
```json
{
  "products": ["Wireless Earbuds", "Standing Desk", "Coffee Grinder"]
}
```

**Response:**
```json
{
  "job_ids": ["abc123", "def456", "ghi789"]
}
```

---

### POST `/results`
Accepts job IDs. Returns status and subject line for each.

**Request:**
```json
{
  "job_ids": ["abc123", "def456", "ghi789"]
}
```

**Response:**
```json
{
  "results": [
    {"job_id": "abc123", "status": "done", "subject_line": "Hear the Difference"},
    {"job_id": "def456", "status": "processing"},
    {"job_id": "ghi789", "status": "queued"}
  ]
}
```

**Status values:**

| Status | Meaning |
|---|---|
| `queued` | Job is waiting in Redis, not picked up yet |
| `processing` | Worker is currently running this job |
| `done` | OpenAI responded, subject line is ready |
| `failed` | Job encountered an error |
| `not_found` | Invalid or expired job ID |

> `/results` is `POST` (not `GET`) because browsers block GET requests with a body. Swagger UI enforces this restriction.

---

## Queue — Key Concept

Both `main.py` and `worker.py` must use the **same queue name**. The name is just a Redis key — it has no special meaning to RQ.

```python
# main.py — writes jobs here
queue = Queue("default", connection=redis_conn)

# worker.py — listens here
worker = SimpleWorker(queues=["default"], connection=redis_conn)
```

If they don't match, jobs sit in Redis forever — the worker stays idle with no error thrown.

Redis stores the queue as: `rq:queue:default`

---

## Worker Types — Comparison

| | `SimpleWorker` | `SpawnWorker` | `Worker` |
|---|---|---|---|
| Own memory per job | No | Yes | Yes |
| Works on Windows | Yes | Yes | No |
| How it runs jobs | Same process | Spawns new process | Forks process (Unix only) |
| Crash isolation | No | Yes | Yes |
| Startup speed | Fastest | Slower | Fast |
| Best for | Windows dev | Windows production | Linux production |

`Worker` uses `os.fork()` which does not exist on Windows — use `SimpleWorker` or `SpawnWorker` instead.

`SpawnWorker` requires the `if __name__ == "__main__":` guard to prevent infinite spawning.

---

## Running on Windows with Valkey (Docker)

This project uses **Valkey** (Redis-compatible drop-in) via Docker instead of a native Redis install.

### Startup Order

```
Step 1 (Docker)      Step 2 (Terminal 1)     Step 3 (Terminal 2)
─────────────────    ───────────────────     ───────────────────
Start Valkey     →   python worker.py    →   uvicorn main:app
container                                    --reload --port 8000
```

### Step 1 — Start Valkey

```powershell
# First time only
docker run -d --name valkey -p 6379:6379 valkey/valkey

# From second time onwards
docker start valkey

# Verify it's running
docker exec -it valkey valkey-cli ping
# Expected output: PONG
```

> If port 6379 is already allocated, another container is running. Check with `docker ps` — if it's healthy, just use it as-is. Your app points to `localhost:6379` regardless of container name.

### Step 2 — Start the Worker

```powershell
cd path/to/email_subject_generator
python worker.py
```

Expected output:
```
Worker rq:worker:xxx started
*** Listening on default...
```

### Step 3 — Start FastAPI

```powershell
uvicorn main:app --reload --port 8000
```

Expected output:
```
Uvicorn running on http://127.0.0.1:8000
```

---

## Testing

### Swagger UI (browser)
```
http://127.0.0.1:8000/docs
```

### curl — Enqueue jobs
```bash
curl -X POST http://127.0.0.1:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"products": ["Wireless Earbuds", "Standing Desk", "Coffee Grinder"]}'
```

### curl — Poll results (paste your actual job IDs)
```bash
curl -X POST http://127.0.0.1:8000/results \
  -H "Content-Type: application/json" \
  -d '{"job_ids": ["abc123", "def456", "ghi789"]}'
```

Call `/results` 2-3 times. Watch status move: `queued` → `processing` → `done`

---

## Environment Variables (`.env`)

```bash
OPENAI_API_KEY=sk-your-real-key-here

REDIS_HOST=localhost
REDIS_PORT=6379

APP_HOST=127.0.0.1
APP_PORT=8000
```

All variables have safe defaults in `config.py` — only `OPENAI_API_KEY` is mandatory.

---

## Common Errors and Fixes

| Error | Cause | Fix |
|---|---|---|
| `cannot import name 'Connection' from 'rq'` | RQ v1.16+ removed `Connection` | Remove `Connection` import, pass `connection=` directly to `Worker` |
| `os has no attribute 'fork'` | `Worker` uses Unix-only `os.fork()` | Use `SimpleWorker` or `SpawnWorker` on Windows |
| `port is already allocated` | Another container using port 6379 | Run `docker ps`, use the existing container or stop it first |
| `GET request cannot have body` | Browser blocks GET with body | Change `/results` to `POST` in `main.py` |
| Jobs stuck in `queued` forever | Queue name mismatch | Ensure `main.py` and `worker.py` use the same queue name |

---

## Important Notes

- **Result expiry:** Job results are stored in Redis for **500 seconds** then auto-deleted. Poll before they expire.
- **Job limit:** `/generate` enforces a maximum of 10 products per request.
- **No `run.py` needed:** Start FastAPI directly with `uvicorn main:app --reload --port 8000`.
- **Worker must be running** before jobs are enqueued for cleanest operation — though jobs enqueued before the worker starts will still be picked up once the worker comes online.
- **Stopping order:** Stop FastAPI first → then worker → then Valkey. This prevents jobs being enqueued after the worker is dead.
