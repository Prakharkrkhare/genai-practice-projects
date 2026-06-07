from fastapi import FastAPI, HTTPException   # FastAPI core + error helper
from pydantic import BaseModel              # used to define request/response shapes
from typing import List                    # for type hints with lists
import redis                               # to connect to Redis
from rq import Queue                       # RQ's queue abstraction
from rq.job import Job                     # lets us look up job status by ID
from tasks import generate_subject_line    # the function we'll enqueue

# ── App & connections ──────────────────────────────────────────────────────────

app=FastAPI()

# One Redis connection, reused by both endpoints
redis_conn=redis.Redis(host="localhost",port=6379)

# Queue named "default" — must match the queue name in worker.py
queue=Queue("default",connection=redis_conn)

# ── Request / Response models ──────────────────────────────────────────────────

class generateRequest(BaseModel):
    products: List[str]   # expects: {"products": ["Laptop", "Headphones", ...]}

class generateResponse(BaseModel):
    job_ids: List[str]    # returns: {"job_ids": ["abc123", "def456", ...]}

class resultRequest(BaseModel):
    job_ids: List[str]    # expects: {"job_ids": ["abc123", "def456", ...]}


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.post("/generate",response_model=generateResponse)
def generate(request:generateRequest):
  """
    Accepts up to 10 product names.
    Enqueues one RQ job per product.
    Returns the list of job IDs immediately — no waiting for OpenAI.
  """
  if len(request.products)>10:
    # Enforce the 10-product limit; 422 would also work but 400 is clearer
    raise HTTPException(status_code=400, detail="maximum 10 products allowed.")
  
  job_ids=[]

  for product in request.products:
    # queue.enqueue() serialises the function + argument into Redis,
    # then returns a Job object whose .id is a UUID string
    job = queue.enqueue(
        generate_subject_line,  # function to run — must be importable by the worker
        product,                # positional argument passed to that function
        job_timeout=60,         # kill the job if it takes longer than 60 seconds
    )
    job_ids.append(job.id)      # collect the UUID so we can return it

  return generateResponse(job_ids=job_ids)

@app.post("/results")
def results(request:resultRequest):
  """
    Accepts a list of job IDs.
    For each, fetches the job from Redis and maps its status to
    'queued', 'processing', or 'done', plus the result if finished.
  """
  output=[]

  for job_id in request.job_ids:
    # Job.fetch() re-hydrates the job object from Redis by its UUID
    # If the ID is invalid or expired, it raises NoSuchJobError
    try:
      job=Job.fetch(job_id, connection=redis_conn)

    except Exception:
        # Return a clear error entry rather than crashing the whole response
      output.append({"job_id":job_id,"status":"not found"})
      continue

    # job.get_status() returns an RQ JobStatus enum; .value gives the string
    raw_status=job.get_status().value

    # Map RQ's internal status names to your API's three status values
    if raw_status == "queued":
      status = "queued"
    elif raw_status == "started":
      status = "processing"
    elif raw_status == "finished":
      status = "done"
    
    entry={"job_id":job_id,"status":status}

    if raw_status == "finished":
      entry["subject_line"] = job.result

    output.append(entry)

  return output