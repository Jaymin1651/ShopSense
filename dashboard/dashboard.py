import streamlit as st
import pandas as pd

st.title("ShopSense Dashboard")

df = pd.read_csv("data/transactions.csv")

revenue = df["amount"].sum()
st.metric("Total Revenue", f"₹{revenue:,.2f}")

vendor_sales = df.groupby("vendor_id")["amount"].sum()
product_sales = df.groupby("product_id")["quantity"].sum()

st.subheader("Vendor Performance")
st.bar_chart(vendor_sales)

st.subheader("Product Performance")
st.bar_chart(product_sales)

st.subheader("Transaction Summary")
st.dataframe(df)
