"""Run the ShopSense workflow scheduler.

    python -m app.scheduler                     # run on the real schedule (blocking)
    python -m app.scheduler --list              # show jobs and schedules
    python -m app.scheduler --run retrain_forecast
    python -m app.scheduler --run all
    python -m app.scheduler --accelerated 300 --every 20
        # real APScheduler, every job every 20 s for 300 s, then print the success rate
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timezone

from app.database import SessionLocal
from app.scheduler.jobs import JOBS, describe, run_job, run_summary
from app.scheduler.runner import build_scheduler


def main():
    parser = argparse.ArgumentParser(description='ShopSense workflow scheduler')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--run', help="job name or 'all'")
    parser.add_argument('--accelerated', type=int, metavar='SECONDS', help='run for SECONDS with short intervals')
    parser.add_argument('--every', type=int, default=20, help='interval in seconds for --accelerated')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

    if args.list:
        for name, job in JOBS.items():
            print(f'{name:<20} {describe(job):<26} {job.description}')
        return
    if args.run:
        names = list(JOBS) if args.run == 'all' else [args.run]
        for name in names:
            result = run_job(name, trigger='manual')
            print(f"{name:<20} {result['status']:<8} {result['duration_ms']:>7} ms  {result['metrics']}")
        return
    if args.accelerated:
        started = datetime.now(timezone.utc)
        scheduler = build_scheduler('background', every_seconds=args.every, trigger_label='accelerated')
        scheduler.start()
        try:
            time.sleep(args.accelerated)
        finally:
            scheduler.shutdown(wait=True)
        with SessionLocal() as db:
            summary = run_summary(db, since=started)
        total = sum(s['runs'] for s in summary)
        ok = sum(s['success'] for s in summary)
        for s in summary:
            print(f"{s['job']:<20} runs {s['runs']:>3}  success {s['success']:>3}  failed {s['failed']:>2}")
        print(f'TOTAL runs {total}, success rate {ok / total * 100 if total else 0:.1f}%')
        return
    print('ShopSense scheduler started. Jobs:')
    for name, job in JOBS.items():
        print(f'  {name:<20} {describe(job)}')
    build_scheduler('blocking').start()


if __name__ == '__main__':
    main()
