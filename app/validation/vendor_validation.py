from app.schemas.vendor import VendorCreate
from pydantic import ValidationError

def validate_vendor(data: dict) -> bool:
    try:
        VendorCreate(**data)
        return True
    except ValidationError:
        return False
