import pandas as pd


def load_transactions(csv_path: str = "data/transactions.csv"):
    return pd.read_csv(csv_path)

def total_revenue(csv_path: str = "data/transactions.csv"):
    df = load_transactions(csv_path)
    return float(df["amount"].sum())

def vendor_revenue(csv_path: str = "data/transactions.csv"):
    df = load_transactions(csv_path)
    return df.groupby("vendor_id", as_index=False)["amount"].sum()

def product_revenue(csv_path: str = "data/transactions.csv"):
    df = load_transactions(csv_path)
    return df.groupby("product_id", as_index=False)["amount"].sum()

def top_product(csv_path: str = "data/transactions.csv"):
    df = load_transactions(csv_path)
    return int(df.groupby("product_id")["quantity"].sum().idxmax())

def revenue_by_vendor(csv_path: str = "data/transactions.csv"):
    df = load_transactions(csv_path)
    return df.groupby("vendor_id")["amount"].sum().to_dict()
