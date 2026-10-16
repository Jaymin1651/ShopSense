from fastapi import FastAPI
from app.routes.vendor_routes import router as vendor_router
from app.routes.product_routes import router as product_router
from app.routes.analytics_routes import router as analytics_router

app = FastAPI(
    title="ShopSense API",
    description="Vendor management, product management, and sales analytics",
    version="1.0.0"
)

app.include_router(vendor_router)
app.include_router(product_router)
app.include_router(analytics_router)

@app.get("/")
def home():
    return {"message": "Welcome to ShopSense API"}
