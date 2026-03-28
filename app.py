import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
import warnings
warnings.filterwarnings('ignore')

st.set_page_config(page_title="GP Analysis Dashboard", page_icon="📊", layout="wide")

@st.cache_resource
def get_postgres_connection():
    try:
        engine = create_engine(st.secrets["DATABASE_URL"], pool_pre_ping=True, pool_recycle=300, connect_args={"connect_timeout": 30})
        return engine
    except Exception as e:
        st.error(f"PostgreSQL connection error: {e}")
        return None

@st.cache_resource
def get_mysql_connection():
    try:
        engine = create_engine(st.secrets["MYSQL_URL"], pool_pre_ping=True, pool_recycle=300, connect_args={"connect_timeout": 30})
        return engine
    except Exception as e:
        st.error(f"MySQL connection error: {e}")
        return None

@st.cache_data(ttl=3600)
def load_sales_data():
    engine = get_postgres_connection()
    if engine is None:
        return pd.DataFrame()
    query = """
    SELECT product_id, product_name, pt_code, brand_id, SUM(quantity) as total_qty, SUM(revenue_after_discount) as total_revenue, SUM(cogs) as total_cogs
    FROM sales_invoice_full_looker_view
    WHERE entity_id = 43 AND invoice_date >= '2024-01-01'
    GROUP BY product_id, product_name, pt_code, brand_id
    HAVING SUM(quantity) > 0
    """
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
        return df
    except Exception as e:
        st.error(f"Error loading sales data: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_bom_costs():
    engine = get_postgres_connection()
    if engine is None:
        return pd.DataFrame()
    query = """
    SELECT DISTINCT ON (product_id) product_id, material_cost_per_unit, freight_cost_per_unit, total_unit_cost
    FROM vw_product_cost_from_bom
    WHERE entity_id = 43
    ORDER BY product_id, last_updated DESC
    """
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
        return df
    except Exception as e:
        st.error(f"Error loading BOM costs: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_brand_data():
    engine = get_mysql_connection()
    if engine is None:
        return pd.DataFrame()
    query = "SELECT id as brand_id, brand_name FROM brands"
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
        return df
    except Exception as e:
        st.error(f"Error loading brand data: {e}")
        return pd.DataFrame()

def classify_gp(gp_pct):
    if gp_pct < 0:
        return "NEGATIVE"
    elif gp_pct < 10:
        return "CRITICAL"
    elif gp_pct < 20:
        return "WARNING"
    elif gp_pct < 30:
        return "GOOD"
    else:
        return "EXCELLENT"

def main():
    st.title("📊 GP Analysis Dashboard - Entity 43")
    st.markdown("**Starboard/Vietape - Cost Impact Analysis**")
    
    with st.spinner("Loading data..."):
        sales_df = load_sales_data()
        bom_df = load_bom_costs()
        brand_df = load_brand_data()
    
    if sales_df.empty:
        st.error("❌ Cannot load sales data. Please check database connection.")
        st.info("Make sure Secrets are configured correctly in Streamlit Cloud.")
        return
    
    st.success(f"✅ Loaded {len(sales_df)} products from sales data")
    
    if not bom_df.empty:
        df = sales_df.merge(bom_df, on='product_id', how='left')
        st.success(f"✅ Loaded {len(bom_df)} products with BOM costs")
    else:
        df = sales_df.copy()
        df['material_cost_per_unit'] = 0
        df['freight_cost_per_unit'] = 0
        df['total_unit_cost'] = 0
        st.warning("⚠️ BOM costs not available - using COGS from sales data")
    
    if not brand_df.empty:
        df = df.merge(brand_df, on='brand_id', how='left')
        df['brand_name'] = df['brand_name'].fillna('Unknown')
    else:
        df['brand_name'] = 'Unknown'
    
    df['unit_price'] = np.where(df['total_qty'] > 0, df['total_revenue'] / df['total_qty'], 0)
    df['unit_cogs'] = np.where(df['total_qty'] > 0, df['total_cogs'] / df['total_qty'], 0)
    df['gp_usd'] = df['total_revenue'] - df['total_cogs']
    df['gp_pct'] = np.where(df['total_revenue'] > 0, (df['gp_usd'] / df['total_revenue']) * 100, 0)
    df['status'] = df['gp_pct'].apply(classify_gp)
    
    st.sidebar.header("🎛️ Cost Adjustment")
    material_increase = st.sidebar.slider("Material Cost Increase (%)", 0, 50, 10, 1)
    freight_increase = st.sidebar.slider("Freight Cost Increase (%)", 0, 50, 15, 1)
    
    st.sidebar.header("🔍 Filters")
    min_revenue = st.sidebar.number_input("Minimum Revenue ($)", 0, 1000000, 1000, 100)
    df_filtered = df[df['total_revenue'] >= min_revenue].copy()
    
    tab1, tab2 = st.tabs(["📈 Current GP Analysis", "⚠️ Cost Impact Analysis"])
    
    with tab1:
        st.header("Current GP Performance")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Revenue", f"${df_filtered['total_revenue'].sum():,.0f}")
        with col2:
            st.metric("Total COGS", f"${df_filtered['total_cogs'].sum():,.0f}")
        with col3:
            total_gp = df_filtered['gp_usd'].sum()
            st.metric("Total GP", f"${total_gp:,.0f}")
        with col4:
            avg_gp_pct = (total_gp / df_filtered['total_revenue'].sum() * 100) if df_filtered['total_revenue'].sum() > 0 else 0
            st.metric("Avg GP%", f"{avg_gp_pct:.1f}%")
        
        col1, col2 = st.columns(2)
        with col1:
            status_counts = df_filtered['status'].value_counts()
            fig = px.pie(values=status_counts.values, names=status_counts.index, title="Products by GP Status", color=status_counts.index, color_discrete_map={"NEGATIVE": "red", "CRITICAL": "orange", "WARNING": "yellow", "GOOD": "lightgreen", "EXCELLENT": "green"})
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            fig = px.histogram(df_filtered, x='gp_pct', nbins=30, title="GP% Distribution", labels={'gp_pct': 'GP %'})
            fig.add_vline(x=0, line_dash="dash", line_color="red")
            fig.add_vline(x=20, line_dash="dash", line_color="green")
            st.plotly_chart(fig, use_container_width=True)
        
        st.subheader("📋 Product Details")
        display_df = df_filtered[['product_name', 'pt_code', 'brand_name', 'total_qty', 'total_revenue', 'total_cogs', 'gp_usd', 'gp_pct', 'status']].sort_values('total_revenue', ascending=False)
        display_df.columns = ['Product', 'PT Code', 'Brand', 'Qty', 'Revenue', 'COGS', 'GP $', 'GP %', 'Status']
        st.dataframe(display_df.head(50).style.format({'Revenue': '${:,.0f}', 'COGS': '${:,.0f}', 'GP $': '${:,.0f}', 'GP %': '{:.1f}%'}), use_container_width=True)
    
    with tab2:
        st.header("Cost Increase Impact Analysis")
        st.info(f"📊 Simulating: **+{material_increase}% Material** and **+{freight_increase}% Freight** cost increase")
        
        df_impact = df_filtered.copy()
        
        if 'material_cost_per_unit' in df_impact.columns and df_impact['material_cost_per_unit'].sum() > 0:
            df_impact['new_material'] = df_impact['material_cost_per_unit'] * (1 + material_increase/100)
            df_impact['new_freight'] = df_impact['freight_cost_per_unit'] * (1 + freight_increase/100)
            df_impact['new_unit_cost'] = df_impact['new_material'] + df_impact['new_freight']
            df_impact['new_cogs'] = df_impact['new_unit_cost'] * df_impact['total_qty']
        else:
            df_impact['new_cogs'] = df_impact['total_cogs'] * (1 + (material_increase + freight_increase/2)/100)
        
        df_impact['new_gp_usd'] = df_impact['total_revenue'] - df_impact['new_cogs']
        df_impact['new_gp_pct'] = np.where(df_impact['total_revenue'] > 0, (df_impact['new_gp_usd'] / df_impact['total_revenue']) * 100, 0)
        df_impact['new_status'] = df_impact['new_gp_pct'].apply(classify_gp)
        df_impact['gp_change'] = df_impact['new_gp_pct'] - df_impact['gp_pct']
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            old_gp = df_filtered['gp_usd'].sum()
            new_gp = df_impact['new_gp_usd'].sum()
            st.metric("Total GP (Before)", f"${old_gp:,.0f}")
        with col2:
            st.metric("Total GP (After)", f"${new_gp:,.0f}", delta=f"${new_gp-old_gp:,.0f}")
        with col3:
            old_gp_pct = (old_gp / df_filtered['total_revenue'].sum() * 100) if df_filtered['total_revenue'].sum() > 0 else 0
            new_gp_pct = (new_gp / df_impact['total_revenue'].sum() * 100) if df_impact['total_revenue'].sum() > 0 else 0
            st.metric("Avg GP% (Before)", f"{old_gp_pct:.1f}%")
        with col4:
            st.metric("Avg GP% (After)", f"{new_gp_pct:.1f}%", delta=f"{new_gp_pct-old_gp_pct:.1f}%")
        
        st.subheader("🚨 Products Most Affected")
        worst_impact = df_impact.nsmallest(20, 'gp_change')[['product_name', 'brand_name', 'total_revenue', 'gp_pct', 'new_gp_pct', 'gp_change', 'status', 'new_status']]
        worst_impact.columns = ['Product', 'Brand', 'Revenue', 'GP% Before', 'GP% After', 'Change', 'Status Before', 'Status After']
        st.dataframe(worst_impact.style.format({'Revenue': '${:,.0f}', 'GP% Before': '{:.1f}%', 'GP% After': '{:.1f}%', 'Change': '{:.1f}%'}), use_container_width=True)
        
        st.subheader("⚠️ Products Turning Negative GP")
        turning_negative = df_impact[(df_impact['gp_pct'] >= 0) & (df_impact['new_gp_pct'] < 0)]
        if len(turning_negative) > 0:
            st.error(f"🚨 {len(turning_negative)} products will have NEGATIVE GP after cost increase!")
            neg_display = turning_negative[['product_name', 'brand_name', 'total_revenue', 'gp_pct', 'new_gp_pct']].sort_values('total_revenue', ascending=False)
            neg_display.columns = ['Product', 'Brand', 'Revenue', 'GP% Before', 'GP% After']
            st.dataframe(neg_display.style.format({'Revenue': '${:,.0f}', 'GP% Before': '{:.1f}%', 'GP% After': '{:.1f}%'}), use_container_width=True)
        else:
            st.success("✅ No products will turn negative GP with this cost increase")

if __name__ == "__main__":
    main()
