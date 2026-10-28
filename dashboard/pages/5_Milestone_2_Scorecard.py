"""Milestone 2 evaluation targets against measured results."""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui import AMBER, MUTED, TEAL, VIOLET, api, apply_style, note, pill, require_user  # noqa: E402

st.set_page_config(page_title='ShopSense | Milestone 2', page_icon='🛍️', layout='wide')
apply_style()
require_user('admin', 'vendor')

st.title('Milestone 2 results')
report = api('GET', '/api/evaluation/milestone2')
if not report or report.get('available') is False:
    st.info('No evaluation yet. Run `python -m scripts.evaluate_milestone2` (add `--olist` for real-data checks).')
    st.stop()
note(f"Measured on held-out data by <code>scripts/evaluate_milestone2.py</code>, {report['generated_at']}. "
     'Each figure is computed by the script; nothing is entered by hand.')

for row in report['scorecard']:
    with st.container(border=True):
        left, mid, right = st.columns([3, 1, 1])
        left.markdown(f"**{row['criterion']}**  \n<span style='color:{MUTED}'>{row['metric']}</span>",
                      unsafe_allow_html=True)
        value = row['value']
        mid.metric('Measured', f'{value}%' if 'pct' in row['metric'] or '%' in row['target'] else value)
        right.markdown(f"<div style='padding-top:.4rem'>Target {row['target']}<br>"
                       + (pill('Met', TEAL) if row['met'] else pill('Not met', AMBER)) + '</div>',
                       unsafe_allow_html=True)
        st.caption(row['context'])

syn = report['synthetic']
st.subheader('Forecasting: model against simple baselines')
note('Forecast accuracy = 1 − WAPE on the last 12 weeks, forecasting one week ahead at a time. '
     'Accuracy rises as sales are grouped: single products are noisy, the whole store is smooth.')
levels = list(syn['forecasting'].items())
if 'olist' in report:
    levels += [(f'Olist {k}', v) for k, v in report['olist']['forecasting'].items()]
names = {'random_forest': ('Random Forest', TEAL), 'moving_average_4': ('4-week average', VIOLET),
         'naive': ('Last week', '#AEB6C4'), 'seasonal_naive': ('Same week last year', '#D5DAE3')}
fig = go.Figure()
labels = [lvl.replace('_', ' ') for lvl, _ in levels]
for key, (label, color) in names.items():
    fig.add_bar(x=labels, y=[res['methods'][key]['accuracy_pct'] for _, res in levels], name=label, marker_color=color)
fig.add_hline(y=80, line=dict(color=MUTED, dash='dash', width=1), annotation_text='Target 80%',
              annotation_font_color=MUTED,
                  annotation_position='top left')
fig.update_layout(barmode='group', height=380, yaxis=dict(title='Accuracy (%)', range=[0, 100]))
st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

st.subheader('Segmentation quality')
rows = []
for key, res in syn['segmentation'].items():
    m = res['metrics']
    rows.append({'Run': f"Synthetic, k={res['k']}", 'Silhouette': m['silhouette'], 'Stability': m['stability_ari'],
                 'Davies-Bouldin': m['davies_bouldin'], 'Matches simulated personas (ARI)': m.get('persona_recovery_ari')})
if 'olist' in report:
    m = report['olist']['segmentation']['metrics']
    rows.append({'Run': f"Olist real customers, k={report['olist']['segmentation']['k']}", 'Silhouette': m['silhouette'],
                 'Stability': m['stability_ari'], 'Davies-Bouldin': m['davies_bouldin'],
                 'Matches simulated personas (ARI)': None})
st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
note('Silhouette measures how cleanly groups separate; stability measures whether the same groups come back '
     'when customers are resampled. Purchase behaviour is a continuum, so silhouette scores of 0.3–0.5 are normal.')

if 'olist' in report:
    st.caption(f"Real-data check: {report['olist']['dataset']}. "
               f"Recommendations not evaluated on Olist: {report['olist']['recommendation']['reason']}")
