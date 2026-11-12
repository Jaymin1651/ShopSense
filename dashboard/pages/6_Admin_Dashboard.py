"""Admin business-intelligence dashboard (Milestone 3): live KPIs, revenue, vendors, customers, exports."""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui import (AMBER, INK, MUTED, RED, SEGMENT_COLOR, TEAL, api, api_live, apply_style,  # noqa: E402
                currency, currency_short, download, note, require_user)

st.set_page_config(page_title='ShopSense | BI dashboard', page_icon='🛍️', layout='wide')
apply_style()
user = require_user('admin')

st.title('Business intelligence')
note('Live marketplace numbers refresh every 5 seconds. Panels below come from analytics snapshots that are '
     'recomputed whenever the data changes and by the scheduled workflows.')


@st.fragment(run_every=5)
def live_strip():
    k = api_live('/api/live/kpis')
    if not k:
        st.warning('Live KPIs are not available.')
        return
    c = st.columns(6)
    c[0].metric('GMV', currency_short(k['gmv']), help=f"Exact: {currency(k['gmv'])}")
    c[1].metric('Orders', f"{k['orders']:,}")
    c[2].metric('Avg order value', currency(k['average_order_value']))
    c[3].metric('Customers', f"{k['customers']:,}")
    c[4].metric('Orders today', f"{k['orders_today']:,}", help=f"{k['orders_last_hour']} in the last hour")
    c[5].metric('Low stock', k['low_stock_products'], help=f"{k['out_of_stock_products']} out of stock")
    stamp = datetime.fromisoformat(k['as_of']).strftime('%H:%M:%S')
    st.markdown(f"<p class='ss-note'><span style='color:{TEAL}'>●</span> Live · updated {stamp} UTC · "
                f"data version {k['data_version'].split('-')[0]} orders</p>", unsafe_allow_html=True)


live_strip()

rev = api('GET', '/api/revenue/overview')
if not rev or not rev.get('monthly'):
    st.info('No orders yet. Load demo data with `python -m scripts.seed_milestone2`.')
    st.stop()

# -------------------------------------------------------------- headline row
g = rev['growth']
left, right = st.columns([3, 2])
with left:
    st.subheader('Revenue trend')
    daily = pd.DataFrame(rev['daily'])
    fig = go.Figure()
    fig.add_bar(x=daily['period'], y=daily['gmv'], name='GMV per day', marker_color='rgba(14,124,123,0.35)')
    fig.add_scatter(x=daily['period'], y=daily['gmv_7d_avg'], name='7-day average', line=dict(color=TEAL, width=2.5))
    fig.update_layout(height=300, yaxis_title='GMV', hovermode='x unified')
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
with right:
    st.subheader('Growth')
    a, b = st.columns(2)
    a.metric('Last 30 days', currency_short(g['last_30_days_gmv']),
             f"{g['growth_30d_pct']:+.1f}% vs prior 30" if g['growth_30d_pct'] is not None else None)
    month = pd.Period(g['last_month']).strftime('%B %Y') if g['last_month'] else 'Last month'
    b.metric(month, currency_short(g['last_month_gmv']),
             f"{g['month_over_month_pct']:+.1f}% m/m" if g['month_over_month_pct'] is not None else None)
    p = rev['pareto_products']
    st.metric('Top 20% of products earn', f"{p['top_20_pct_share']}% of GMV",
              help=f"{p['top_items']} of {p['items']} products. A high share means revenue depends on few products.")

# ---------------------------------------------------- mockup panels (3 across)
seg_col, rec_col, fc_col = st.columns(3)
ci = api('GET', '/api/customer-intelligence/overview') or {}
picks = (api('GET', '/api/recommendations/segments') or {}).get('items', [])
fc = api('GET', '/api/forecast/summary') or {}
with seg_col:
    st.subheader('Customer segments')
    if ci.get('available') and ci['by_segment']:
        segs = pd.DataFrame(ci['by_segment']).sort_values('customers', ascending=False)
        for row in segs.itertuples():
            st.markdown(f"<div class='ss-rec'><b style='color:{SEGMENT_COLOR.get(row.segment, INK)}'>{row.segment}</b> · "
                        f"{row.customers:,} customers<br><span>Churn risk {row.avg_churn:.0%} · expected value "
                        f"{currency_short(row.value_12m)} in 12 months</span></div>", unsafe_allow_html=True)
    else:
        st.caption(ci.get('reason', 'Not enough customers yet.'))
with rec_col:
    st.subheader('Recommendation engine')
    if picks:
        for s in picks:
            top = s['recommendations'][0] if s['recommendations'] else None
            if top:
                why = (f"{top['lift']:.1f}× more likely than the average customer" if top['lift'] >= 1.05
                       else f"bought by {top['segment_buyers_pct']:.0f}% of this group")
                st.markdown(f"<div class='ss-rec'><b>{s['segment']}</b> → {top['product']}<br><span>{why}</span></div>",
                            unsafe_allow_html=True)
    else:
        st.caption('Segment picks appear once there are enough customers.')
with fc_col:
    st.subheader(f"Inventory forecast, {fc.get('weeks', 4)} weeks")
    items = pd.DataFrame(fc.get('products', [])).head(6)
    if not items.empty:
        for row in items.itertuples():
            color = RED if row.projected_stock < 0 else AMBER if row.projected_stock < row.reorder_level else TEAL
            st.markdown(f"<div class='ss-rec'><b>{row.name}</b>: predicted stock "
                        f"<b style='color:{color}'>{row.projected_stock:.0f}</b> units<br><span>{row.current_stock} now, "
                        f"{row.forecast_units:.0f} expected to sell</span></div>", unsafe_allow_html=True)
        st.caption(f"Model: {fc.get('source')}")

# ---------------------------------------------------------------------- tabs
t_rev, t_ven, t_cus, t_exp = st.tabs(['Revenue', 'Vendor benchmarking', 'Customer intelligence', 'Exports'])

with t_rev:
    monthly = pd.DataFrame(rev['monthly'])
    fig = go.Figure()
    partial = monthly.get('partial', pd.Series(False, index=monthly.index)).fillna(False)
    fig.add_bar(x=monthly['period'], y=monthly['gmv'], name='GMV',
                marker_color=['#9FCFCE' if p else TEAL for p in partial])
    fig.add_scatter(x=monthly['period'], y=monthly['growth_pct'], name='Growth %', yaxis='y2',
                    line=dict(color=INK, width=2), mode='lines+markers')
    fig.update_layout(height=340, yaxis=dict(title='GMV'),
                      yaxis2=dict(title='Growth %', overlaying='y', side='right', showgrid=False, ticksuffix='%'))
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    if partial.any():
        note('The lighter bar is the current month so far; it gets a growth figure when the month ends.')
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('**Category mix, last 90 days**')
        cats = pd.DataFrame(rev['categories'])
        fig = go.Figure(go.Bar(x=cats['gmv'], y=cats['category'], orientation='h', marker_color=TEAL,
                               customdata=cats[['share_pct', 'growth_pct']].to_numpy(),
                               hovertemplate='%{x:$,.0f}<br>%{customdata[0]}% of GMV<br>growth %{customdata[1]}%<extra></extra>'))
        fig.update_layout(height=320, yaxis=dict(autorange='reversed'))
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    with c2:
        st.markdown('**Customer cohorts: share buying again**')
        coh = api('GET', '/api/revenue/cohorts') or {}
        if coh.get('matrix'):
            z = [[v if v is not None else None for v in row[1:7]] for row in coh['matrix']]
            fig = go.Figure(go.Heatmap(z=z, x=[f'+{a}m' for a in coh['ages'][1:7]], y=coh['cohorts'],
                                       colorscale=[[0, '#F3F5F8'], [1, TEAL]], zmin=0, zmax=60,
                                       hovertemplate='%{y}, %{x}: %{z}%<extra></extra>',
                                       colorbar=dict(ticksuffix='%', thickness=10)))
            fig.update_layout(height=320, yaxis=dict(autorange='reversed'))
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
            note(f"On average {coh['average_month_1_pct']}% of new customers buy again in their second month.")

with t_ven:
    bench = api('GET', '/api/revenue/benchmark') or {}
    vend = pd.DataFrame(bench.get('vendors', []))
    if not vend.empty:
        m = bench['marketplace']
        note(f"Last {bench['days']} days. Score = average percentile of GMV, growth, order value and repeat rate "
             f"(100 = best). Marketplace median growth {m['median_growth_pct']}%.")
        fig = go.Figure(go.Scatter(x=vend['growth_pct'], y=vend['gmv'], mode='markers+text', text=vend['vendor'],
                                   textposition='top center', marker=dict(size=vend['score'] / 4 + 8, color=TEAL,
                                                                          line=dict(width=1, color='white'))))
        fig.add_vline(x=m['median_growth_pct'] or 0, line=dict(color=MUTED, dash='dot', width=1))
        fig.update_layout(height=340, xaxis_title='Growth vs previous 90 days (%)', yaxis_title='GMV, last 90 days')
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        st.dataframe(vend[['rank', 'vendor', 'gmv', 'share_pct', 'growth_pct', 'aov', 'repeat_rate_pct',
                           'in_stock_rate_pct', 'score']] if 'in_stock_rate_pct' in vend else vend,
                     hide_index=True, width='stretch',
                     column_config={'rank': '#', 'vendor': 'Vendor',
                                    'gmv': st.column_config.NumberColumn('GMV', format='$%.0f'),
                                    'share_pct': st.column_config.NumberColumn('Share', format='%.1f%%'),
                                    'growth_pct': st.column_config.NumberColumn('Growth', format='%.1f%%'),
                                    'aov': st.column_config.NumberColumn('Avg order', format='$%.0f'),
                                    'repeat_rate_pct': st.column_config.NumberColumn('Repeat buyers', format='%.0f%%'),
                                    'in_stock_rate_pct': st.column_config.NumberColumn('In stock', format='%.0f%%'),
                                    'score': st.column_config.ProgressColumn('Score', min_value=0, max_value=100, format='%d')})

with t_cus:
    if ci.get('available'):
        mm = ci['model_metrics']
        q = st.columns(4)
        q[0].metric('High churn risk', f"{ci['risk_counts']['High']:,} customers")
        q[1].metric('Spend at risk', currency_short(ci['value_at_risk_12m']),
                    help='Lifetime spend of high-risk customers.')
        q[2].metric('Expected value, next 12 months', currency_short(ci['expected_value_12m_total']))
        q[3].metric('Churn model AUC', f"{mm['roc_auc']:.2f}",
                    f"recency-only rule {mm['baseline_recency_auc']:.2f}", delta_color='off')
        note(f"Churn = no order in the next {mm['horizon_days']} days. Logistic regression on recency, frequency, "
             f"spend and recent activity, tested on the window after {mm['test_cutoff']}.")
        risk = ci['risk_counts']
        fig = go.Figure(go.Bar(x=list(risk.values()), y=list(risk.keys()), orientation='h',
                               marker_color=[RED, AMBER, TEAL]))
        fig.update_layout(height=200, yaxis=dict(autorange='reversed'), xaxis_title='Customers')
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        st.markdown('**Most valuable customers at high risk**')
        st.dataframe(pd.DataFrame(ci['high_risk_customers']).head(15), hide_index=True, width='stretch',
                     column_config={'customer_id': 'Customer', 'segment': 'Segment', 'orders': 'Orders',
                                    'total_spent': st.column_config.NumberColumn('Spent', format='$%.0f'),
                                    'recency_days': 'Days since order',
                                    'churn_probability': st.column_config.ProgressColumn('Churn risk', min_value=0,
                                                                                          max_value=1, format='%.2f'),
                                    'expected_value_12m': st.column_config.NumberColumn('Value, 12 m', format='$%.0f')})
    else:
        st.info(ci.get('reason', 'Not enough customers yet.'))

with t_exp:
    note('Download the same numbers as a report. The scheduled workflow also writes these files every morning.')
    a, b = st.columns(2)
    if a.button('Prepare Excel report', width='stretch'):
        st.session_state['xlsx'] = download('/api/reports/business.xlsx')
    if b.button('Prepare PDF report', width='stretch'):
        st.session_state['pdf'] = download('/api/reports/business.pdf')
    if st.session_state.get('xlsx'):
        a.download_button('Download Excel', st.session_state['xlsx'], 'shopsense-business.xlsx', width='stretch',
                          mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    if st.session_state.get('pdf'):
        b.download_button('Download PDF', st.session_state['pdf'], 'shopsense-business.pdf', mime='application/pdf',
                          width='stretch')

meta = rev.get('meta', {})
freshness = 'up to date' if meta.get('fresh') else f"{meta.get('orders_behind', 0)} orders behind, refreshing"
st.markdown(f"<p class='ss-note' style='margin-top:1.5rem'>Analytics snapshot computed "
            f"{meta.get('computed_at', '')} · {freshness}</p>", unsafe_allow_html=True)
