"""Shared dashboard helpers: API client, theme, chart template and page guards."""
import os

import plotly.graph_objects as go
import plotly.io as pio
import requests
import streamlit as st

from session import resolve_user

API_URL = os.getenv('API_URL', 'http://localhost:8000').rstrip('/')

INK = '#1C2433'
MUTED = '#5A6478'
SURFACE = '#F3F5F8'
GRID = '#E3E7EE'
TEAL = '#0E7C7B'      # healthy stock, primary
AMBER = '#B7791F'     # at or below reorder level
RED = '#B42318'       # out of stock / runs out within lead time
VIOLET = '#5B4BC4'    # forecast values only
STATUS_COLORS = {'Available': TEAL, 'Low stock': AMBER, 'Out of stock': RED,
                 'warning': AMBER, 'critical': RED}
SEGMENT_COLORS = [TEAL, '#3B7EA1', '#8A94A6', AMBER, '#7A5C9E', RED]
FONT = '"IBM Plex Sans", "Source Sans 3", "Source Sans Pro", -apple-system, "Segoe UI", Roboto, sans-serif'

CSS = f'''<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap');
html, body, [class*="css"], .stMarkdown, .stDataFrame, button, input, textarea, select {{
  font-family: {FONT};
}}
.block-container {{padding-top: 2rem; max-width: 1240px;}}
h1 {{font-weight: 600; letter-spacing: -0.02em; font-size: 2rem;}}
h2, h3 {{font-weight: 600; letter-spacing: -0.01em;}}
[data-testid="stMetric"] {{padding: 2px 0 10px; border-bottom: 1px solid {GRID};}}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * {{font-family: {FONT}; font-variant-numeric: tabular-nums;
  font-weight: 600; font-size: 1.9rem;}}
[data-testid="stMetricLabel"] p {{color: {MUTED};}}
[data-testid="stDataFrame"] {{font-variant-numeric: tabular-nums;}}
.ss-note {{color: {MUTED}; font-size: .9rem; max-width: 72ch; margin: -.25rem 0 1rem;}}
.ss-pill {{display: inline-block; padding: 1px 9px; border-radius: 999px; font-size: .8rem;
          font-weight: 500; color: #fff; margin-right: 6px;}}
.ss-rec {{padding: 12px 0; border-bottom: 1px solid {GRID};}}
.ss-rec b {{font-weight: 600;}}
.ss-rec span {{color: {MUTED}; font-size: .9rem;}}
@media (prefers-reduced-motion: reduce) {{ * {{transition: none !important; animation: none !important;}} }}
</style>'''

pio.templates['shopsense'] = go.layout.Template(layout=dict(
    font=dict(family=FONT, color=INK, size=13),
    colorway=[TEAL, VIOLET, AMBER, '#3B7EA1', RED, '#8A94A6'],
    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
    xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID),
    yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID),
    margin=dict(l=10, r=10, t=30, b=40), hoverlabel=dict(font_family=FONT),
    legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0, title_text=''),
))
pio.templates.default = 'plotly_white+shopsense'


def apply_style():
    st.markdown(CSS, unsafe_allow_html=True)


def note(text: str):
    st.markdown(f'<p class="ss-note">{text}</p>', unsafe_allow_html=True)


def pill(label: str, color: str) -> str:
    return f'<span class="ss-pill" style="background:{color}">{label}</span>'


def api(method, path, quiet=False, **kwargs):
    """Call the ShopSense API with the signed-in token; show errors inline."""
    token = st.session_state.get('token')
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    try:
        r = requests.request(method, f'{API_URL}{path}', headers=headers, timeout=60, **kwargs)
        if r.status_code >= 400:
            try:
                detail = r.json().get('detail', r.text)
                if isinstance(detail, list):
                    detail = '; '.join(str(d.get('msg', d)) for d in detail)
            except ValueError:
                detail = r.text
            if not quiet:
                st.error(f'{r.status_code}: {detail}')
            return None
        content_type = r.headers.get('content-type', '')
        if content_type.startswith('text/csv'):
            return r.text
        if content_type.startswith('application/pdf'):
            return r.content
        return r.json()
    except requests.RequestException as exc:
        if not quiet:
            st.error(f'The API at {API_URL} is not reachable ({exc}). Start it with `uvicorn app.main:app`.')
        return None


def currency(value):
    return f'${float(value):,.2f}'  # Demo currency only; no conversion.


def require_user(*roles):
    """Return the signed-in user for a sub-page, or stop with directions."""
    user = resolve_user(st.session_state, lambda: api('GET', '/api/auth/me', quiet=True))
    if not user:
        nav(None)
        st.info('Sign in on the main ShopSense page to see this page.')
        st.page_link('dashboard.py', label='Go to sign in')
        st.stop()
    nav(user)
    if roles and user['role'] not in roles:
        st.info(f"This page is for {' and '.join(roles)} accounts. You are signed in as a {user['role']}.")
        st.stop()
    return user


def nav(user):
    """One sidebar menu for every page, labelled for people rather than file names."""
    with st.sidebar:
        st.markdown('### ShopSense')
        st.page_link('dashboard.py', label='Overview' if not user or user['role'] != 'customer' else 'Shop')
        if user and user['role'] in ('admin', 'vendor'):
            st.page_link('pages/2_Inventory_Intelligence.py', label='Inventory')
            st.page_link('pages/3_Customer_Analytics.py', label='Customers')
            st.page_link('pages/4_Recommendations.py', label='Recommendations')
            st.page_link('pages/5_Milestone_2_Scorecard.py', label='Milestone 2 results')
        elif user:
            st.page_link('pages/4_Recommendations.py', label='Picked for you')
        st.page_link('pages/1_Historical_Analytics.py', label='Historical data (Olist)')
