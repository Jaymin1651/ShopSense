from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_add_product():
    payload = {
        "name": "Laptop",
        "category": "Electronics",
        "price": 550.0,
        "stock": 10,
        "vendor_id": 1
    }

    response = client.post("/products/", json=payload)
    assert response.status_code == 201
    assert response.json()["message"] == "Product Added"
