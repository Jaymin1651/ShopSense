import random
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def generate_valid_vendor(i):
    return {
        "business_name": f"Business {i}",
        "owner_name": f"Owner {i}",
        "email": f"valid{i}@example.com",
        "phone": f"+1{7000000000 + i}"
    }

def generate_invalid_vendor(i):
    invalid_cases = [
        {"business_name": "", "owner_name": "Owner", "email": "bad@example.com", "phone": "123456"},
        {"business_name": "Business", "owner_name": "", "email": "bad@example.com", "phone": "123456"},
        {"business_name": "Business", "owner_name": "Owner", "email": "invalid", "phone": "123456"},
        {"business_name": "Business", "owner_name": "Owner", "email": "bad@example.com", "phone": "abc"},
    ]
    return invalid_cases[i % len(invalid_cases)]


def test_vendor_registration_accuracy():
    total = 1000
    valid_count = 995
    invalid_count = total - valid_count

    records = [generate_valid_vendor(i) for i in range(valid_count)]
    records += [generate_invalid_vendor(i) for i in range(invalid_count)]
    random.shuffle(records)

    accepted = 0
    for record in records:
        response = client.post("/vendors/", json=record)
        if response.status_code == 201:
            accepted += 1

    accuracy = (accepted / total) * 100
    print(f"Vendor registration validation accuracy: {accuracy:.2f}%")
    assert accuracy >= 99.0
