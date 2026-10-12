def test_health_and_auth(client):
    assert client.get('/health').json()['status'] == 'ok'
    assert client.get('/ready').status_code == 200
    assert client.get('/api/analytics/summary').status_code == 401
    result = client.post('/api/auth/login', json={'email':'admin@example.com','password':'bad'})
    assert result.status_code == 401


def test_pending_vendor_cannot_list(client, login):
    created = client.post('/api/auth/register/vendor', json={
        'business_name': 'Pending Store', 'owner_name': 'Test Owner', 'email': 'pending@example.com',
        'phone': '1234567890', 'category': 'Books', 'password': 'PendingSecret123!'
    })
    assert created.status_code == 201
    headers = login('pending@example.com', 'PendingSecret123!')
    denied = client.post('/api/products', headers=headers, json={
        'name':'Notebook','category':'Books','price':'2.00','quantity':5
    })
    assert denied.status_code == 403
    assert client.get('/api/products').json() == []


def test_vendor_approval_and_catalog(client, setup_marketplace):
    s = setup_marketplace
    catalog = client.get('/api/products').json()
    assert len(catalog) == 1 and catalog[0]['name'] == 'Keyboard'
    assert catalog[0]['quantity'] == 7
    mine = client.get('/api/products/mine', headers=s['vendor'])
    assert mine.status_code == 200 and len(mine.json()) == 1
    assert client.get('/api/vendors', headers=s['customer']).status_code == 403
    assert client.get('/api/vendors', headers=s['admin']).status_code == 200
    changed = client.put(f"/api/products/{s['product_id']}/inventory", headers=s['vendor'], json={'quantity':3})
    assert changed.status_code == 200
    assert changed.json()['quantity'] == 3


def test_order_updates_stock_and_revenue(client, setup_marketplace):
    s = setup_marketplace
    order = client.post('/api/orders', headers=s['customer'], json={
        'items':[{'product_id':s['product_id'], 'quantity':2}]})
    assert order.status_code == 201, order.text
    assert float(order.json()['total']) == 100.0
    assert client.get('/api/products').json()[0]['quantity'] == 5
    analytics = client.get('/api/analytics/summary', headers=s['vendor']).json()
    assert analytics['gmv'] == 100.0 and analytics['orders'] == 1
    assert analytics['average_order_value'] == 100.0
    assert analytics['low_stock_products'] == 1
    csv = client.get('/api/analytics/sales.csv', headers=s['vendor'])
    assert csv.status_code == 200 and '100.00' in csv.text
    pdf = client.get('/api/analytics/sales.pdf', headers=s['vendor'])
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF-')
    forecast = client.get('/api/analytics/forecast', headers=s['vendor'], params={'product_id':s['product_id']})
    assert forecast.status_code == 200 and len(forecast.json()['forecast']) == 7


def test_insufficient_stock_preserves_state(client, setup_marketplace):
    s = setup_marketplace
    bad = client.post('/api/orders', headers=s['customer'], json={
        'items':[{'product_id':s['product_id'], 'quantity':99}]})
    assert bad.status_code == 409
    assert client.get('/api/products').json()[0]['quantity'] == 7
    assert client.get('/api/analytics/summary', headers=s['admin']).json()['orders'] == 0


def test_interactions_and_recommendations(client, setup_marketplace):
    s = setup_marketplace
    recorded = client.post('/api/customers/interactions', headers=s['customer'], json={
        'product_id': s['product_id'], 'event_type':'view'
    })
    assert recorded.status_code == 201
    assert client.post('/api/customers/interactions', headers=s['vendor'], json={
        'product_id': s['product_id'], 'event_type':'view'
    }).status_code == 403
    recs = client.get('/api/customers/recommendations/me', headers=s['customer'])
    assert recs.status_code == 200
    assert recs.json() == []  # only known product already viewed


def test_validation_and_vendors_scope(client, setup_marketplace):
    s = setup_marketplace
    other = client.post('/api/auth/register/vendor', json={
        'business_name':'Second Shop','owner_name':'Second Owner','email':'second@example.com',
        'phone':'1234567890','category':'Games','password':'SecondSecret123!'
    })
    assert other.status_code == 201
    denied = client.patch(f"/api/vendors/{s['vendor_id']}/status", params={'status':'suspended'}, headers=s['vendor'])
    assert denied.status_code == 403
    invalid = client.post('/api/orders', headers=s['customer'], json={'items':[
        {'product_id':s['product_id'],'quantity':1}, {'product_id':s['product_id'],'quantity':1}]})
    assert invalid.status_code == 422
    assert client.get('/api/analytics/vendors', headers=s['vendor']).status_code == 403


def test_two_vendor_order_isolated_subtotals(client, setup_marketplace, login):
    s = setup_marketplace
    vendor2 = client.post('/api/auth/register/vendor', json={
        'business_name': 'Bookshop Two', 'owner_name':'Another Vendor', 'email': 'bookshop@example.com',
        'phone':'1234567890', 'category':'Books', 'password':'AnotherSecret123!'
    })
    assert vendor2.status_code == 201
    headers2 = login('bookshop@example.com', 'AnotherSecret123!')
    assert client.patch(f"/api/vendors/{vendor2.json()['vendor_id']}/status", headers=s['admin'],
                        params={'status':'approved'}).status_code == 200
    product2 = client.post('/api/products', headers=headers2, json={
        'name':'Book of Analytics','category':'Books','price':'20.00','quantity':3
    })
    assert product2.status_code == 201
    assert client.put(f"/api/products/{s['product_id']}/inventory", headers=headers2,
                      json={'quantity':50}).status_code == 403
    order = client.post('/api/orders', headers=s['customer'], json={'items':[
        {'product_id':s['product_id'], 'quantity':1},
        {'product_id':product2.json()['id'], 'quantity':2}]})
    assert order.status_code == 201
    assert float(order.json()['total']) == 90
    a = client.get('/api/orders', headers=s['vendor']).json()
    b = client.get('/api/orders', headers=headers2).json()
    assert len(a) == 1 and len(b) == 1
    assert len(a[0]['items']) == 1 and len(b[0]['items']) == 1
    assert float(a[0]['total']) == 50 and float(b[0]['total']) == 40
    assert client.get('/api/analytics/summary', headers=s['vendor']).json()['gmv'] == 50
    assert client.get('/api/analytics/summary', headers=headers2).json()['gmv'] == 40
    assert client.get('/api/analytics/summary', headers=s['admin']).json()['gmv'] == 90


def test_approved_vendor_product_publication_and_visibility(client, login):
    """Regression: product appears to customers only after vendor approval and listing."""
    admin = login('admin@example.com', 'AdminSecret123!')
    vendor = client.post('/api/auth/register/vendor', json={
        'business_name': 'Local Stationery', 'owner_name': 'Solo Shopkeeper',
        'email': 'stationery@example.com', 'phone': '1234567890',
        'category': 'Stationery', 'password': 'StationerySecret123!'
    }).json()
    vendor_headers = login('stationery@example.com', 'StationerySecret123!')
    assert client.get('/api/products').json() == []
    assert client.get('/api/products/mine', headers=vendor_headers).json() == []

    approved = client.patch(f"/api/vendors/{vendor['vendor_id']}/status",
                            params={'status': 'approved'}, headers=admin)
    assert approved.status_code == 200
    assert client.get('/api/products').json() == []  # Approval does not create a product.

    added = client.post('/api/products', headers=vendor_headers, json={
        'name': 'Campus Notebook', 'description': '100 pages', 'category': 'Stationery',
        'price': '49.00', 'quantity': 5,
    })
    assert added.status_code == 201, added.text
    product_id = added.json()['id']
    assert added.json()['visible_to_customers'] is True
    assert added.json()['visibility_note'] == 'Visible in customer catalog'
    catalog = client.get('/api/products')
    assert catalog.status_code == 200
    assert [p['id'] for p in catalog.json()] == [product_id]

    hidden = client.patch(f'/api/products/{product_id}', headers=vendor_headers,
                          json={'is_active': False})
    assert hidden.status_code == 200
    assert hidden.json()['visible_to_customers'] is False
    assert client.get('/api/products').json() == []
    mine = client.get('/api/products/mine', headers=vendor_headers).json()
    assert mine[0]['visibility_note'] == 'Product is hidden by vendor'

    assert client.patch(f'/api/products/{product_id}', headers=vendor_headers,
                        json={'is_active': True}).status_code == 200
    assert len(client.get('/api/products').json()) == 1

    # Suspended sellers cannot sell, even if their products are marked active.
    assert client.patch(f"/api/vendors/{vendor['vendor_id']}/status", headers=admin,
                        params={'status': 'suspended'}).status_code == 200
    assert client.get('/api/products').json() == []
    mine = client.get('/api/products/mine', headers=vendor_headers).json()
    assert mine[0]['visible_to_customers'] is False
    assert 'suspended' in mine[0]['visibility_note']
    assert client.patch(f"/api/vendors/{vendor['vendor_id']}/status", headers=admin,
                        params={'status': 'approved'}).status_code == 200
    assert len(client.get('/api/products').json()) == 1

    # Stock affects cart availability, but not whether an active product is listed.
    assert client.put(f'/api/products/{product_id}/inventory', headers=vendor_headers,
                      json={'quantity': 0}).status_code == 200
    item = client.get('/api/products').json()[0]
    assert item['visible_to_customers'] is True
    assert item['quantity'] == 0
    assert item['visibility_note'] == 'Visible, but out of stock'
