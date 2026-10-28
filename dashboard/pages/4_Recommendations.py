"""Personalised picks for customers; click-through and offline quality for staff."""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui import GRID, MUTED, TEAL, api, apply_style, currency, note, require_user  # noqa: E402

st.set_page_config(page_title='ShopSense | Recommendations', page_icon='🛍️', layout='wide')
apply_style()
user = require_user()

if user['role'] == 'customer':
    st.title('Picked for you')
    note('Based on what you and shoppers with similar taste have viewed and bought. '
         'Products you already bought are left out.')
    recs = api('GET', '/api/recommendations/me', params={'limit': 12}) or []
    if not recs:
        st.info('Browse a few products or place an order, and suggestions will appear here.')
        st.stop()
    shown = tuple(r['product']['id'] for r in recs)
    if st.session_state.get('rec_logged') != shown:
        api('POST', '/api/recommendations/feedback', quiet=True, json={'event': 'impression', 'product_ids': list(shown)})
        st.session_state['rec_logged'] = shown
    cart = st.session_state.setdefault('cart', {})
    for r in recs:
        p = r['product']
        row = st.columns([5, 2, 2])
        row[0].markdown(f"<div class='ss-rec'><b>{p['name']}</b><br><span>{r['reason']}</span></div>",
                        unsafe_allow_html=True)
        row[1].markdown(f"<div class='ss-rec'>{currency(p['price'])}<br><span>{p['category']} · "
                        f"{p['quantity']} in stock</span></div>", unsafe_allow_html=True)
        if row[2].button('Add to cart', key=f"rec_cart_{p['id']}", width='stretch'):
            api('POST', '/api/recommendations/feedback', quiet=True, json={'event': 'click', 'product_ids': [p['id']]})
            api('POST', '/api/customers/interactions', quiet=True, json={'product_id': p['id'], 'event_type': 'cart'})
            cart[p['id']] = min(cart.get(p['id'], 0) + 1, p['quantity'])
            st.toast(f"Added {p['name']} to your cart. Check out from the main page.")
    st.stop()

st.title('Recommendations')
note('How the recommendation engine performs: live click-through from customers, and offline accuracy '
     'measured on purchases the model had not seen.')

if user['role'] == 'admin':
    live = api('GET', '/api/recommendations/metrics')
    if live:
        c = st.columns(4)
        c[0].metric('Times shown', f"{live['impressions']:,}")
        c[1].metric('Clicks', f"{live['clicks']:,}")
        c[2].metric('Click-through rate', f"{live['ctr_pct']}%" if live['ctr_pct'] is not None else '—')
        c[3].metric('Purchases after a click', live['purchases_after_click'])
        if live['by_product']:
            st.dataframe(pd.DataFrame(live['by_product']), hide_index=True, width='stretch',
                         column_config={'product_id': None, 'product': 'Product', 'impressions': 'Shown',
                                        'clicks': 'Clicks', 'ctr_pct': st.column_config.NumberColumn('CTR', format='%.1f%%')})
        else:
            st.caption('No customer has seen recommendations yet. Sign in as a customer and open this page to start tracking.')

report = api('GET', '/api/evaluation/milestone2')
rec = report and report.get('synthetic', {}).get('recommendation')
if rec:
    st.subheader('Offline evaluation')
    k10 = rec['k10']
    note(f"Trained on events before {k10['cutoff']}; scored on products each of {k10['test_customers']:,} "
         f"customers newly bought after it. {k10['relevance_definition']}.")
    rows = []
    for key in ('k5', 'k10'):
        k = rec[key]['k']
        for name, m in rec[key]['models'].items():
            rows.append({'model': 'Hybrid engine' if name == 'hybrid' else 'Most popular (baseline)', 'k': f'Top {k}',
                         'Hit rate': m[f'hit_rate_at_{k}_pct'], 'Precision': m[f'precision_at_{k}_pct'],
                         'Recall': m[f'recall_at_{k}_pct'], 'Coverage': m['catalogue_coverage_pct']})
    table = pd.DataFrame(rows)
    fig = go.Figure()
    for name, color in (('Hybrid engine', TEAL), ('Most popular (baseline)', '#AEB6C4')):
        part = table.loc[table['model'] == name]
        fig.add_bar(x=part['k'], y=part['Hit rate'], name=name, marker_color=color,
                    text=[f'{v:.1f}%' for v in part['Hit rate']], textposition='outside')
    fig.add_hline(y=75, line=dict(color=MUTED, dash='dash', width=1), annotation_text='Target 75%',
                  annotation_font_color=MUTED,
                  annotation_position='top left')
    fig.update_layout(barmode='group', height=340, yaxis=dict(title='Hit rate (%)', range=[0, 100], gridcolor=GRID))
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    st.dataframe(table, hide_index=True, width='stretch',
                 column_config={c: st.column_config.NumberColumn(c, format='%.1f%%')
                                for c in ('Hit rate', 'Precision', 'Recall', 'Coverage')})
else:
    st.info('Run `python -m scripts.evaluate_milestone2` on the API server to add offline results here.')
