from typing import Optional
from pydantic import BaseModel, Field

class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1)
    category: Optional[str] = None
    price: float = Field(..., gt=0)
    stock: int = Field(..., ge=0)
    vendor_id: int = Field(..., gt=0)
