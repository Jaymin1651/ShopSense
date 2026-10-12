"""Protected analytics endpoints, forecast and CSV reporting."""
import csv
import io
from datetime import datetime, timezone
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Product, User
from app.security import require_roles
from app.services import analytics as svc

router = APIRouter(prefix='/api/analytics', tags=['Analytics & Reporting'])


def scoped_vendor(user: User):
    return user.vendor_id if user.role == 'vendor' else None


@router.get('/summary')
def summary(db: Session = Depends(get_db), user: User = Depends(require_roles('admin', 'vendor'))):
    return svc.get_summary(db, scoped_vendor(user))


@router.get('/trends')
def trends(days: int = Query(default=30, ge=1, le=365), db: Session = Depends(get_db),
           user: User = Depends(require_roles('admin', 'vendor'))):
    return svc.get_trends(db, scoped_vendor(user), days)


@router.get('/top-products')
def top_products(db: Session = Depends(get_db), user: User = Depends(require_roles('admin', 'vendor'))):
    return svc.get_top_products(db, scoped_vendor(user))


@router.get('/vendors')
def vendors(db: Session = Depends(get_db), _: User = Depends(require_roles('admin'))):
    return svc.get_vendor_ranking(db)


@router.get('/customer-segments')
def customer_segments(db: Session = Depends(get_db), user: User = Depends(require_roles('admin', 'vendor'))):
    return svc.get_customer_segments(db, scoped_vendor(user))


@router.get('/forecast')
def forecast(product_id: int, days: int = Query(default=7, ge=1, le=30),
             db: Session = Depends(get_db), user: User = Depends(require_roles('admin', 'vendor'))):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, 'Product not found')
    if user.role == 'vendor' and product.vendor_id != user.vendor_id:
        raise HTTPException(403, 'Forecast limited to your products')
    return svc.get_forecast(db, product_id, days)


@router.get('/sales.csv')
def export_sales(db: Session = Depends(get_db), user: User = Depends(require_roles('admin', 'vendor'))):
    content = io.StringIO()
    writer = csv.writer(content)
    writer.writerow(['order_id', 'date', 'vendor_id', 'product_id', 'quantity', 'unit_price', 'line_gmv'])
    for item, order in svc.sales_rows(db, scoped_vendor(user)):
        writer.writerow([order.id, order.created_at.isoformat(), item.vendor_id, item.product_id,
                         item.quantity, str(item.unit_price), str(item.unit_price * item.quantity)])
    return StreamingResponse(iter([content.getvalue()]), media_type='text/csv',
                             headers={'Content-Disposition': 'attachment; filename="shopsense_sales.csv"'})


@router.get('/sales.pdf')
def export_sales_pdf(db: Session = Depends(get_db), user: User = Depends(require_roles('admin', 'vendor'))):
    """One-page executive overview; CSV contains transaction detail."""
    summary = svc.get_summary(db, scoped_vendor(user))
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    pdf.setTitle('ShopSense Sales Overview')
    pdf.setFont('Helvetica-Bold', 20)
    pdf.drawString(45, h-70, 'ShopSense Sales Overview')
    pdf.setFont('Helvetica', 10)
    pdf.drawString(45, h-92, f"Generated UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}")
    pdf.drawString(45, h-110, f"Scope: {'All vendors' if user.role == 'admin' else f'Vendor #{user.vendor_id}'}")
    items = [('Gross merchandise value', f"${summary['gmv']:,.2f}"),
             ('Orders', str(summary['orders'])),
             ('Average order value', f"${summary['average_order_value']:,.2f}"),
             ('Active products', str(summary['active_products'])),
             ('Low-stock products', str(summary['low_stock_products']))]
    pdf.setFont('Helvetica', 12)
    for i, (name, value) in enumerate(items):
        y = h-155-i*34
        pdf.drawString(45, y, name)
        pdf.drawRightString(w-50, y, value)
        pdf.line(45, y-12, w-50, y-12)
    pdf.setFont('Helvetica', 9)
    pdf.drawString(45, h-390, 'GMV is before refunds, shipping, taxes, payment fees and vendor commissions.')
    pdf.drawString(45, h-410, 'Demo orders do not represent completed payments or recognized revenue.')
    pdf.save()
    buffer.seek(0)
    return StreamingResponse(buffer, media_type='application/pdf',
                             headers={'Content-Disposition': 'attachment; filename="shopsense_overview.pdf"'})
