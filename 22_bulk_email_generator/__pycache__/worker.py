import redis
from rq import SimpleWorker, Worker, Queue
# Connect to local Redis on its default port (6379)
# decode_responses=False is important — RQ stores binary data internally
redis_conn =redis.Redis(host="localhost",port=6379)

if __name__ == "__main__":
  # Connection is a context manager that sets the global RQ Redis connection

  # Listen on the "default" queue — must match what main.py uses
  worker = SimpleWorker(queues=["default"], connection=redis_conn)
            
  # burst=False means: keep running forever, waiting for new jobs
  worker.work(burst=False)
