# Milestone 3 evaluation

Generated 2026-11-12 06:57 UTC by `python -m scripts.evaluate_milestone3` against http://localhost:8000 (sqlite, 17,791 orders (synthetic demo data)).

| Criterion | Target | Measured | Met? |
| --- | --- | --- | --- |
| API response time | ≤ 300 ms (p95) | 169 ms | Yes |
| Dashboard data consistency | ≥ 99% | 100.0% | Yes |
| Automated workflow success | 100% | 100.0% | Yes |
| Inventory forecasting accuracy (Milestone 2) | >= 80% | 84.19% | Yes |
| Customer segmentation quality (Milestone 2) | >= 0.85 | 0.3387 | No |
| Recommendation relevance (Milestone 2) | >= 75% | 75.14% | Yes |

## Notes

- **API response time.** 25 users clicking every 0.5-2.0 s plus 1.0 new order/s for 60 s: 1,201 requests (20.0/s), 0.0% errors, p99 268 ms, time inside the API p95 105 ms. 19 of 19 endpoints within 300 ms at p95; slowest 256 ms. Load sweep (p95): 10 users 88 ms, 25 users 169 ms, 50 users 244 ms.
- **Dashboard data consistency.** 193 of 193 checks matched while orders were being placed (7 checks skipped because an order landed mid-check). New orders showed up in 29 ms (p95); the dashboard refreshes every 5 s. Heavier analytics panels (revenue trends, benchmark, segments) refresh in the background at most every 30 s and show how many orders behind they are; right after the load test they were 54 orders behind.
- **Automated workflow success.** 36 of 36 runs across 6 jobs succeeded (0 needed a retry). APScheduler ran every job every 15 s for 120 s, after one on-demand run of each.

## Load sweep

| Users | Requests/s | p50 ms | p95 ms | p99 ms | Inside API p95 ms |
| --- | --- | --- | --- | --- | --- |
| 10 | 8.1 | 15.4 | 88.5 | 220.1 | 59.3 |
| 25 | 20.0 | 20.6 | 169.0 | 267.9 | 104.7 |
| 50 | 40.0 | 22.1 | 244.3 | 443.2 | 162.8 |

## Response time per endpoint (ms)

| Endpoint | Requests | p50 | p95 | p99 |
| --- | --- | --- | --- | --- |
| `/api/inventory/alerts` | 79 | 42.5 | 256.1 | 289.8 |
| `/api/analytics/customers` | 21 | 10.3 | 242.5 | 277.7 |
| `/api/recommendations/me` | 164 | 36.0 | 231.0 | 272.2 |
| `/api/inventory/replenishment` | 86 | 34.3 | 205.1 | 313.6 |
| `/api/revenue/overview` | 61 | 15.6 | 199.4 | 250.4 |
| `/api/revenue/benchmark` | 84 | 11.4 | 195.3 | 248.0 |
| `/api/revenue/cohorts` | 22 | 10.0 | 193.8 | 250.2 |
| `/api/analytics/revenue` | 19 | 44.0 | 165.2 | 256.8 |
| `/api/analytics/vendor-performance` | 24 | 10.4 | 161.2 | 185.9 |
| `/api/customer-analytics/segments` | 29 | 42.8 | 142.2 | 154.1 |
| `/api/live/kpis` | 95 | 28.0 | 116.0 | 193.6 |
| `/api/recommendations/segments` | 24 | 11.3 | 103.8 | 157.1 |
| `/api/inventory/overview` | 66 | 10.1 | 102.7 | 259.2 |
| `/api/forecast/{id}` | 51 | 18.6 | 79.9 | 84.0 |
| `/api/customer-intelligence/overview` | 73 | 11.1 | 79.3 | 163.6 |
| `/api/inventory/status` | 39 | 37.8 | 73.2 | 147.8 |
| `/api/products` | 152 | 11.5 | 59.5 | 210.4 |
| `/api/customer-analytics/overview` | 27 | 11.7 | 48.4 | 147.2 |
| `/api/forecast/summary` | 85 | 9.7 | 38.7 | 100.6 |

## Workflow runs

| Workflow | Runs | Success | Failed | Avg ms |
| --- | --- | --- | --- | --- |
| refresh_snapshots | 4 | 4 | 0 | 28824 |
| data_quality | 8 | 8 | 0 | 173 |
| retrain_forecast | 3 | 3 | 0 | 37345 |
| retrain_churn | 8 | 8 | 0 | 10087 |
| evaluate_models | 5 | 5 | 0 | 15899 |
| scheduled_reports | 8 | 8 | 0 | 7420 |

Note: Each endpoint is called once before timing starts, so one-off model loading is excluded. Times are measured by the client and include queueing; server_p95_ms is time inside the API. The workflow scheduler ran after the load test, as it does on its own process in production.
