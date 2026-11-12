"""Milestone 3 evaluation results against the targets."""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui import AMBER, MUTED, TEAL, api, apply_style, note, pill, require_user  # noqa: E402

st.set_page_config(page_title='ShopSense | Milestone 3', page_icon='🛍️', layout='wide')
apply_style()
require_user('admin', 'vendor')

st.title('Milestone 3 results')
report = api('GET', '/api/evaluation/milestone3')
if not report or report.get('available') is False:
    st.info('No evaluation yet. With the API running, run `python -m scripts.evaluate_milestone3`.')
    st.stop()
env = report['environment']
note(f"Measured by <code>scripts/evaluate_milestone3.py</code>, {report['generated_at']}, against a running API "
     f"({env['database']}, {env['dataset']}). Each figure is computed by the script.")

for row in report['scorecard']:
    with st.container(border=True):
        left, mid, right = st.columns([3, 1, 1])
        left.markdown(f"**{row['criterion']}**  \n<span style='color:{MUTED}'>{row['metric']}</span>",
                      unsafe_allow_html=True)
        mid.metric('Measured', row['display'])
        right.markdown(f"<div style='padding-top:.4rem'>Target {row['target']}<br>"
                       + (pill('Met', TEAL) if row['met'] else pill('Not met', AMBER)) + '</div>', unsafe_allow_html=True)
        st.caption(row['context'])

lat = report['latency']
st.subheader('API response time under load')
note(f"{lat['users']} simulated users for {lat['duration_s']} s, plus {lat['write_rate_per_s']} new orders per "
     f"second, {lat['requests']:,} requests, {lat['error_rate_pct']}% errors. Bars show the 95th percentile per endpoint.")
eps = pd.DataFrame(lat['endpoints']).sort_values('p95_ms')
fig = go.Figure(go.Bar(x=eps['p95_ms'], y=eps['path'], orientation='h',
                       marker_color=[TEAL if v <= 300 else AMBER for v in eps['p95_ms']],
                       customdata=eps[['p50_ms', 'p99_ms', 'requests']].to_numpy(),
                       hovertemplate='p95 %{x:.0f} ms<br>p50 %{customdata[0]:.0f} ms · p99 %{customdata[1]:.0f} ms'
                                     '<br>%{customdata[2]} requests<extra></extra>'))
fig.add_vline(x=300, line=dict(color=MUTED, dash='dash', width=1), annotation_text='Target 300 ms',
              annotation_font_color=MUTED, annotation_position='top')
fig.update_layout(height=max(320, 26 * len(eps) + 80), xaxis_title='95th percentile (ms)')
st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

c = report['consistency']
w = report['workflows']
a, b = st.columns(2)
with a:
    st.subheader('Dashboard data consistency')
    note(f"{c['checks']} checks while {c['writes']} orders were placed. Each check compares the dashboard's live "
         f"numbers with a direct database count at the same moment.")
    st.metric('Consistent reads', f"{c['consistency_pct']}%", f"{c['consistent']} of {c['checks']}", delta_color='off')
    st.metric('Time for a new order to appear', f"{c['visibility_ms_p95']:.0f} ms (p95)",
              f"dashboard refreshes every {c['dashboard_refresh_s']} s", delta_color='off')
with b:
    st.subheader('Automated workflows')
    note(f"Real APScheduler run for {w['duration_s']} s with every job triggered every {w['every_s']} s, "
         'plus one run of each job on demand.')
    st.metric('Successful runs', f"{w['success_rate_pct']}%", f"{w['success']} of {w['runs']}", delta_color='off')
    st.dataframe(pd.DataFrame(w['jobs'])[['job', 'runs', 'success', 'failed', 'avg_duration_ms']], hide_index=True,
                 width='stretch', column_config={'job': 'Workflow', 'avg_duration_ms': 'Avg ms'})
