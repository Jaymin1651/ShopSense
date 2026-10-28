"""API tests for Milestone 2 inventory, customer and recommendation endpoints."""
from datetime import datetime, timedelta, timezone

from app.database import get_db
from app.main import app
from app.models import Inventory, Order, OrderItem, Product, User
from app.security import hash_password


def db_session():
    return next(app.dependency_overrides[get_db]())


def test_inventory_endpoints_with_short_history(client, setup_marketplace):
    s = setup_marketplace
    client.post('/api/orders', headers=s['customer'], json={'items': [{'product_id': s['product_id'], 'quantity': 3}]})
    status = client.get('/api/inventory/status', headers=s['vendor'])
    assert status.status_code == 200
    row = status.json()[0]
    assert row['current_stock'] == 4 and row['status'] == 'Low stock'
    assert row['demand_source'] == '8_week_average'  # a single order is far too little to train on

    alerts = client.get('/api/inventory/alerts', headers=s['vendor']).json()
    assert [a['product_id'] for a in alerts] == [s['product_id']]
    plan = client.get('/api/inventory/replenishment', headers=s['admin']).json()
    assert plan[0]['reorder_qty'] > 0

    forecast = client.get(f"/api/inventory/forecast/{s['product_id']}", headers=s['vendor'], params={'weeks': 3})
    assert forecast.status_code == 200
    assert forecast.json()['method'] in {'moving_average_4_weeks', 'no_history'}

    overview = client.get('/api/inventory/overview', headers=s['admin']).json()
    assert overview['products'] == 1 and overview['low_stock'] == 1 and overview['forecast_method'] == '8_week_average'
    turnover = client.get('/api/inventory/turnover', headers=s['vendor'], params={'days': 30}).json()
    assert turnover['products'][0]['units_sold'] == 3 and turnover['portfolio']['basis'] == 'units'

    moves = client.get(f"/api/inventory/movements/{s['product_id']}", headers=s['vendor']).json()
    assert [m['reason'] for m in moves] == ['sale', 'initial_stock'] and moves[0]['delta'] == -3


def test_inventory_access_control(client, setup_marketplace, login):
    s = setup_marketplace
    assert client.get('/api/inventory/status').status_code == 401
    assert client.get('/api/inventory/status', headers=s['customer']).status_code == 403
    other = client.post('/api/auth/register/vendor', json={
        'business_name': 'Other Shop', 'owner_name': 'Other Owner', 'email': 'other@example.com',
        'phone': '1234567890', 'category': 'Books', 'password': 'OtherSecret123!'}).json()
    client.patch(f"/api/vendors/{other['vendor_id']}/status", params={'status': 'approved'}, headers=s['admin'])
    other_headers = login('other@example.com', 'OtherSecret123!')
    assert client.get('/api/inventory/status', headers=other_headers).json() == []
    assert client.get(f"/api/inventory/forecast/{s['product_id']}", headers=other_headers).status_code == 403
    assert client.get(f"/api/inventory/movements/{s['product_id']}", headers=other_headers).status_code == 403
    assert client.get('/api/inventory/forecast/999', headers=s['admin']).status_code == 404


def test_warehouses_categories_and_inventory_settings(client, setup_marketplace):
    s = setup_marketplace
    assert client.post('/api/warehouses', headers=s['vendor'], json={'name': 'West Hub'}).status_code == 403
    hub = client.post('/api/warehouses', headers=s['admin'], json={'name': 'West Hub', 'location': 'Ahmedabad'})
    assert hub.status_code == 201
    assert client.post('/api/warehouses', headers=s['admin'], json={'name': 'West Hub'}).status_code == 409
    assert client.get('/api/warehouses', headers=s['vendor']).json()[0]['location'] == 'Ahmedabad'

    parent = client.post('/api/categories', headers=s['admin'], json={'name': 'Electronics'}).json()
    client.post('/api/categories', headers=s['admin'], json={'name': 'Laptop', 'parent_id': parent['id']})
    assert client.post('/api/categories', headers=s['admin'], json={'name': 'Bad', 'parent_id': 999}).status_code == 404
    tree = client.get('/api/categories').json()
    assert tree[0]['name'] == 'Electronics' and tree[0]['children'][0]['name'] == 'Laptop'

    updated = client.put(f"/api/products/{s['product_id']}/inventory", headers=s['vendor'],
                         json={'quantity': 7, 'warehouse_id': hub.json()['id'], 'lead_time_days': 12})
    assert updated.status_code == 200 and updated.json()['lead_time_days'] == 12
    assert client.put(f"/api/products/{s['product_id']}/inventory", headers=s['vendor'],
                      json={'quantity': 7, 'warehouse_id': 999}).status_code == 404
    status = client.get('/api/inventory/status', headers=s['vendor']).json()[0]
    assert status['warehouse'] == 'West Hub' and status['lead_time_days'] == 12

    product = client.post('/api/products', headers=s['vendor'], json={
        'name': 'Laptop Stand', 'category': 'Laptop', 'price': '30.00', 'unit_cost': '18.00', 'quantity': 4,
        'warehouse_id': hub.json()['id'], 'lead_time_days': 5})
    assert product.status_code == 201 and product.json()['unit_cost'] == '18.00'


def test_customer_analytics_and_segments(client, setup_marketplace):
    s = setup_marketplace
    client.post('/api/orders', headers=s['customer'], json={'items': [{'product_id': s['product_id'], 'quantity': 2}]})
    overview = client.get('/api/customer-analytics/overview', headers=s['vendor']).json()
    assert overview['summary']['customers'] == 1 and overview['summary']['average_order_value'] == 100.0
    segments = client.get('/api/customer-analytics/segments', headers=s['admin']).json()
    assert segments['available'] is False and segments['customers'] == 1
    assert client.get('/api/customer-analytics/segments', headers=s['customer']).status_code == 403


def test_segments_with_enough_customers(client, setup_marketplace):
    s = setup_marketplace
    db = db_session()
    product = db.get(Product, s['product_id'])
    now = datetime.now(timezone.utc)
    for n in range(30):
        user = User(email=f'buyer{n}@example.com', password_hash=hash_password('x' * 12), role='customer')
        db.add(user)
        db.flush()
        for k in range(1 + (n % 3) * 4):
            order = Order(customer_id=user.id, total=product.price, created_at=now - timedelta(days=5 + (n % 3) * 150 + k))
            order.items = [OrderItem(product_id=product.id, vendor_id=product.vendor_id, quantity=1, unit_price=product.price)]
            db.add(order)
    db.commit()
    result = client.get('/api/customer-analytics/segments', headers=s['vendor'], params={'k': 3}).json()
    assert result['available'] and result['k'] == 3
    assert {p['segment'] for p in result['profiles']} == {'High value', 'Regular', 'Dormant'}
    assert -1 <= result['metrics']['silhouette'] <= 1 and len(result['points']) == 30


def test_recommendations_feedback_and_metrics(client, setup_marketplace):
    s = setup_marketplace
    second = client.post('/api/products', headers=s['vendor'], json={
        'name': 'Mouse', 'category': 'Electronics', 'price': '20.00', 'quantity': 10}).json()
    client.post('/api/orders', headers=s['customer'], json={'items': [{'product_id': s['product_id'], 'quantity': 1}]})
    recs = client.get('/api/recommendations/me', headers=s['customer'])
    assert recs.status_code == 200
    body = recs.json()
    assert [r['product']['id'] for r in body] == [second['id']]  # purchased keyboard is excluded
    assert isinstance(body[0]['score'], float) and body[0]['reason']
    assert client.get('/api/recommendations/me', headers=s['vendor']).status_code == 403

    shown = client.post('/api/recommendations/feedback', headers=s['customer'],
                        json={'event': 'impression', 'product_ids': [second['id'], 999]})
    assert shown.json() == {'recorded': 1}
    client.post('/api/recommendations/feedback', headers=s['customer'], json={'event': 'click', 'product_ids': [second['id']]})
    client.post('/api/orders', headers=s['customer'], json={'items': [{'product_id': second['id'], 'quantity': 1}]})
    metrics = client.get('/api/recommendations/metrics', headers=s['admin']).json()
    assert metrics['impressions'] == 1 and metrics['clicks'] == 1 and metrics['ctr_pct'] == 100.0
    assert metrics['purchases_after_click'] == 1
    assert client.get('/api/recommendations/metrics', headers=s['vendor']).status_code == 403
    # Impressions and clicks are tracking events, not taste signals for the legacy endpoint.
    assert client.get('/api/customers/recommendations/me', headers=s['customer']).json() == []


def test_out_of_stock_products_are_not_recommended(client, setup_marketplace):
    s = setup_marketplace
    db = db_session()
    db.get(Inventory, 1).quantity = 0
    db.commit()
    assert client.get('/api/recommendations/me', headers=s['customer']).json() == []


def test_evaluation_report_endpoint(client, setup_marketplace):
    s = setup_marketplace
    assert client.get('/api/evaluation/milestone2', headers=s['customer']).status_code == 403
    report = client.get('/api/evaluation/milestone2', headers=s['admin']).json()
    assert 'scorecard' in report or report.get('available') is False
