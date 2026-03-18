"""Gunicorn 生产配置"""
import multiprocessing

bind = "0.0.0.0:5000"
workers = min(multiprocessing.cpu_count() * 2 + 1, 4)
worker_class = "gthread"
threads = 4
timeout = 120
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 50

accesslog = "logs/gunicorn_access.log"
errorlog = "logs/gunicorn_error.log"
loglevel = "info"

preload_app = False
