"""Which products to promote to each customer segment.

For every K-Means segment, a product's *lift* is its share of the segment's
buyers divided by its share of all buyers. Lift 2.0 means the segment is twice
as likely to buy it as the average customer. Products need a minimum number
of buyers in the segment so a single purchase cannot top the list.
"""
from __future__ import annotations

import pandas as pd


def segment_recommendations(sales: pd.DataFrame, assignments: pd.DataFrame, products: pd.DataFrame,
                            top_n: int = 3, min_buyers: int = 5) -> list[dict]:
    """``assignments``: customer_id, segment. ``products``: product_id, name, category."""
    if sales.empty or assignments.empty:
        return []
    buyers = sales[['customer_id', 'product_id']].drop_duplicates().merge(assignments[['customer_id', 'segment']],
                                                                          on='customer_id')
    total_customers = buyers['customer_id'].nunique()
    overall = buyers.groupby('product_id')['customer_id'].nunique() / total_customers
    names = products.set_index('product_id')
    out = []
    for segment, grp in buyers.groupby('segment'):
        seg_customers = assignments.loc[assignments['segment'] == segment, 'customer_id'].nunique()
        counts = grp.groupby('product_id')['customer_id'].nunique()
        share = counts / seg_customers
        table = pd.DataFrame({'buyers': counts, 'segment_share': share, 'overall_share': overall.reindex(counts.index)})
        table = table.loc[table['buyers'] >= min_buyers]
        table['lift'] = table['segment_share'] / table['overall_share']
        table = table.sort_values(['lift', 'buyers'], ascending=False).head(top_n)
        picks = [{'product_id': int(pid), 'product': str(names.loc[pid, 'name']) if pid in names.index else f'#{pid}',
                  'category': str(names.loc[pid, 'category']) if pid in names.index else '',
                  'lift': round(float(r.lift), 2), 'segment_buyers_pct': round(float(r.segment_share) * 100, 1)}
                 for pid, r in table.iterrows()]
        out.append({'segment': segment, 'customers': int(seg_customers), 'recommendations': picks})
    return out
