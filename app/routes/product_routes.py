from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.product import Product
from app.schemas.product import ProductCreate

router = APIRouter(prefix="/products", tags=["Products"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", status_code=status.HTTP_201_CREATED)
def add_product(product: ProductCreate, db: Session = Depends(get_db)):
    db_product = Product(
        name=product.name,
        category=product.category,
        price=product.price,
        stock=product.stock,
        vendor_id=product.vendor_id
    )

    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    return {
        "status": "success",
        "message": "Product Added",
        "product": {
            "id": db_product.id,
            "name": db_product.name,
            "category": db_product.category,
            "price": db_product.price,
            "stock": db_product.stock,
            "vendor_id": db_product.vendor_id
        }
    }
