"""ShopSense interactive Streamlit demo dashboard using the REST API."""
from decimal import Decimal
import pandas as pd
import plotly.express as px
import streamlit as st

from session import resolve_user
from ui import TEAL, VIOLET, api, apply_style, currency, nav, note

st.set_page_config(page_title='ShopSense • Marketplace Intelligence', page_icon='🛍️', layout='wide')
apply_style()


# Recover an interrupted sign-in instead of reading a missing session key.
user = resolve_user(st.session_state, lambda: api('GET', '/api/auth/me'))

nav(user)
with st.sidebar:
    if user:
        st.success(f"{user['role'].title()} · {user['email']}")
        if st.button('Sign out', width='stretch'):
            for k in ['token', 'user', 'cart']:
                st.session_state.pop(k, None)
            st.rerun()
    st.divider()
    st.caption('Demonstration app. Orders do not process real payments.')


if not user:
    st.title('Grow your marketplace with actionable analytics')
    st.write('Manage vendors, list products, place simulated orders, and monitor revenue and demand.')
    t1, t2, t3 = st.tabs(['Sign in', 'Register as vendor', 'Register as customer'])
    with t1:
        with st.form('login'):
            email = st.text_input('Email')
            password = st.text_input('Password', type='password')
            submitted = st.form_submit_button('Sign in', type='primary')
        if submitted:
            token = api('POST', '/api/auth/login', json={'email': email, 'password': password})
            if token and token.get('access_token'):
                st.session_state['token'] = token['access_token']
                me = api('GET', '/api/auth/me')
                if me:
                    st.session_state['user'] = me
                    st.rerun()
                st.session_state.pop('token', None)
    with t2:
        with st.form('vendor_signup'):
            business_name = st.text_input('Business name')
            owner_name = st.text_input('Owner name')
            vemail = st.text_input('Business email')
            phone = st.text_input('Phone')
            category = st.text_input('Primary category')
            vpassword = st.text_input('Password (10+ chars)', type='password')
            register_vendor = st.form_submit_button('Submit for approval')
        if register_vendor and api('POST', '/api/auth/register/vendor', json={
            'business_name': business_name, 'owner_name': owner_name, 'email': vemail,
            'phone': phone, 'category': category, 'password': vpassword}):
            st.success('Registration submitted. An administrator must approve your account.')
    with t3:
        with st.form('customer_signup'):
            full_name = st.text_input('Full name')
            cemail = st.text_input('Email')
            cpassword = st.text_input('Password (10+ chars)', type='password')
            register_customer = st.form_submit_button('Create customer account')
        if register_customer and api('POST', '/api/auth/register/customer', json={
            'full_name': full_name, 'email': cemail, 'password': cpassword}):
            st.success('Customer account created. Please sign in.')
    st.stop()

role = user['role']
st.title('ShopSense dashboard' if role == 'admin' else 'My shop' if role == 'vendor' else 'ShopSense marketplace')
st.caption('Products, orders, stock and sales in one place')

if role in ('admin', 'vendor'):
    summary, trends, top, segments = (api('GET', p) for p in [
        '/api/analytics/summary', '/api/analytics/trends?days=30',
        '/api/analytics/top-products', '/api/analytics/customer-segments'])
    if summary:
        cols = st.columns(4)
        for col, label, value in zip(cols, ['Gross merchandise value', 'Orders', 'Average order value', 'Low-stock products'],
                                     [currency(summary['gmv']), summary['orders'], currency(summary['average_order_value']), summary['low_stock_products']]):
            col.metric(label, value)
        st.caption('GMV is calculated from placed order items. It is not collected payment, profit, or net revenue.')
    alerts = api('GET', '/api/inventory/alerts') or []
    critical = [a for a in alerts if a['severity'] == 'critical']
    if critical:
        names = ', '.join(a['name'] for a in critical[:3]) + (f' and {len(critical) - 3} more' if len(critical) > 3 else '')
        st.warning(f'{len(critical)} product{"s" if len(critical) != 1 else ""} will run out before restock: {names}.')
        st.page_link('pages/2_Inventory_Intelligence.py', label='Open the reorder plan')

    tabs = st.tabs(['Overview', 'Vendors' if role == 'admin' else 'My products', 'Order history', 'Demand insights', 'Reports'])
    with tabs[0]:
        left, right = st.columns([3, 2])
        with left:
            st.subheader('Revenue trend')
            if trends:
                df = pd.DataFrame(trends)
                fig = px.area(df, x='date', y='gmv', labels={'date': 'Date', 'gmv': 'GMV'})
                fig.update_traces(line_color=TEAL, fillcolor='rgba(14,124,123,0.10)')
                st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        with right:
            st.subheader('Best-selling products')
            if top:
                fig = px.bar(pd.DataFrame(top).iloc[::-1], x='gmv', y='product', orientation='h',
                             labels={'gmv': 'GMV', 'product': ''})
                fig.update_traces(marker_color=TEAL)
                st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
            else:
                st.info('Sales charts appear after customers place orders.')
    with tabs[1]:
        if role == 'admin':
            st.subheader('Vendor approvals and lifecycle')
            vendors = api('GET', '/api/vendors')
            if vendors:
                st.dataframe(pd.DataFrame(vendors)[['id', 'business_name', 'owner_name', 'email', 'category', 'status']], hide_index=True, width='stretch')
                vendor_id = st.selectbox('Vendor to manage', [v['id'] for v in vendors], format_func=lambda v: next(x['business_name'] for x in vendors if x['id']==v))
                action = st.selectbox('New status', ['approved', 'suspended', 'rejected'])
                if st.button('Update vendor status', type='primary'):
                    if api('PATCH', f'/api/vendors/{vendor_id}/status', params={'status': action}):
                        st.rerun()
            else:
                st.info('No vendor applications yet.')
        else:
            vendor = api('GET', '/api/vendors/me')
            if vendor:
                if vendor['status'] == 'approved':
                    st.success('Your shop is approved. Add a product below to show it to customers.')
                else:
                    st.warning(f"Shop status: {vendor['status']}. Products will only be visible to customers after approval.")
            products = api('GET', '/api/products/mine')
            if products:
                st.dataframe(pd.DataFrame(products)[['id','name','category','price','quantity','visible_to_customers','visibility_note']], hide_index=True, width='stretch')
                st.caption('Customer visibility depends on shop approval and whether a product is active. Out-of-stock products are displayed but cannot be ordered.')
                st.subheader('Show or hide a product')
                visibility_id = st.selectbox('Choose product', [p['id'] for p in products],
                    format_func=lambda x: next(p['name'] for p in products if p['id'] == x), key='visibility_product')
                current = next(p for p in products if p['id'] == visibility_id)
                with st.form('product_visibility'):
                    publish = st.checkbox('Visible in catalog', value=current['is_active'])
                    if st.form_submit_button('Save visibility'):
                        if api('PATCH', f'/api/products/{visibility_id}', json={'is_active': publish}):
                            st.rerun()
            with st.expander('Add product', expanded=not bool(products)):
                with st.form('new_product'):
                    name = st.text_input('Product name')
                    description = st.text_area('Description')
                    category = st.text_input('Category')
                    price = st.number_input('Unit price ($)', min_value=0.01, value=10.00, step=1.00)
                    quantity = st.number_input('Opening stock', min_value=0, value=15, step=1)
                    threshold = st.number_input('Low-stock threshold', min_value=0, value=5, step=1)
                    submit = st.form_submit_button('Add product')
                if submit and api('POST', '/api/products', json={
                    'name': name, 'description': description, 'category': category, 'price': str(price),
                    'quantity': quantity, 'low_stock_threshold': threshold}):
                    st.rerun()
            if products:
                with st.expander('Adjust inventory'):
                    product_id = st.selectbox('Product', [p['id'] for p in products], format_func=lambda v: next(p['name'] for p in products if p['id']==v))
                    chosen = next(p for p in products if p['id']==product_id)
                    new_stock = st.number_input('New stock count', min_value=0, value=int(chosen['quantity']))
                    if st.button('Save stock level'):
                        if api('PUT', f'/api/products/{product_id}/inventory', json={'quantity': int(new_stock)}):
                            st.rerun()
    with tabs[2]:
        orders = api('GET', '/api/orders')
        if orders:
            df = pd.DataFrame(orders)
            st.dataframe(df[['id','created_at','status','total','items']], width='stretch', hide_index=True)
        else:
            st.info('No orders yet.')
    with tabs[3]:
        st.subheader('Demand forecast')
        note('Weekly forecast from the Random Forest demand model (4-week average when a product has under '
             '12 weeks of sales). The Inventory page has the full forecast, alerts and reorder plan.')
        ps = api('GET', '/api/products/mine') if role == 'vendor' else api('GET', '/api/products')
        if ps:
            pid = st.selectbox('Select a product', [p['id'] for p in ps], format_func=lambda x: next(p['name'] for p in ps if p['id']==x))
            forecast = api('GET', f'/api/inventory/forecast/{pid}', params={'weeks': 4})
            if forecast and forecast.get('weekly'):
                f1, f2, f3 = st.columns(3)
                f1.metric('Predicted units per day', forecast['predicted_daily_units'])
                f2.metric('Available stock', forecast['current_stock'])
                f3.metric('Days of stock', forecast['estimated_days_of_stock'] or '—')
                fig = px.line(pd.DataFrame(forecast['weekly']), x='week', y='forecast', markers=True,
                              labels={'week': 'Week ending', 'forecast': 'Units'})
                fig.update_traces(line=dict(color=VIOLET, dash='dot'))
                st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
            elif forecast:
                st.info('No sales yet for this product.')
        st.subheader('Customer segments')
        if segments:
            st.dataframe(pd.DataFrame(segments['segments']), hide_index=True, width='stretch')
            st.caption('Simple rule-based recency/frequency groups. The Customers page has K-Means segments.')
        if role == 'admin':
            st.subheader('Vendor comparison')
            ranking = api('GET', '/api/analytics/vendors')
            if ranking:
                st.dataframe(pd.DataFrame(ranking), hide_index=True, width='stretch')
    with tabs[4]:
        st.subheader('Export sales records')
        csv_content = api('GET', '/api/analytics/sales.csv')
        if csv_content is not None:
            st.download_button('Download sales CSV', csv_content, file_name='shopsense_sales.csv', mime='text/csv')
        pdf_content = api('GET', '/api/analytics/sales.pdf')
        if pdf_content is not None:
            st.download_button('Download PDF overview', pdf_content, file_name='shopsense_overview.pdf', mime='application/pdf')

elif role == 'customer':
    catalog, orders_tab, recommended = st.tabs(['Product catalog', 'My orders', 'For you'])
    with catalog:
        products = api('GET', '/api/products') or []
        if not products:
            st.info('No products have been published yet. An approved vendor must add a product and keep it active for it to appear here.')
        cart = st.session_state.setdefault('cart', {})
        for p in products:
            with st.container(border=True):
                cols = st.columns([4,2,1])
                cols[0].subheader(p['name'])
                cols[0].write(f"{p['description']} · {p['category']}")
                cols[1].metric('Price', currency(p['price']))
                cols[1].caption(f"Available: {p['quantity']}")
                if cols[2].button('View', key=f"view_{p['id']}"):
                    api('POST','/api/customers/interactions', json={'product_id':p['id'],'event_type':'view'})
                if cols[2].button('Add to cart', key=f"cart_{p['id']}", disabled=p['quantity']==0):
                    cart[p['id']] = min(cart.get(p['id'], 0)+1, p['quantity'])
                    api('POST','/api/customers/interactions', json={'product_id':p['id'],'event_type':'cart'})
                    st.rerun()
        st.subheader('Your cart')
        if cart:
            for pid, qty in list(cart.items()):
                match = next((p for p in products if p['id']==pid), None)
                if match:
                    st.write(f"{match['name']} × {qty} · {currency(Decimal(match['price'])*qty)}")
            if st.button('Place simulated order', type='primary'):
                order = api('POST','/api/orders', json={'items':[{'product_id':pid,'quantity':qty} for pid,qty in cart.items()]})
                if order:
                    st.session_state['cart'] = {}
                    st.success(f"Order #{order['id']} placed. No payment was collected.")
    with orders_tab:
        orders = api('GET','/api/orders')
        if orders:
            st.dataframe(pd.DataFrame(orders)[['id','created_at','status','total','items']], hide_index=True, width='stretch')
        else:
            st.info('You have not placed an order.')
    with recommended:
        recs = api('GET', '/api/recommendations/me', params={'limit': 8})
        if recs:
            shown = tuple(r['product']['id'] for r in recs)
            if st.session_state.get('rec_logged') != shown:
                api('POST', '/api/recommendations/feedback', quiet=True,
                    json={'event': 'impression', 'product_ids': list(shown)})
                st.session_state['rec_logged'] = shown
            for r in recs:
                p = r['product']
                st.markdown(f"<div class='ss-rec'><b>{p['name']}</b> · {currency(p['price'])}<br>"
                            f"<span>{r['reason']}</span></div>", unsafe_allow_html=True)
        else:
            st.info('Browse or place an order to receive personalized product suggestions.')
