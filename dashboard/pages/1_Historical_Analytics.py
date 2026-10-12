"""Independent public-data dashboard; not connected to ShopSense live orders."""
import os
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from historical_data import SOURCE, download_dataset, read_dataset, build_sales, summarize, group_sales

st.set_page_config(page_title='ShopSense | Historical Analysis', page_icon='📊', layout='wide')
st.title('📊 Historical e-commerce analytics')
st.caption('Real, anonymized Olist order data (2016–2018) · Delivered orders only · Brazilian reais (R$)')
st.info('This page analyzes an external historical dataset. Its sellers are not the registered vendors in the live ShopSense marketplace.')


@st.cache_data(ttl=3600, show_spinner='Downloading and analyzing historical order files...')
def get_historical_data():
    root = Path(os.getenv('OLIST_DATA_DIR', '/tmp/shopsense_olist'))
    download_dataset(root)
    return build_sales(read_dataset(root))


try:
    sales, audit = get_historical_data()
except Exception as exc:
    st.error(f'Historical data is unavailable: {exc}')
    st.markdown(f'Download the five required CSVs from [the original Olist dataset]({SOURCE}), '
                'place them in a folder, and set the `OLIST_DATA_DIR` environment variable to that folder. '
                'You can also retry after the dataset mirror is accessible.')
    st.stop()

if sales.empty:
    st.warning('The dataset did not contain valid delivered order items.')
    st.stop()

with st.sidebar:
    st.subheader('Historical dataset filters')
    min_date = sales['purchase_date'].min().date()
    max_date = sales['purchase_date'].max().date()
    dates = st.date_input('Purchase date range', value=(min_date, max_date), min_value=min_date,
                          max_value=max_date, key='historical_dates')
    state_options = sorted(sales['seller_state'].unique().tolist())
    states = st.multiselect('Seller states', state_options, key='historical_states')
    category_options = sorted(sales['category'].unique().tolist())
    categories = st.multiselect('Product categories', category_options, key='historical_categories')
    st.caption('Filters only affect historical charts on this page.')

filtered = sales
if len(dates) == 2:
    start, end = dates
    filtered = filtered.loc[filtered['purchase_date'].dt.date.between(start, end)]
if states:
    filtered = filtered.loc[filtered['seller_state'].isin(states)]
if categories:
    filtered = filtered.loc[filtered['category'].isin(categories)]

kpis = summarize(filtered)
a, b, c, d, e = st.columns(5)
a.metric('Item sales value', f"R$ {kpis['item_sales_brl']:,.2f}")
b.metric('Distinct orders', f"{kpis['orders']:,}")
c.metric('Active sellers', f"{kpis['sellers']:,}")
d.metric('Products sold', f"{kpis['products']:,}")
e.metric('Units sold', f"{kpis['units']:,}")
st.caption('Item sales value = sum of item prices on delivered orders; excludes freight and is not net revenue or profit.')

overview, sellers_tab, products_tab, quality = st.tabs(['Overview', 'Seller analysis', 'Product analysis', 'Data quality & source'])
with overview:
    monthly = group_sales(filtered, ['month']).sort_values('month')
    st.subheader('Monthly delivered-item sales value')
    if len(monthly):
        st.plotly_chart(px.line(monthly, x='month', y='item_sales_brl', markers=True,
                                labels={'month': 'Purchase month', 'item_sales_brl': 'Sales value (R$)'}),
                        width='stretch')
    else:
        st.info('No data matches these filters.')
    left, right = st.columns(2)
    with left:
        st.subheader('Top categories')
        chart = group_sales(filtered, ['category'], 10)
        if len(chart):
            st.plotly_chart(px.bar(chart.sort_values('item_sales_brl'), x='item_sales_brl', y='category',
                                    orientation='h', labels={'item_sales_brl':'Sales value (R$)', 'category':'Category'}),
                            width='stretch')
    with right:
        st.subheader('Seller state comparison')
        chart = group_sales(filtered, ['seller_state'], 10)
        if len(chart):
            st.plotly_chart(px.bar(chart, x='seller_state', y='item_sales_brl',
                                    labels={'seller_state':'State', 'item_sales_brl':'Sales value (R$)'}),
                            width='stretch')
with sellers_tab:
    st.subheader('Seller rankings')
    rank = group_sales(filtered, ['seller_id', 'seller_city', 'seller_state'])
    st.dataframe(rank.head(50).rename(columns={'seller_id':'Seller ID','seller_city':'City',
                'seller_state':'State','item_sales_brl':'Item sales (R$)','units':'Units','orders':'Orders'}),
                 hide_index=True, width='stretch')
    st.download_button('Download seller ranking CSV', rank.to_csv(index=False).encode('utf-8'),
                       file_name='olist_seller_ranking.csv', mime='text/csv')
with products_tab:
    st.subheader('Top products by units sold')
    ranked = group_sales(filtered, ['product_id', 'category']).sort_values(
        ['units', 'item_sales_brl'], ascending=False)
    st.dataframe(ranked.head(50).rename(columns={'product_id':'Product ID', 'category':'Category',
                'item_sales_brl':'Item sales (R$)','units':'Units','orders':'Orders'}),
                 hide_index=True, width='stretch')
    st.download_button('Download product ranking CSV', ranked.to_csv(index=False).encode('utf-8'),
                       file_name='olist_product_ranking.csv', mime='text/csv')
with quality:
    st.subheader('Data preparation audit')
    st.json(audit)
    st.write('Five original Olist CSV tables were joined on order, product and seller identifiers. '
             'Only delivered order items with a valid price and purchase date were included. '
             'Each item row counts as one unit; multi-seller orders count once in the order KPI.')
    st.markdown(f'**Original dataset:** [Brazilian E-Commerce Public Dataset by Olist]({SOURCE})  '
                '\n**License:** CC BY-NC-SA 4.0 (noncommercial, share-alike).  '
                '\n**Data period:** 2016–2018. Historical records do not represent current sales.')
    st.caption('Data mirror: spdrio/Brazilian-E-Commerce-Public-Dataset-by-Olist on GitHub. '
               'Source files are cached locally and are not committed to ShopSense.')