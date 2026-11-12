"""MLflow registry, workflow runs, report exports and the Milestone 3 evaluation."""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import admin, scope, staff
from app.database import get_db
from app.mlflow_tracking import tracking
from app.models import User, WorkflowRun
from app.reports.data import collect
from app.reports.excel_reports import build_workbook
from app.reports.pdf_reports import build_pdf
from app.scheduler.jobs import JOBS, run_job, run_summary

router = APIRouter(tags=['MLOps & Workflows'])
EVAL_PATH = Path(__file__).resolve().parents[2] / 'reports' / 'milestone3_evaluation.json'


@router.get('/api/mlops/models')
def models(_: User = Depends(admin)):
    """Registered models, versions, aliases (production / challenger) and metrics."""
    return tracking.registry_overview()


@router.get('/api/mlops/runs')
def runs(limit: int = Query(default=20, ge=1, le=100), _: User = Depends(admin)):
    """Most recent MLflow runs across the ShopSense experiments."""
    return tracking.recent_runs(limit)


@router.get('/api/workflows')
def workflows(db: Session = Depends(get_db), _: User = Depends(admin)):
    """Every job with its schedule, run counts and success rate."""
    return run_summary(db)


@router.get('/api/workflows/runs')
def workflow_runs(job: str | None = None, limit: int = Query(default=50, ge=1, le=500),
                  db: Session = Depends(get_db), _: User = Depends(admin)):
    stmt = select(WorkflowRun).order_by(WorkflowRun.id.desc()).limit(limit)
    if job:
        stmt = stmt.where(WorkflowRun.job == job)
    return [{'id': r.id, 'job': r.job, 'trigger': r.trigger, 'status': r.status, 'attempts': r.attempts,
             'started_at': r.started_at.isoformat(timespec='seconds') if r.started_at else None,
             'duration_ms': r.duration_ms, 'message': r.message.split('\n')[0][:300],
             'metrics': json.loads(r.metrics or '{}')} for r in db.scalars(stmt).all()]


@router.post('/api/workflows/{job}/run', status_code=202)
def trigger(job: str, wait: bool = False, db: Session = Depends(get_db), _: User = Depends(admin)):
    """Run a job now. ``wait=true`` returns the finished run; otherwise it runs in the background."""
    if job not in JOBS:
        raise HTTPException(404, f'Unknown job. Choose one of: {", ".join(JOBS)}')
    bind = db.get_bind()

    def factory():
        return Session(bind=bind)
    if wait:
        return run_job(job, trigger='manual', session_factory=factory, retries=0)
    threading.Thread(target=run_job, args=(job, 'manual', factory), daemon=True).start()
    return {'job': job, 'started': True}


def _download(content: bytes, media: str, ext: str, user: User) -> Response:
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d')
    who = 'marketplace' if user.role == 'admin' else f'vendor{user.vendor_id}'
    return Response(content, media_type=media,
                    headers={'Content-Disposition': f'attachment; filename="shopsense-{who}-{stamp}.{ext}"'})


@router.get('/api/reports/business.xlsx')
def excel(db: Session = Depends(get_db), user: User = Depends(staff)):
    """Excel workbook: summary, revenue, categories, benchmark, customers, segment picks, forecast."""
    return _download(build_workbook(collect(db, scope(user))),
                     'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx', user)


@router.get('/api/reports/business.pdf')
def pdf(db: Session = Depends(get_db), user: User = Depends(staff)):
    """PDF report with KPIs, revenue chart, benchmark, customer risk and stock shortfalls."""
    return _download(build_pdf(collect(db, scope(user))), 'application/pdf', 'pdf', user)


@router.get('/api/evaluation/milestone3')
def milestone3_report(_: User = Depends(staff)):
    """Latest result of scripts/evaluate_milestone3.py."""
    if not EVAL_PATH.exists():
        return {'available': False, 'reason': 'Run python -m scripts.evaluate_milestone3 to create the report.'}
    return json.loads(EVAL_PATH.read_text())
