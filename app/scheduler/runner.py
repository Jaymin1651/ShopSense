"""Build APScheduler schedulers for the ShopSense workflows."""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

from app.scheduler.jobs import JOBS, run_job

JOB_DEFAULTS = {'max_instances': 1, 'coalesce': True, 'misfire_grace_time': 3600}


def build_scheduler(kind: str = 'blocking', every_seconds: int | None = None, trigger_label: str = 'schedule'):
    """``every_seconds`` replaces every schedule with a short interval (testing)."""
    scheduler = (BlockingScheduler if kind == 'blocking' else BackgroundScheduler)(
        timezone='UTC', job_defaults=JOB_DEFAULTS)
    for name, job in JOBS.items():
        if every_seconds:
            scheduler.add_job(run_job, 'interval', seconds=every_seconds, args=[name, trigger_label],
                              id=name, name=job.description)
        else:
            scheduler.add_job(run_job, job.trigger, args=[name, trigger_label], id=name, name=job.description,
                              **job.schedule)
    return scheduler
