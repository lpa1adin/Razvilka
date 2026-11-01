from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "razvilka_http_requests_total", "HTTP-запросы к API", ["method", "route", "status"]
)
HTTP_DURATION = Histogram(
    "razvilka_http_request_duration_seconds", "Длительность HTTP-запросов", ["method", "route"]
)
WORKER_HEARTBEAT = Gauge(
    "razvilka_worker_heartbeat_timestamp_seconds", "Последний цикл воркера", ["worker"]
)
JOBS_QUEUED = Gauge("razvilka_jobs_queued", "Задачи в очереди", ["kind"])
JOBS_DONE = Counter("razvilka_jobs_done_total", "Выполненные задачи", ["kind", "result"])
AGENT_RUNS = Counter("razvilka_agent_runs_total", "Обращения к Claude", ["purpose", "result"])
AGENT_SECONDS = Histogram(
    "razvilka_agent_run_seconds", "Длительность обращения к Claude", ["purpose"],
    buckets=(1, 3, 10, 30, 60, 120, 300, 600, 1200),
)
AGENT_TOKENS = Counter("razvilka_agent_tokens_total", "Токены Claude по видам", ["purpose", "kind"])
