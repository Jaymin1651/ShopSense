from app.analytics.analytics import total_revenue, vendor_revenue, product_revenue, top_product


def test_revenue_calculation():
    total = total_revenue("data/transactions.csv")
    assert total == 1200 + 500 + 850 + 2500 + 700


def test_vendor_revenue():
    result = vendor_revenue("data/transactions.csv")
    assert result["amount"].sum() == 1200 + 500 + 850 + 2500 + 700


def test_top_product():
    result = top_product("data/transactions.csv")
    assert result == 104
