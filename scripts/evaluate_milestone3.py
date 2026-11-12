"""Measure the Milestone 3 targets against a running ShopSense API.

Start the API first (same DATABASE_URL as this script), with demo data loaded:

    python -m scripts.seed_milestone2
    uvicorn app.main:app --port 8000
    python -m scripts.evaluate_milestone3 --users 25 --duration 60

Targets from the Milestone 3 plan:
* REST API endpoints respond within 300 ms at the 95th percentile under load
* BI dashboard metrics update in near real time with >= 99% data consistency
* automated workflows complete scheduled processing without failures (100%)

Writes reports/milestone3_evaluation.json and reports/MILESTONE3_EVALUATION.md.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'
TARGET_MS = 300

ADMIN_PATHS = ['/api/live/kpis', '/api/revenue/overview', '/api/revenue/benchmark', '/api/revenue/cohorts',
               '/api/customer-intelligence/overview', '/api/recommendations/segments', '/api/forecast/summary',
               '/api/inventory/overview', '/api/inventory/status', '/api/inventory/alerts',
               '/api/customer-analytics/overview', '/api/customer-analytics/segments', '/api/analytics/revenue',
               '/api/analytics/vendor-performance', '/api/analytics/customers', '/api/inventory/replenishment']
VENDOR_PATHS = ['/api/live/kpis', '/api/revenue/overview', '/api/revenue/benchmark', '/api/forecast/summary',
                '/api/inventory/alerts', '/api/inventory/replenishment', '/api/customer-intelligence/overview',
                '/api/inventory/overview', '/api/forecast/{own_product}']
CUSTOMER_PATHS = ['/api/recommendations/me', '/api/products']


def label(path: str) -> str:
    return re.sub(r'/\d+', '/{id}', path.split('?')[0])


# ------------------------------------------------------------------ helpers
async def login(client, email, password):
    r = await client.post('/api/auth/login', json={'email': email, 'password': password})
    r.raise_for_status()
    return {'Authorization': f"Bearer {r.json()['access_token']}"}


async def setup(client, vendors=5, shoppers=40):
    admin = await login(client, 'demo.admin@example.com', 'DemoAdmin123!')
    vend = []
    for i in range(1, vendors + 1):
        h = await login(client, f'vendor{i}@shopsense.example', 'DemoVendor123!')
        mine = (await client.get('/api/products/mine', headers=h)).json()
        vend.append((h, [p['id'] for p in mine]))
    shop = [await login(client, f'shopper{i}@shopsense.example', 'DemoShopper123!') for i in range(1, shoppers + 1)]
    products = [p['id'] for p in (await client.get('/api/products')).json() if p['quantity'] > 20]
    return admin, vend, shop, products


async def place_order(client, shoppers, products):
    h = random.choice(shoppers)
    started = time.perf_counter()
    r = await client.post('/api/orders', headers=h, json={'items': [{'product_id': random.choice(products), 'quantity': 1}]})
    return r.status_code, (time.perf_counter() - started) * 1000


# ------------------------------------------------------------- 1. latency
async def latency_test(api, users, duration, write_rate, think=(0.5, 2.0)):
    limits = httpx.Limits(max_connections=users + 5)
    async with httpx.AsyncClient(base_url=api, timeout=30, limits=limits) as client:
        admin, vend, shop, products = await setup(client)
        # Warm-up: one pass over every endpoint so one-off model loading is not counted.
        for p in ADMIN_PATHS + ['/api/customer-analytics/segments']:
            await client.get(p, headers=admin)
        for h, mine in vend:
            for p in VENDOR_PATHS:
                await client.get(p.replace('{own_product}', str(mine[0])), headers=h)
        for h in shop[:5]:
            for p in CUSTOMER_PATHS:
                await client.get(p, headers=h)

        samples, writes, stop = [], [], time.perf_counter() + duration

        async def user():
            while time.perf_counter() < stop:
                role = random.random()
                if role < 0.35:
                    headers, path = admin, random.choice(ADMIN_PATHS)
                elif role < 0.75:
                    headers, mine = random.choice(vend)
                    path = random.choice(VENDOR_PATHS).replace('{own_product}', str(random.choice(mine)))
                else:
                    headers, path = random.choice(shop), random.choice(CUSTOMER_PATHS)
                t0 = time.perf_counter()
                server = None
                try:
                    r = await client.get(path, headers=headers)
                    status = r.status_code
                    timing = r.headers.get('server-timing', '')
                    server = float(timing.split('dur=')[1]) if 'dur=' in timing else None
                except httpx.HTTPError:
                    status = 0
                samples.append((label(path), (time.perf_counter() - t0) * 1000, status, server))
                await asyncio.sleep(random.uniform(*think))  # a person reading the page before the next click

        async def writer():
            while time.perf_counter() < stop:
                writes.append(await place_order(client, shop, products))
                await asyncio.sleep(1 / write_rate)

        await asyncio.gather(*[user() for _ in range(users)], writer())

    lat = np.array([s[1] for s in samples])
    errors = sum(1 for s in samples if s[2] != 200)
    per = {}
    for path, ms, status, _ in samples:
        per.setdefault(path, []).append(ms)
    server = np.array([s[3] for s in samples if s[3] is not None])
    endpoints = [{'path': p, 'requests': len(v), 'p50_ms': round(float(np.percentile(v, 50)), 1),
                  'p95_ms': round(float(np.percentile(v, 95)), 1), 'p99_ms': round(float(np.percentile(v, 99)), 1)}
                 for p, v in sorted(per.items())]
    write_ms = [w[1] for w in writes]
    return {
        'users': users, 'duration_s': duration, 'write_rate_per_s': write_rate, 'requests': len(samples),
        'think_time_s': list(think),
        'server_p95_ms': round(float(np.percentile(server, 95)), 1) if len(server) else None,
        'server_p50_ms': round(float(np.percentile(server, 50)), 1) if len(server) else None,
        'throughput_rps': round(len(samples) / duration, 1), 'errors': errors,
        'error_rate_pct': round(errors / len(samples) * 100, 2) if samples else None,
        'overall': {'p50_ms': round(float(np.percentile(lat, 50)), 1), 'p95_ms': round(float(np.percentile(lat, 95)), 1),
                    'p99_ms': round(float(np.percentile(lat, 99)), 1), 'mean_ms': round(float(lat.mean()), 1)},
        'worst_endpoint_p95_ms': max(e['p95_ms'] for e in endpoints),
        'endpoints_within_target': sum(e['p95_ms'] <= TARGET_MS for e in endpoints), 'endpoint_count': len(endpoints),
        'endpoints': endpoints,
        'writes': {'orders': len(writes), 'ok': sum(1 for w in writes if w[0] == 201),
                   'p95_ms': round(float(np.percentile(write_ms, 95)), 1) if write_ms else None},
        'note': ('Each endpoint is called once before timing starts, so one-off model loading is excluded. '
                 'Times are measured by the client and include queueing; server_p95_ms is time inside the API.'),
    }


# --------------------------------------------------------- 2. consistency
TRUTH_SQL = text("""
    SELECT COALESCE(SUM(oi.quantity * oi.unit_price), 0), COUNT(DISTINCT oi.order_id), COALESCE(SUM(oi.quantity), 0),
           COUNT(DISTINCT o.customer_id)
    FROM order_items oi JOIN orders o ON o.id = oi.order_id WHERE o.status != 'cancelled'""")


def truth():
    with SessionLocal() as db:
        gmv, orders, units, customers = db.execute(TRUTH_SQL).one()
    return round(float(gmv), 2), int(orders), int(units), int(customers)


async def consistency_test(api, checks, write_rate):
    async with httpx.AsyncClient(base_url=api, timeout=30) as client:
        admin, _, shop, products = await setup(client, vendors=1)
        consistent = compared = ambiguous = 0
        visibility, stop = [], asyncio.Event()

        async def writer():
            while not stop.is_set():
                await place_order(client, shop, products)
                await asyncio.sleep(1 / write_rate)

        task = asyncio.create_task(writer())
        for _ in range(checks):
            before = await asyncio.to_thread(truth)
            k = (await client.get('/api/live/kpis', headers=admin)).json()
            after = await asyncio.to_thread(truth)
            if before != after:  # an order landed mid-check; cannot tell which state the API saw
                ambiguous += 1
                continue
            compared += 1
            consistent += (round(k['gmv'], 2), k['orders'], k['units_sold'], k['customers']) == before
            await asyncio.sleep(0.05)
        stop.set()
        await task

        # Time from an order being accepted to the dashboard's live numbers showing it.
        for _ in range(20):
            seen = (await client.get('/api/live/kpis', headers=admin)).json()['orders']
            await place_order(client, shop, products)
            t0 = time.perf_counter()
            while (await client.get('/api/live/kpis', headers=admin)).json()['orders'] <= seen:
                await asyncio.sleep(0.01)
            visibility.append((time.perf_counter() - t0) * 1000)
            await asyncio.sleep(0.1)
        overview = (await client.get('/api/revenue/overview', headers=admin)).json()
    return {'checks': compared, 'consistent': consistent, 'ambiguous_skipped': ambiguous,
            'consistency_pct': round(consistent / compared * 100, 2) if compared else None,
            'writes': ambiguous + compared, 'visibility_ms_p95': round(float(np.percentile(visibility, 95)), 1),
            'dashboard_refresh_s': 5,
            'snapshot_orders_behind_after_load': overview['meta']['orders_behind']}


# ------------------------------------------------------------ 3. workflows
def workflow_test(seconds, every):
    from app.scheduler.jobs import JOBS, run_job, run_summary
    from app.scheduler.runner import build_scheduler
    started = datetime.now(timezone.utc)
    for name in JOBS:  # one on-demand run of each job
        run_job(name, trigger='evaluation')
    scheduler = build_scheduler('background', every_seconds=every, trigger_label='accelerated')
    scheduler.start()
    time.sleep(seconds)
    scheduler.shutdown(wait=True)
    with SessionLocal() as db:
        jobs = run_summary(db, since=started)
        retried = db.execute(text('SELECT COUNT(*) FROM workflow_runs WHERE attempts > 1 AND started_at >= :s'),
                             {'s': started}).scalar()
    runs = sum(j['runs'] for j in jobs)
    success = sum(j['success'] for j in jobs)
    return {'duration_s': seconds, 'every_s': every, 'runs': runs, 'success': success, 'failed': runs - success,
            'retried_runs': int(retried or 0), 'success_rate_pct': round(success / runs * 100, 2) if runs else None,
            'jobs': [{k: j[k] for k in ('job', 'runs', 'success', 'failed', 'avg_duration_ms')} for j in jobs]}


# --------------------------------------------------------------- report
def scorecard(report):
    lat, con, wf = report['latency'], report['consistency'], report['workflows']
    rows = [
        {'criterion': 'API response time', 'target': '≤ 300 ms (p95)', 'value': lat['overall']['p95_ms'],
         'display': f"{lat['overall']['p95_ms']:.0f} ms", 'met': lat['overall']['p95_ms'] <= TARGET_MS,
         'metric': '95th percentile over all analytical GET requests',
         'context': (f"{lat['users']} users clicking every {lat['think_time_s'][0]}-{lat['think_time_s'][1]} s plus "
                     f"{lat['write_rate_per_s']} new order/s for {lat['duration_s']} s: {lat['requests']:,} requests "
                     f"({lat['throughput_rps']}/s), {lat['error_rate_pct']}% errors, p99 {lat['overall']['p99_ms']:.0f} ms, "
                     f"time inside the API p95 {lat['server_p95_ms']:.0f} ms. {lat['endpoints_within_target']} of "
                     f"{lat['endpoint_count']} endpoints within 300 ms at p95; slowest {lat['worst_endpoint_p95_ms']:.0f} ms. "
                     + sweep_text(report))},
        {'criterion': 'Dashboard data consistency', 'target': '≥ 99%', 'value': con['consistency_pct'],
         'display': f"{con['consistency_pct']}%", 'met': (con['consistency_pct'] or 0) >= 99,
         'metric': 'Live dashboard numbers equal to a direct database count',
         'context': (f"{con['consistent']} of {con['checks']} checks matched while orders were being placed "
                     f"({con['ambiguous_skipped']} checks skipped because an order landed mid-check). New orders "
                     f"showed up in {con['visibility_ms_p95']:.0f} ms (p95); the dashboard refreshes every "
                     f"{con['dashboard_refresh_s']} s. Heavier analytics panels (revenue trends, benchmark, segments) "
                     f"refresh in the background at most every 30 s and show how many orders behind they are; right "
                     f"after the load test they were {con['snapshot_orders_behind_after_load']} orders behind.")},
        {'criterion': 'Automated workflow success', 'target': '100%', 'value': wf['success_rate_pct'],
         'display': f"{wf['success_rate_pct']}%", 'met': wf['success_rate_pct'] == 100,
         'metric': 'Finished workflow runs that succeeded',
         'context': (f"{wf['success']} of {wf['runs']} runs across {len(wf['jobs'])} jobs succeeded "
                     f"({wf['retried_runs']} needed a retry). APScheduler ran every job every {wf['every_s']} s "
                     f"for {wf['duration_s']} s, after one on-demand run of each.")},
    ]
    m2 = report.get('milestone2_targets') or []
    for r in m2:
        rows.append({**r, 'display': f"{r['value']}{'%' if '%' in r['target'] else ''}",
                     'criterion': f"{r['criterion']} (Milestone 2)"})
    return rows


def sweep_text(report) -> str:
    sweep = report.get('load_sweep') or []
    if not sweep:
        return ''
    parts = [f"{x['users']} users {x['p95_ms']:.0f} ms" for x in sweep]
    return 'Load sweep (p95): ' + ', '.join(parts) + '.'


def markdown(report):
    lines = ['# Milestone 3 evaluation', '',
             f"Generated {report['generated_at']} by `python -m scripts.evaluate_milestone3` against "
             f"{report['environment']['api']} ({report['environment']['database']}, {report['environment']['dataset']}).", '',
             '| Criterion | Target | Measured | Met? |', '| --- | --- | --- | --- |']
    lines += [f"| {r['criterion']} | {r['target']} | {r['display']} | {'Yes' if r['met'] else 'No'} |"
              for r in report['scorecard']]
    lines += ['', '## Notes', ''] + [f"- **{r['criterion']}.** {r['context']}" for r in report['scorecard'][:3]]
    if report.get('load_sweep'):
        lines += ['', '## Load sweep', '', '| Users | Requests/s | p50 ms | p95 ms | p99 ms | Inside API p95 ms |',
                  '| --- | --- | --- | --- | --- | --- |']
        lines += [f"| {x['users']} | {x['throughput_rps']} | {x['p50_ms']} | {x['p95_ms']} | {x['p99_ms']} | {x['server_p95_ms']} |"
                  for x in report['load_sweep']]
    lines += ['', '## Response time per endpoint (ms)', '', '| Endpoint | Requests | p50 | p95 | p99 |',
              '| --- | --- | --- | --- | --- |']
    lines += [f"| `{e['path']}` | {e['requests']} | {e['p50_ms']} | {e['p95_ms']} | {e['p99_ms']} |"
              for e in sorted(report['latency']['endpoints'], key=lambda e: -e['p95_ms'])]
    lines += ['', '## Workflow runs', '', '| Workflow | Runs | Success | Failed | Avg ms |', '| --- | --- | --- | --- | --- |']
    lines += [f"| {j['job']} | {j['runs']} | {j['success']} | {j['failed']} | {j['avg_duration_ms']} |"
              for j in report['workflows']['jobs']]
    lines += ['', f"Note: {report['latency']['note']} The workflow scheduler ran after the load test, as it does on "
              'its own process in production.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Evaluate Milestone 3 targets')
    parser.add_argument('--api', default='http://localhost:8000')
    parser.add_argument('--users', type=int, default=25)
    parser.add_argument('--duration', type=int, default=60)
    parser.add_argument('--think-min', type=float, default=0.5)
    parser.add_argument('--think-max', type=float, default=2.0)
    parser.add_argument('--sweep', default='', help='extra user counts to measure, e.g. "10,50"')
    parser.add_argument('--write-rate', type=float, default=1.0, help='new orders per second during the tests')
    parser.add_argument('--checks', type=int, default=200)
    parser.add_argument('--workflow-seconds', type=int, default=120)
    parser.add_argument('--every', type=int, default=15)
    parser.add_argument('--workers', type=int, default=1, help='uvicorn workers serving the API (for the record)')
    parser.add_argument('--stages', default='latency,consistency,workflows',
                        help='run only some stages; results merge into the existing report')
    args = parser.parse_args()
    random.seed(7)
    stages = set(args.stages.split(','))
    path = REPORTS / 'milestone3_evaluation.json'
    partial = REPORTS / 'milestone3_evaluation.partial.json'
    report = {}
    if stages != {'latency', 'consistency', 'workflows'}:  # merge with earlier stages
        for source in (partial, path):
            if source.exists():
                report = json.loads(source.read_text())
                break
    think = (args.think_min, args.think_max)

    if 'latency' in stages:
        print(f'Load test: {args.users} users for {args.duration} s ...', flush=True)
        report['latency'] = asyncio.run(latency_test(args.api, args.users, args.duration, args.write_rate, think))
        print(f"    p95 {report['latency']['overall']['p95_ms']} ms over {report['latency']['requests']} requests", flush=True)
    if 'sweep' in stages and args.sweep:
        sweep = []
        for n in [int(x) for x in args.sweep.split(',')]:
            r = asyncio.run(latency_test(args.api, n, args.duration, args.write_rate, think))
            sweep.append({'users': n, 'throughput_rps': r['throughput_rps'], **r['overall'],
                          'server_p95_ms': r['server_p95_ms'], 'errors': r['errors']})
            print(f"    sweep {n} users: p95 {r['overall']['p95_ms']} ms", flush=True)
        main_level = report.get('latency')
        if main_level:
            sweep.append({'users': main_level['users'], 'throughput_rps': main_level['throughput_rps'],
                          **main_level['overall'], 'server_p95_ms': main_level['server_p95_ms'],
                          'errors': main_level['errors']})
        report['load_sweep'] = sorted(sweep, key=lambda x: x['users'])
    if 'consistency' in stages:
        print(f'Consistency: {args.checks} checks ...', flush=True)
        report['consistency'] = asyncio.run(consistency_test(args.api, args.checks, args.write_rate))
        print(f"    {report['consistency']['consistency_pct']}% consistent", flush=True)
    if 'workflows' in stages:
        print(f'Workflows: APScheduler every {args.every} s for {args.workflow_seconds} s ...', flush=True)
        report['workflows'] = workflow_test(args.workflow_seconds, args.every)
        print(f"    {report['workflows']['success']}/{report['workflows']['runs']} runs succeeded", flush=True)

    missing = [k for k in ('latency', 'consistency', 'workflows') if k not in report]
    if missing:
        REPORTS.mkdir(exist_ok=True)
        partial.write_text(json.dumps(report, indent=2, default=str))
        print('Saved partial results; still to run:', ', '.join(missing))
        return
    m2_path = REPORTS / 'milestone2_evaluation.json'
    m2 = json.loads(m2_path.read_text())['scorecard'] if m2_path.exists() else []
    with SessionLocal() as db:
        orders = db.execute(text('SELECT COUNT(*) FROM orders')).scalar()
    report.update({
        'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        'environment': {'api': args.api, 'workers': args.workers, 'database': settings.database_url.split(':')[0],
                        'dataset': f'{orders:,} orders (synthetic demo data)',
                        'machine': 'one shared CPU core for the API, the load generator and the scheduler'},
        'targets': {'api_p95_ms': TARGET_MS, 'consistency_pct': 99, 'workflow_success_pct': 100},
        'milestone2_targets': [{k: r[k] for k in ('criterion', 'target', 'value', 'met', 'metric', 'context')}
                               for r in m2],
    })
    report['scorecard'] = scorecard(report)
    REPORTS.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str))
    (REPORTS / 'MILESTONE3_EVALUATION.md').write_text(markdown(report))
    partial.unlink(missing_ok=True)
    for r in report['scorecard']:
        print(f"{'PASS' if r['met'] else 'MISS'}  {r['criterion']}: {r['display']} (target {r['target']})")


if __name__ == '__main__':
    main()
