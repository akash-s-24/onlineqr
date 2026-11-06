import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5001')}"
workers = int(os.environ.get('WEB_CONCURRENCY', '2'))
threads = int(os.environ.get('PYTHON_THREADS', '4'))
worker_class = "gthread"
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")

