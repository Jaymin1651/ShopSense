"""Collect everything a business report needs, for the marketplace or one vendor."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.analytics.revenue_analysis import anonymise_benchmark, live_kpis
from app.models import Vendor
from app.services import bi, intelligence


def collect(db: Session, vendor_id: int | None) -> dict:
    scope = 'Whole marketplace'
    if vendor_id is not None:
        vendor = db.get(Vendor, vendor_id)
        scope = f'Vendor: {vendor.business_name}' if vendor else f'Vendor #{vendor_id}'
    bench = bi.compute_benchmark(db)
    return {
        'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        'scope': scope, 'vendor_id': vendor_id,
        'kpis': live_kpis(db, vendor_id),
        'revenue': bi.compute_revenue_overview(db, vendor_id),
        'benchmark': bench if vendor_id is None else anonymise_benchmark(bench, vendor_id),
        'customers': bi.compute_customer_intelligence(db, vendor_id),
        'segment_recommendations': bi.compute_segment_recommendations(db, vendor_id),
        'forecast': bi.compute_forecast_summary(db, vendor_id),
        'alerts': intelligence.alerts(db, vendor_id),
        'reorder': intelligence.replenishment_plan(db, vendor_id, 0.95, 7),
    }
