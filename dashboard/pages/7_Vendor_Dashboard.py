"""Vendor business dashboard (Milestone 3): own sales, benchmark against the marketplace, forecast, exports."""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui import (AMBER, INK, MUTED, RED, TEAL, api, api_live, apply_style, currency, currency_short,  # noqa: E402
                download, note, require_user)

st.set_page_config(page_title='ShopSense | My business', page_icon='🛍️', layout='wide')
apply_style()
user = require_user('vendor')

st.title('My business')
note('Your own sales, how you compare with other vendors, and what to restock. Other vendors stay anonymous.')


@st.fragment(run_every=5)
def live_strip():
    k = api_live('/api/live/kpis')
    if not k:
        return
    c = st.columns(5)
    c[0].metric('Your GMV', currency_short(k['gmv']), help=f"Exact: {currency(k['gmv'])}")
    c[1].metric('Orders', f"{k['orders']:,}")
    c[2].metric('Avg order value', currency(k['average_order_value']))
    c[3].metric('Orders today', k['orders_today'])
    c[4].metric('Low stock', k['low_stock_products'], help=f"{k['out_of_stock_products']} out of stock")
    st.markdown(f"<p class='ss-note'><span style='color:{TEAL}'>●</span> Live · updated "
                f"{datetime.fromisoformat(k['as_of']).strftime('%H:%M:%S')} UTC</p>", unsafe_allow_html=True)


live_strip()

bench = api('GET', '/api/revenue/benchmark') or {}
you, market = bench.get('you'), bench.get('marketplace', {})
st.subheader('You and the marketplace')
if not you:
    st.info('Your benchmark appears after your first orders.')
else:
    note(f"Last {bench['days']} days. Percentile 100 means you lead the marketplace on that measure.")
    c = st.columns(4)
    c[0].metric('Rank by GMV', f"{you['rank']} of {market['vendors']}")
    c[1].metric('Share of marketplace GMV', f"{you['share_pct']}%")
    median = market.get('median_growth_pct')
    c[2].metric('Growth', f"{you['growth_pct']:+.1f}%" if you['growth_pct'] is not None else '—',
                help=f'Marketplace median: {median:+.1f}%' if median is not None else None)
    c[3].metric('Overall score', f"{you['score']:.0f} / 100")
    measures = [('GMV', 'gmv_percentile'), ('Growth', 'growth_pct_percentile'), ('Avg order value', 'aov_percentile'),
                ('Repeat buyers', 'repeat_rate_pct_percentile')]
    vals = [you[k] or 0 for _, k in measures]
    fig = go.Figure(go.Bar(x=vals, y=[m for m, _ in measures], orientation='h', text=[f'{v:.0f}' for v in vals],
                           textposition='outside', marker_color=[TEAL if v >= 50 else AMBER for v in vals]))
    fig.add_vline(x=50, line=dict(color=MUTED, dash='dot', width=1), annotation_text='median',
                  annotation_font_color=MUTED, annotation_position='top')
    fig.update_layout(height=240, xaxis=dict(range=[0, 110], title='Percentile among vendors'),
                      yaxis=dict(autorange='reversed'))
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    peers = bench.get('peer_gmv_distribution', [])
    if peers:
        fig = go.Figure()
        fig.add_scatter(x=peers, y=[0] * len(peers), mode='markers', marker=dict(size=14, color='#C9CED8'),
                        name='Other vendors', hovertemplate='%{x:$,.0f}<extra></extra>')
        fig.add_scatter(x=[you['gmv']], y=[0], mode='markers', marker=dict(size=20, color=TEAL), name='You',
                        hovertemplate='You: %{x:$,.0f}<extra></extra>')
        fig.update_layout(height=130, yaxis=dict(visible=False), xaxis=dict(title='GMV, last 90 days', tickformat='$,.0f'),
                          margin=dict(t=10, b=40), showlegend=True)
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

rev = api('GET', '/api/revenue/overview') or {}
left, right = st.columns(2)
with left:
    st.subheader('Your monthly revenue')
    monthly = pd.DataFrame(rev.get('monthly', []))
    if not monthly.empty:
        fig = go.Figure(go.Bar(x=monthly['period'], y=monthly['gmv'], marker_color=TEAL,
                               customdata=monthly['growth_pct'], hovertemplate='%{y:$,.0f}<br>%{customdata}%<extra></extra>'))
        fig.update_layout(height=300, yaxis_title='GMV')
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
with right:
    fc = api('GET', '/api/forecast/summary') or {}
    st.subheader(f"Stock in {fc.get('weeks', 4)} weeks")
    items = pd.DataFrame(fc.get('products', [])).head(10)
    if not items.empty:
        colors = [RED if p < 0 else AMBER if p < r else TEAL for p, r in zip(items['projected_stock'], items['reorder_level'])]
        fig = go.Figure(go.Bar(x=items['projected_stock'], y=items['name'], orientation='h', marker_color=colors,
                               hovertemplate='%{x:.0f} units<extra></extra>'))
        fig.add_vline(x=0, line=dict(color=INK, width=1))
        fig.update_layout(height=300, yaxis=dict(autorange='reversed'), xaxis_title='Predicted units left')
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        note('Red: runs out before the period ends. Amber: below the reorder level. Open Inventory for the reorder plan.')

st.subheader('Your report')
a, b = st.columns(2)
if a.button('Prepare Excel report', width='stretch'):
    st.session_state['vxlsx'] = download('/api/reports/business.xlsx')
if b.button('Prepare PDF report', width='stretch'):
    st.session_state['vpdf'] = download('/api/reports/business.pdf')
if st.session_state.get('vxlsx'):
    a.download_button('Download Excel', st.session_state['vxlsx'], 'my-shopsense-report.xlsx', width='stretch',
                      mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
if st.session_state.get('vpdf'):
    b.download_button('Download PDF', st.session_state['vpdf'], 'my-shopsense-report.pdf', mime='application/pdf',
                      width='stretch')
