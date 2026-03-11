"""gunicorn_conf.py - Gunicorn 生产配置"""
import multiprocessing

bind = "0.0.0.0:5000"
workers = min(multiprocessing.cpu_count() * 2 + 1, 4)
timeout = 120
accesslog = "logs/access.log"
errorlog = "logs/error.log"
loglevel = "info"
