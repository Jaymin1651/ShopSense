"""Customer behaviour analytics and K-Means segments."""
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui import INK, SEGMENT_COLORS, TEAL, VIOLET, api, apply_style, currency, note, require_user  # noqa: E402

st.set_page_config(page_title='ShopSense | Customers', page_icon='🛍️', layout='wide')
apply_style()
user = require_user('admin', 'vendor')

st.title('Customers')
note('How customers buy, who your best customers are, and which groups they fall into.'
     + ('' if user['role'] == 'admin' else ' Figures cover orders that include your products.'))

data = api('GET', '/api/customer-analytics/overview')
if not data or not data['summary']['customers']:
    st.info('Customer analytics appear after the first orders are placed.')
    st.stop()
s = data['summary']
c = st.columns(5)
c[0].metric('Customers who bought', f"{s['customers']:,}")
c[1].metric('Average spend per customer', currency(s['average_spending']),
            help=f"Median {currency(s['median_spending'])}: a few big spenders pull the average up.")
c[2].metric('Average order value', currency(s['average_order_value']))
c[3].metric('Bought more than once', f"{s['repeat_rate_pct']}%")
c[4].metric('Median days since last order', s['median_recency_days'])

seg_tab, behaviour_tab, top_tab = st.tabs(['Segments', 'Buying behaviour', 'Top customers'])

with seg_tab:
    a, b, _ = st.columns([1.3, 1, 2.5])
    auto = a.toggle('Pick k automatically', value=False, help='Pick the number of groups with the best silhouette.')
    k = b.number_input('Number of segments', 2, 6, 3, disabled=auto)
    seg = api('GET', '/api/customer-analytics/segments', params={'k': int(k), 'auto_k': auto})
    if seg and not seg.get('available'):
        st.info(seg.get('reason', 'Not enough customers to segment yet.'))
    elif seg:
        m = seg['metrics']
        note(f"K-Means with k={seg['k']} on days since last order, number of orders and total spend "
             '(log-scaled and standardised). Segment names come from each group’s average value, '
             'not from the cluster number.')
        q = st.columns(4)
        q[0].metric('Silhouette', f"{m['silhouette']:.2f}", help='Separation between groups, from -1 to 1. Higher is better.')
        q[1].metric('Stability', f"{m['stability_ari']:.2f}" if m.get('stability_ari') is not None else '—',
                    help='Adjusted Rand index between this clustering and re-fits on resampled customers. 1 = identical.')
        q[2].metric('Davies-Bouldin', f"{m['davies_bouldin']:.2f}", help='Lower is better.')
        q[3].metric('Best k by silhouette', max(m['silhouette_by_k'], key=m['silhouette_by_k'].get))

        profiles = pd.DataFrame(seg['profiles'])
        order = profiles['segment'].tolist()
        colors = {name: SEGMENT_COLORS[i % len(SEGMENT_COLORS)] for i, name in enumerate(order)}
        points = pd.DataFrame(seg['points'])
        left, right = st.columns([3, 2])
        with left:
            fig = px.scatter(points, x='orders', y='total_spent', color='segment', log_x=True, log_y=True,
                             category_orders={'segment': order}, color_discrete_map=colors, opacity=0.65,
                             hover_data={'recency_days': True, 'customer_id': True},
                             labels={'orders': 'Orders (log scale)', 'total_spent': 'Total spend (log scale)',
                                     'recency_days': 'Days since last order', 'segment': 'Segment'})
            fig.update_traces(marker=dict(size=7, line=dict(width=0)))
            fig.update_layout(height=420, xaxis=dict(dtick=1), yaxis=dict(dtick=1))
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        with right:
            fig = go.Figure(go.Bar(x=profiles['customers'], y=profiles['segment'], orientation='h',
                                   marker_color=[colors[n] for n in profiles['segment']],
                                   text=[f'{p}%' for p in profiles['share_pct']], textposition='inside',
                                   insidetextanchor='end', textfont=dict(color='white'),
                                   hovertemplate='%{x} customers<extra></extra>'))
            fig.update_layout(height=420, yaxis=dict(autorange='reversed'), xaxis_title='Customers')
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        st.dataframe(profiles[['segment', 'description', 'customers', 'share_pct', 'avg_orders', 'avg_spent',
                               'avg_order_value', 'avg_recency_days']],
                     hide_index=True, width='stretch',
                     column_config={'segment': 'Segment', 'description': st.column_config.TextColumn('Who they are', width='large'),
                                    'customers': 'Customers', 'share_pct': st.column_config.NumberColumn('Share', format='%.1f%%'),
                                    'avg_orders': 'Avg orders', 'avg_spent': st.column_config.NumberColumn('Avg spend', format='$%.0f'),
                                    'avg_order_value': st.column_config.NumberColumn('Avg order', format='$%.0f'),
                                    'avg_recency_days': 'Avg days since last order'})

with behaviour_tab:
    left, right = st.columns(2)
    with left:
        st.subheader('Orders per customer')
        freq = pd.DataFrame(data['frequency'])
        fig = go.Figure(go.Bar(x=freq['bucket'], y=freq['customers'], marker_color=TEAL))
        fig.update_layout(height=320, yaxis_title='Customers')
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    with right:
        st.subheader('From browsing to buying')
        f = data.get('funnel')
        if f and f['viewed']:
            fig = go.Figure(go.Funnel(y=['Viewed', 'Added to cart', 'Bought'],
                                      x=[f['viewed'], f['carted'], f['purchased']],
                                      marker=dict(color=[INK, VIOLET, TEAL]), textinfo='value'))
            fig.update_layout(height=320)
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
            note(f"Counted as customer–product pairs. {f['view_to_cart_pct']}% of viewed pairs were added to a cart; "
                 f"{f['cart_to_purchase_pct']}% of carted pairs were bought.")
        else:
            st.info('No browsing events recorded yet.')
    monthly = pd.DataFrame(data['monthly_active'])
    if not monthly.empty:
        st.subheader('Active customers by month')
        fig = go.Figure()
        fig.add_bar(x=monthly['month'], y=monthly['active_customers'], name='Customers who ordered', marker_color=TEAL)
        fig.add_scatter(x=monthly['month'], y=monthly['orders'], name='Orders', yaxis='y2',
                        line=dict(color=INK, width=2))
        fig.update_layout(height=320, yaxis=dict(title='Customers'),
                          yaxis2=dict(title='Orders', overlaying='y', side='right', showgrid=False))
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

with top_tab:
    top = pd.DataFrame(s['top_customers'])
    if not top.empty:
        st.dataframe(top, hide_index=True, width='stretch',
                     column_config={'customer_id': 'Customer ID', 'orders': 'Orders',
                                    'total_spent': st.column_config.ProgressColumn(
                                        'Total spend', format='$%.0f', min_value=0, max_value=float(top['total_spent'].max())),
                                    'average_order_value': st.column_config.NumberColumn('Avg order', format='$%.2f'),
                                    'recency_days': 'Days since last order'})
        note('Customers are shown by account ID only. Spend counts item value on placed orders.')
