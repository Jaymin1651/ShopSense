"""MLflow model registry and automated workflow runs (Milestone 3)."""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui import AMBER, TEAL, api, api_live, apply_style, note, pill, require_user  # noqa: E402

st.set_page_config(page_title='ShopSense | Models & workflows', page_icon='🛍️', layout='wide')
apply_style()
require_user('admin')

st.title('Models & workflows')
note('Every model is trained, logged and versioned in the MLflow registry. A new version only becomes '
     '<b>production</b> if it scores at least as well as the current one; otherwise it is kept as the '
     '<b>challenger</b>. Workflows retrain models, refresh analytics and write reports on a schedule.')

models_tab, runs_tab, flows_tab = st.tabs(['Model registry', 'Training runs', 'Workflows'])

with models_tab:
    reg = api('GET', '/api/mlops/models') or {}
    if not reg.get('enabled'):
        st.info('MLflow is switched off (MLFLOW_ENABLED=0).')
    elif not reg.get('models'):
        st.info('No models registered yet. Run the retrain_forecast and retrain_churn workflows.')
    key_metric = {'InventoryForecast': ('category_accuracy_pct', 'Category accuracy (%)'),
                  'ChurnRisk': ('roc_auc', 'ROC AUC')}
    for m in reg.get('models', []):
        metric, label = key_metric.get(m['name'], (None, None))
        st.subheader(m['name'])
        prod = m['production_version']
        st.markdown((f"Serving: **version {prod}** · {m['total_versions']} versions registered" if prod
                     else 'No production version yet.'))
        versions = pd.DataFrame(m['versions'])
        if versions.empty:
            continue
        versions['alias'] = versions['aliases'].map(lambda a: ', '.join(a) or '—')
        versions['score'] = versions['metrics'].map(lambda x: x.get(metric))
        chart = versions.sort_values('version')
        colors = [TEAL if 'production' in a else AMBER if 'challenger' in a else '#C9CED8' for a in chart['aliases']]
        fig = go.Figure(go.Bar(x=[f'v{v}' for v in chart['version']], y=chart['score'], marker_color=colors,
                               text=[f'{v:.3g}' if v is not None else '' for v in chart['score']],
                               textposition='outside'))
        fig.update_layout(height=220, yaxis_title=label, margin=dict(t=20, b=30))
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        st.markdown(pill('production', TEAL) + pill('challenger', AMBER) + pill('older version', '#8A94A6'),
                    unsafe_allow_html=True)
        st.dataframe(versions[['version', 'alias', 'score', 'decision', 'created', 'run_id']], hide_index=True,
                     width='stretch', column_config={'version': 'Version', 'alias': 'Alias', 'score': label,
                                                     'decision': 'Decision', 'created': 'Registered',
                                                     'run_id': 'MLflow run'})

with runs_tab:
    runs = api('GET', '/api/mlops/runs', params={'limit': 30}) or []
    if runs:
        table = pd.DataFrame([{'started': r['start'], 'experiment': r['experiment'].replace('shopsense-', ''),
                               'run': r['run_name'], 'status': r['status'],
                               'main metrics': ', '.join(f'{k} {v:g}' for k, v in list(r['metrics'].items())[:3])}
                              for r in runs])
        st.dataframe(table, hide_index=True, width='stretch')
        note('Open the full MLflow UI with <code>mlflow ui --backend-store-uri sqlite:///mlflow.db</code> '
             '(port 5000) to compare runs and download models.')
    else:
        st.info('No training runs logged yet.')

with flows_tab:
    @st.fragment(run_every=10)
    def workflow_table():
        flows = api_live('/api/workflows') or []
        if not flows:
            return
        total = sum(f['runs'] for f in flows)
        ok = sum(f['success'] for f in flows)
        c = st.columns(3)
        c[0].metric('Workflow runs', f'{total:,}')
        c[1].metric('Success rate', f'{ok / total * 100:.1f}%' if total else '—')
        c[2].metric('Failed runs', total - ok)
        frame = pd.DataFrame(flows)
        st.dataframe(frame[['job', 'schedule', 'runs', 'success_rate_pct', 'avg_duration_ms', 'last_run', 'description']],
                     hide_index=True, width='stretch',
                     column_config={'job': 'Workflow', 'schedule': 'Schedule', 'runs': 'Runs',
                                    'success_rate_pct': st.column_config.NumberColumn('Success', format='%.0f%%'),
                                    'avg_duration_ms': st.column_config.NumberColumn('Avg time', format='%d ms'),
                                    'last_run': 'Last run', 'description': 'What it does'})
        recent = api_live('/api/workflows/runs', params={'limit': 15}) or []
        if recent:
            st.markdown('**Latest runs**')
            rows = pd.DataFrame(recent)
            rows['status'] = rows['status'].map({'success': '✓ success', 'failed': '✗ failed'}).fillna(rows['status'])
            st.dataframe(rows[['started_at', 'job', 'trigger', 'status', 'attempts', 'duration_ms', 'message']],
                         hide_index=True, width='stretch',
                         column_config={'started_at': 'Started', 'job': 'Workflow', 'trigger': 'Trigger',
                                        'status': 'Result', 'attempts': 'Attempts',
                                        'duration_ms': st.column_config.NumberColumn('Time', format='%d ms'),
                                        'message': 'Message'})

    workflow_table()
    st.markdown('**Run a workflow now**')
    flows = api('GET', '/api/workflows') or []
    cols = st.columns(3)
    for i, f in enumerate(flows):
        if cols[i % 3].button(f"Run {f['job'].replace('_', ' ')}", key=f"run_{f['job']}", width='stretch'):
            if api('POST', f"/api/workflows/{f['job']}/run"):
                st.toast(f"Started {f['job']}. The table updates when it finishes.")
