"""Small synthetic fixtures test the logic; real Olist CSVs are downloaded at runtime."""
from pathlib import Path
import sys
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dashboard'))
from historical_data import build_sales, summarize, group_sales


def rows():
    return {
        'items': pd.DataFrame([
            {'order_id':'o1','order_item_id':1,'product_id':'p1','seller_id':'s1','price':10},
            {'order_id':'o1','order_item_id':2,'product_id':'p2','seller_id':'s2','price':20},
            {'order_id':'o2','order_item_id':1,'product_id':'p1','seller_id':'s1','price':999},
            {'order_id':'o3','order_item_id':1,'product_id':'p1','seller_id':'s1','price':15},
        ]),
        'orders': pd.DataFrame([
            {'order_id':'o1','order_status':'delivered','order_purchase_timestamp':'2018-06-01 12:00:00'},
            {'order_id':'o2','order_status':'canceled','order_purchase_timestamp':'2018-06-02 12:00:00'},
            {'order_id':'o3','order_status':'delivered','order_purchase_timestamp':'2018-06-03 12:00:00'},
        ]),
        'products': pd.DataFrame([
            {'product_id':'p1','product_category_name':'livros'},
            {'product_id':'p2','product_category_name':'casa'},
        ]),
        'sellers': pd.DataFrame([
            {'seller_id':'s1','seller_city':'campinas','seller_state':'SP'},
            {'seller_id':'s2','seller_city':'rio','seller_state':'RJ'},
        ]),
        'categories': pd.DataFrame([
            {'product_category_name':'livros','product_category_name_english':'books'},
            {'product_category_name':'casa','product_category_name_english':'home'},
        ]),
    }


def test_actual_joins_and_delivered_order_aggregation():
    sales, audit = build_sales(rows())
    assert audit['source_item_rows'] == 4
    assert audit['not_delivered_or_missing_order'] == 1
    assert summarize(sales) == {'item_sales_brl':45.0, 'orders':2,'sellers':2,'products':2,'units':3}
    assert sales.loc[sales.product_id.eq('p1'), 'category'].tolist() == ['books','books']
    top = group_sales(sales,['seller_id'])
    assert top.iloc[0]['seller_id'] == 's1'
    assert top.iloc[0]['item_sales_brl'] == 25


def test_duplicate_order_items_are_rejected():
    dataset=rows()
    dataset['items'].loc[1,'order_item_id']=1
    with pytest.raises(ValueError, match='duplicate order_id/order_item_id'):
        build_sales(dataset)


def test_missing_required_column_rejected():
    dataset=rows()
    dataset['sellers'] = dataset['sellers'].drop(columns=['seller_state'])
    with pytest.raises(ValueError,match='missing columns'):
        build_sales(dataset)


def test_invalid_price_is_excluded_and_audited():
    dataset=rows()
    dataset['items'].loc[0,'price']=-8
    sales,audit=build_sales(dataset)
    assert audit['invalid_price_or_date']==1
    assert summarize(sales)['item_sales_brl']==35


def test_empty_filtered_sales_is_supported():
    sales,_=build_sales(rows())
    empty=sales.loc[sales['seller_state']=='XX']
    assert summarize(empty)['orders']==0
    assert group_sales(empty,['month']).empty


def test_product_duplicates_are_not_allowed():
    dataset=rows()
    dataset['products']=pd.concat([dataset['products'],dataset['products'].iloc[:1]],ignore_index=True)
    with pytest.raises(ValueError,match='product_id'):
        build_sales(dataset)