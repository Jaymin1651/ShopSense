"""Inventory intelligence: stock runway, alerts, replenishment, forecasts, turnover."""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui import (AMBER, INK, MUTED, RED, TEAL, VIOLET, api, apply_style, currency,  # noqa: E402
                note, pill, require_user)

st.set_page_config(page_title='ShopSense | Inventory', page_icon='🛍️', layout='wide')
apply_style()
user = require_user('admin', 'vendor')

st.title('Inventory')
note('Stock levels, what will run out first, and how much to reorder. Demand comes from a weekly '
     'Random Forest trained on past orders; products with under 12 weeks of sales use an 8-week average.')

overview = api('GET', '/api/inventory/overview')
if not overview or not overview.get('products'):
    st.info('No products yet. Add products on the main page, or load the demo data with '
            '`python -m scripts.seed_milestone2`.')
    st.stop()

c = st.columns(6)
c[0].metric('Units in stock', f"{overview['units_in_stock']:,}")
c[1].metric('Low stock', overview['low_stock'])
c[2].metric('Out of stock', overview['out_of_stock'])
turn = overview.get('turnover_90d')
c[3].metric('Turnover, 90 days', f'{turn:.2f}×' if turn is not None else '—',
            help='Cost of goods sold ÷ average inventory value (units when costs are missing).')
c[4].metric('Demand, next 7 days', f"{overview['forecast_units_next_7_days']:,.0f}",
            help='Forecast demand summed over all products.')
c[5].metric('Products to reorder', overview['reorder_lines'],
            help=f"{overview['reorder_units']:,} units in total at a 95% service level.")

status = pd.DataFrame(api('GET', '/api/inventory/status') or [])

# ----------------------------------------------------------------- stock runway
st.subheader('Stock runway')
note('Days until each product sells out at forecast demand. The tick marks the supplier lead time: '
     'a bar that ends before its tick will run out before a new order can arrive.')
if not status.empty:
    runway = status.copy()
    runway['cover'] = runway['days_of_cover'].astype(float)
    runway['lead'] = runway['lead_time_days'].astype(float)
    runway = runway.loc[runway['cover'].notna() | (runway['current_stock'] <= 0)]
    runway['cover'] = runway['cover'].fillna(0)
    cap = 60
    runway['shown'] = runway['cover'].clip(upper=cap)
    runway['color'] = [RED if (s <= 0 or cv < ld) else AMBER if st_ == 'Low stock' else TEAL
                       for s, cv, ld, st_ in zip(runway['current_stock'], runway['cover'], runway['lead'], runway['status'])]
    runway = runway.sort_values('cover')
    left, right = st.columns([3, 1])
    with right:
        count = st.slider('Products shown', 5, max(5, len(runway)), min(20, len(runway)), key='runway_count')
        only_risk = st.toggle('Only products at risk', value=False)
    if only_risk:
        runway = runway.loc[runway['color'] != TEAL]
    view = runway.head(count).iloc[::-1]
    labels = [f"{n}  ·  {int(s)} left" for n, s in zip(view['name'], view['current_stock'])]
    fig = go.Figure()
    fig.add_bar(x=view['shown'], y=labels, orientation='h', marker_color=view['color'],
                customdata=view[['cover', 'lead', 'daily_demand']].to_numpy(),
                hovertemplate='%{customdata[0]:.1f} days of cover<br>lead time %{customdata[1]:.0f} days'
                              '<br>%{customdata[2]:.2f} units/day<extra></extra>')
    fig.add_scatter(x=view['lead'], y=labels, mode='markers', name='Lead time',
                    marker=dict(symbol='line-ns', size=18, line=dict(width=2.5, color=INK)),
                    hovertemplate='Lead time %{x:.0f} days<extra></extra>')
    reach = max(float(view['shown'].max() or 0), float(view['lead'].max() or 0)) * 1.12 + 1
    fig.update_layout(height=max(280, 26 * len(view) + 90), showlegend=False, bargap=0.35,
                      xaxis=dict(title='Days of cover', range=[0, min(reach, cap + 2)], ticksuffix='d', side='top'),
                      yaxis=dict(tickfont=dict(size=12)), margin=dict(t=50, b=10))
    if (view['cover'] > cap).any():
        fig.add_annotation(x=cap, y=-0.02, yref='paper', text=f'Bars stop at {cap} days', showarrow=False,
                           font=dict(color=MUTED, size=11), xanchor='right', yanchor='top')
    with left:
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    st.markdown(pill('Runs out before restock', RED) + pill('At or below reorder level', AMBER) +
                pill('Healthy', TEAL), unsafe_allow_html=True)

tabs = st.tabs(['Alerts', 'Reorder plan', 'Demand forecast', 'Turnover', 'Stock history', 'All stock'])

with tabs[0]:
    alerts = pd.DataFrame(api('GET', '/api/inventory/alerts') or [])
    if alerts.empty:
        st.success('No product is at or below its reorder level.')
    else:
        crit = int((alerts['severity'] == 'critical').sum())
        st.markdown(f"**{crit} critical**, {len(alerts) - crit} warning. Critical means out of stock or "
                    'expected to sell out before a new delivery arrives.')
        st.dataframe(alerts[['severity', 'name', 'current_stock', 'reorder_level', 'days_of_cover', 'lead_time_days',
                             'warehouse', 'message']],
                     hide_index=True, width='stretch',
                     column_config={'severity': 'Severity', 'name': 'Product', 'current_stock': 'In stock',
                                    'reorder_level': 'Reorder level', 'days_of_cover': 'Days of cover',
                                    'lead_time_days': 'Lead time (days)', 'warehouse': 'Warehouse',
                                    'message': st.column_config.TextColumn('What to do', width='large')})

with tabs[1]:
    a, b, _ = st.columns([1, 1, 2])
    service = a.select_slider('Service level', options=[0.80, 0.85, 0.90, 0.95, 0.975, 0.99], value=0.95,
                              format_func=lambda v: f'{v:.1%}'.replace('.0%', '%'),
                              help='Chance of not running out between deliveries. Higher means more safety stock.')
    review = b.number_input('Days between orders', 1, 60, 7)
    plan = pd.DataFrame(api('GET', '/api/inventory/replenishment',
                            params={'service_level': service, 'review_days': review}) or [])
    note('Order up to: forecast demand over lead time plus the review period, plus safety stock, and never '
         'below twice the reorder level. Products without sales history use the reorder-level rule.')
    if plan.empty:
        st.success('Nothing needs reordering at this service level.')
    else:
        total = plan['order_value'].fillna(0).sum() if 'order_value' in plan else 0
        st.markdown(f"**{len(plan)} products, {int(plan['reorder_qty'].sum()):,} units**"
                    + (f', about {currency(total)} at cost' if total else ''))
        st.dataframe(plan[['name', 'vendor', 'current_stock', 'daily_demand', 'lead_time_days', 'safety_stock',
                           'order_up_to', 'reorder_qty'] + (['order_value'] if 'order_value' in plan else [])],
                     hide_index=True, width='stretch',
                     column_config={'name': 'Product', 'vendor': 'Vendor', 'current_stock': 'In stock',
                                    'daily_demand': st.column_config.NumberColumn('Units/day', format='%.2f'),
                                    'lead_time_days': 'Lead time', 'safety_stock': 'Safety stock',
                                    'order_up_to': 'Order up to',
                                    'reorder_qty': st.column_config.NumberColumn('Order qty', format='%d'),
                                    'order_value': st.column_config.NumberColumn('Cost', format='$%.2f')})
        st.download_button('Download reorder plan (CSV)', plan.to_csv(index=False).encode(),
                           file_name='shopsense_reorder_plan.csv', mime='text/csv')

with tabs[2]:
    if status.empty:
        st.info('No products to forecast.')
    else:
        options = status.sort_values('name')
        pid = st.selectbox('Product', options['product_id'].tolist(),
                           format_func=lambda x: options.set_index('product_id').loc[x, 'name'])
        weeks = st.slider('Weeks ahead', 1, 12, 6)
        fc = api('GET', f'/api/inventory/forecast/{pid}', params={'weeks': weeks})
        if fc and fc.get('weekly'):
            hist = pd.DataFrame(fc['history'])
            fut = pd.DataFrame(fc['weekly'])
            fig = go.Figure()
            if not hist.empty:
                fig.add_scatter(x=hist['week'], y=hist['units'], name='Sold', mode='lines+markers',
                                line=dict(color=INK, width=2), marker=dict(size=4))
            fig.add_scatter(x=list(fut['week']) + list(fut['week'][::-1]), y=list(fut['upper']) + list(fut['lower'][::-1]),
                            fill='toself', fillcolor='rgba(91,75,196,0.14)', line=dict(width=0), name='Likely range',
                            hoverinfo='skip')
            start_x = [hist['week'].iloc[-1]] if not hist.empty else []
            start_y = [hist['units'].iloc[-1]] if not hist.empty else []
            fig.add_scatter(x=start_x + list(fut['week']), y=start_y + list(fut['forecast']), name='Forecast',
                            mode='lines+markers', line=dict(color=VIOLET, width=2.5, dash='dot'), marker=dict(size=6))
            fig.update_layout(height=360, yaxis_title='Units per week', hovermode='x unified')
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
            m = st.columns(4)
            m[0].metric('In stock', fc['current_stock'])
            m[1].metric('Forecast, next week', f"{fut['forecast'].iloc[0]:.0f} units")
            m[2].metric('Days of stock', fc['estimated_days_of_stock'] if fc['estimated_days_of_stock'] is not None else '—')
            m[3].metric('Sells out', f"week of {fc['stock_runs_out_week']}" if fc['stock_runs_out_week']
                        else f'not within {weeks} weeks')
            note(fc.get('note') or f"Method: pooled weekly Random Forest. Shaded area: {fc['interval'].lower()}")
        elif fc:
            st.info('This product has no sales yet, so there is nothing to forecast.')

with tabs[3]:
    days = st.select_slider('Period', options=[30, 60, 90, 180, 365], value=90, format_func=lambda d: f'{d} days')
    turnover = api('GET', '/api/inventory/turnover', params={'days': days})
    if turnover and turnover['products']:
        p = turnover['portfolio']
        note(f"Portfolio turnover over {days} days: <b>{p['turnover']}×</b> on a {p['basis']} basis. "
             f"{turnover['formula'].capitalize()}.")
        tdf = pd.DataFrame(turnover['products'])
        top = tdf.dropna(subset=['turnover']).head(15).iloc[::-1]
        fig = go.Figure(go.Bar(x=top['turnover'], y=top['name'], orientation='h', marker_color=TEAL,
                               hovertemplate='%{x:.2f}×<extra></extra>'))
        fig.update_layout(height=max(260, 24 * len(top) + 60), xaxis_title='Turnover in period', bargap=0.35)
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        st.dataframe(tdf, hide_index=True, width='stretch',
                     column_config={'product_id': None, 'name': 'Product', 'category': 'Category',
                                    'units_sold': 'Units sold', 'average_inventory_units': 'Avg units held',
                                    'turnover': 'Turnover', 'annualised_turnover': 'Per year',
                                    'cogs': st.column_config.NumberColumn('COGS', format='$%.2f'),
                                    'days_of_cover': 'Days of cover', 'basis': 'Basis'})

with tabs[4]:
    if not status.empty:
        pid = st.selectbox('Product ', status['product_id'].tolist(), key='ledger_product',
                           format_func=lambda x: status.set_index('product_id').loc[x, 'name'])
        moves = pd.DataFrame(api('GET', f'/api/inventory/movements/{pid}', params={'limit': 500}) or [])
        if moves.empty:
            st.info('No stock movements recorded.')
        else:
            moves['created_at'] = pd.to_datetime(moves['created_at'], format='mixed')
            current = int(status.set_index('product_id').loc[pid, 'current_stock'])
            moves = moves.sort_values('created_at', ascending=False)
            moves['stock_after'] = current - moves['delta'].shift(1, fill_value=0).cumsum()
            fig = go.Figure(go.Scatter(x=moves['created_at'], y=moves['stock_after'], line_shape='hv',
                                       line=dict(color=TEAL, width=2), fill='tozeroy',
                                       fillcolor='rgba(14,124,123,0.08)', hovertemplate='%{y} units<extra></extra>'))
            reorder = int(status.set_index('product_id').loc[pid, 'reorder_level'])
            fig.add_hline(y=reorder, line=dict(color=AMBER, dash='dash', width=1.5),
                          annotation_text='Reorder level', annotation_font_color=AMBER)
            fig.update_layout(height=300, yaxis_title='Units in stock')
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
            note(f'The latest {len(moves)} movements. The line rebuilds stock level after each sale, restock or adjustment.')
            st.dataframe(moves[['created_at', 'reason', 'delta', 'stock_after']], hide_index=True, width='stretch',
                         column_config={'created_at': 'When', 'reason': 'Reason', 'delta': 'Change',
                                        'stock_after': 'Stock after'})

with tabs[5]:
    if not status.empty:
        st.dataframe(status[['name', 'category', 'vendor', 'warehouse', 'current_stock', 'reorder_level', 'status',
                             'daily_demand', 'days_of_cover', 'demand_source']],
                     hide_index=True, width='stretch',
                     column_config={'name': 'Product', 'category': 'Category', 'vendor': 'Vendor',
                                    'warehouse': 'Warehouse', 'current_stock': 'In stock',
                                    'reorder_level': 'Reorder level', 'status': 'Status',
                                    'daily_demand': st.column_config.NumberColumn('Units/day', format='%.2f'),
                                    'days_of_cover': 'Days of cover', 'demand_source': 'Demand from'})
    warehouses = api('GET', '/api/warehouses') or []
    tree = api('GET', '/api/categories') or []
    w, cat = st.columns(2)
    with w:
        st.subheader('Warehouses')
        if warehouses:
            st.dataframe(pd.DataFrame(warehouses)[['name', 'location']], hide_index=True, width='stretch')
        else:
            st.caption('No warehouses yet.')
        if user['role'] == 'admin':
            with st.form('add_warehouse', clear_on_submit=True):
                name = st.text_input('Warehouse name')
                location = st.text_input('Location')
                if st.form_submit_button('Add warehouse') and api('POST', '/api/warehouses',
                                                                   json={'name': name, 'location': location}):
                    st.rerun()
    with cat:
        st.subheader('Categories')
        if tree:
            for node in tree:
                kids = ', '.join(k['name'] for k in node['children']) or 'no subcategories'
                st.markdown(f"**{node['name']}**: {kids}")
        else:
            st.caption('No category hierarchy yet.')
        if user['role'] == 'admin':
            with st.form('add_category', clear_on_submit=True):
                name = st.text_input('Category name')
                parents = {n['name']: n['id'] for n in tree}
                parent = st.selectbox('Parent', ['None'] + list(parents))
                if st.form_submit_button('Add category') and api('POST', '/api/categories', json={
                        'name': name, 'parent_id': parents.get(parent)}):
                    st.rerun()
st.markdown(f'<p class="ss-note" style="margin-top:2rem;color:{MUTED}">Signed in as {user["email"]}. '
            f'{"All vendors." if user["role"] == "admin" else "Showing your products only."}</p>',
            unsafe_allow_html=True)
