from celery import Celery

from app.core.config import settings


celery_app = Celery("incident_management")
celery_app.conf.broker_url = settings.redis_url
celery_app.conf.result_backend = settings.redis_url
celery_app.conf.task_always_eager = settings.celery_task_always_eager
celery_app.conf.imports = ("app.tasks",)
