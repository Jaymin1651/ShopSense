from fastapi import APIRouter
from app.analytics.analytics import total_revenue, vendor_revenue, product_revenue, top_product

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.get("/revenue")
def revenue():
    return {
        "total_revenue": total_revenue("data/transactions.csv")
    }

@router.get("/vendor-revenue")
def vendor_revenue_route():
    return {
        "vendor_revenue": vendor_revenue("data/transactions.csv").to_dict(orient="records")
    }

@router.get("/product-revenue")
def product_revenue_route():
    return {
        "product_revenue": product_revenue("data/transactions.csv").to_dict(orient="records")
    }

@router.get("/top-product")
def top_product_route():
    return {
        "top_product": top_product("data/transactions.csv")
    }
