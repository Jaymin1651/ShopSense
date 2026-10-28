import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app
from app.models import User
from app.security import hash_password
from app.services import intelligence


@pytest.fixture()
def client():
    intelligence.clear_cache()  # trained models are cached per process; tests use fresh databases
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db:
        db.add(User(email='admin@example.com', password_hash=hash_password('AdminSecret123!'), role='admin'))
        db.commit()

    def overridden_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = overridden_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def login(client):
    def _login(email, password):
        response = client.post('/api/auth/login', json={'email': email, 'password': password})
        assert response.status_code == 200, response.text
        return {'Authorization': 'Bearer ' + response.json()['access_token']}
    return _login


@pytest.fixture()
def setup_marketplace(client, login):
    vendor = client.post('/api/auth/register/vendor', json={
        'business_name': 'North Gadgets', 'owner_name': 'A Vendor', 'email': 'vendor@example.com',
        'phone': '1234567890', 'category': 'Electronics', 'password': 'VendorSecret123!'
    })
    assert vendor.status_code == 201, vendor.text
    vendor_headers = login('vendor@example.com', 'VendorSecret123!')
    admin_headers = login('admin@example.com', 'AdminSecret123!')
    approve = client.patch(f"/api/vendors/{vendor.json()['vendor_id']}/status", params={'status':'approved'}, headers=admin_headers)
    assert approve.status_code == 200, approve.text
    product = client.post('/api/products', headers=vendor_headers, json={
        'name': 'Keyboard', 'description': 'Quiet mechanical keyboard', 'category': 'Electronics',
        'price': '50.00', 'quantity': 7, 'low_stock_threshold': 5
    })
    assert product.status_code == 201, product.text
    customer = client.post('/api/auth/register/customer', json={
        'full_name': 'Test Customer', 'email': 'customer@example.com', 'password': 'CustomerSecret123!'
    })
    assert customer.status_code == 201, customer.text
    customer_headers = login('customer@example.com', 'CustomerSecret123!')
    return {'vendor': vendor_headers, 'admin': admin_headers, 'customer': customer_headers,
            'product_id': product.json()['id'], 'vendor_id': vendor.json()['vendor_id']}
