from typing import Optional
from pydantic import BaseModel, EmailStr, Field, validator

class VendorCreate(BaseModel):
    business_name: str = Field(..., min_length=1)
    owner_name: str = Field(..., min_length=1)
    email: EmailStr
    phone: str = Field(..., min_length=7, max_length=15)
    address: Optional[str] = None

    @validator("phone")
    def validate_phone(cls, value):
        cleaned = value.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        # allow optional leading +, then digits
        if cleaned.startswith("+"):
            if not cleaned[1:].isdigit():
                raise ValueError("Phone must contain digits only after +")
        else:
            if not cleaned.isdigit():
                raise ValueError("Phone must contain digits only")
        return value
