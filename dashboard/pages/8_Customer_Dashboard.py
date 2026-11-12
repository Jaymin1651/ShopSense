"""Customer dashboard (Milestone 3): my orders, spending and picks."""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui import TEAL, api, apply_style, currency, note, require_user  # noqa: E402

st.set_page_config(page_title='ShopSense | My account', page_icon='🛍️', layout='wide')
apply_style()
user = require_user('customer')

st.title('My account')
orders = api('GET', '/api/orders') or []
if not orders:
    st.info('You have no orders yet. Browse the shop and your spending and picks will show here.')
    st.stop()

catalogue = {p['id']: p for p in (api('GET', '/api/products') or [])}
frame = pd.DataFrame([{'order_id': o['id'], 'date': pd.to_datetime(o['created_at'], format='mixed', utc=True),
                       'status': o['status'],
                       'total': float(o['total']), 'items': sum(i['quantity'] for i in o['items'])} for o in orders])
placed = frame.loc[frame['status'] != 'cancelled']
lines = pd.DataFrame([{'product_id': i['product_id'], 'quantity': i['quantity'],
                       'amount': float(i['unit_price']) * i['quantity']} for o in orders if o['status'] != 'cancelled'
                      for i in o['items']])
lines['category'] = lines['product_id'].map(lambda p: catalogue.get(p, {}).get('category', 'Other'))

days_since = (pd.Timestamp.now(tz='UTC') - placed['date'].max()).days if len(placed) else None
c = st.columns(4)
c[0].metric('Orders', len(placed))
c[1].metric('Total spent', currency(placed['total'].sum()))
c[2].metric('Average order', currency(placed['total'].mean()))
c[3].metric('Last order', f'{days_since} days ago' if days_since is not None else '—')

left, right = st.columns([3, 2])
with left:
    st.subheader('Spending by month')
    monthly = placed.set_index('date')['total'].resample('ME').sum().tail(12)
    monthly.index = monthly.index.tz_localize(None)
    fig = go.Figure(go.Bar(x=monthly.index.strftime('%b %Y'), y=monthly.values, marker_color=TEAL,
                           hovertemplate='%{y:$,.2f}<extra></extra>'))
    fig.update_layout(height=280, yaxis_title='Spent')
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
with right:
    st.subheader('What you buy')
    cats = lines.groupby('category')['amount'].sum().sort_values(ascending=False).head(6)
    fig = go.Figure(go.Bar(x=cats.values, y=cats.index, orientation='h', marker_color=TEAL,
                           hovertemplate='%{x:$,.2f}<extra></extra>'))
    fig.update_layout(height=280, yaxis=dict(autorange='reversed'))
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

st.subheader('Picked for you')
recs = api('GET', '/api/recommendations/me', params={'limit': 4}) or []
cols = st.columns(4)
for col, r in zip(cols, recs):
    p = r['product']
    col.markdown(f"<div class='ss-rec'><b>{p['name']}</b><br>{currency(p['price'])}<br><span>{r['reason']}</span></div>",
                 unsafe_allow_html=True)
note('See more on the Picked for you page.')

st.subheader('Recent orders')
st.dataframe(frame.sort_values('date', ascending=False).head(15), hide_index=True, width='stretch',
             column_config={'order_id': 'Order', 'date': st.column_config.DatetimeColumn('Placed', format='D MMM YYYY'),
                            'status': 'Status', 'total': st.column_config.NumberColumn('Total', format='$%.2f'),
                            'items': 'Items'})
