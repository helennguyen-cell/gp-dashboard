import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
import warnings
warnings.filterwarnings('ignore')

# Page config
st.set_page_config(
    page_title="GP Analysis Dashboard - Entity 43",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 15px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    .positive-gp {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
    }
    .negative-gp {
        background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%);
    }
    .warning-gp {
        background: linear-gradient(135deg, #F2994A 0%, #F2C94C 100%);
    }
    .info-box {
        background-color: #e3f2fd;
        padding: 1rem;
        border-radius: 10px;
        border-left: 5px solid #1E88E5;
        margin: 1rem 0;
    }
    .alert-box {
        background-color: #ffebee;
        padding: 1rem;
        border-radius: 10px;
        border-left: 5px solid #e53935;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Database connections
@st.cache_resource
def get_postgres_connection():
    """Create PostgreSQL connection for sales data"""
    try:
        database_url = st.secrets.get("DATABASE_URL", "postgresql://postgres:VietnamFA2024@103.130.211.172:5432/postgres")
        engine = create_engine(database_url, connect_args={"connect_timeout": 10})
        return engine
    except Exception as e:
        st.warning(f"PostgreSQL connection error: {e}")
        return None

@st.cache_resource
def get_mysql_connection():
    """Create MySQL connection for product/brand master data"""
    try:
        # MySQL connection string format: mysql+pymysql://user:password@host:port/database
        mysql_url = st.secrets.get("MYSQL_URL", "mysql+pymysql://user:password@host:3306/vietape")
        engine = create_engine(mysql_url, connect_args={"connect_timeout": 10})
        return engine
    except Exception as e:
        st.warning(f"MySQL connection error: {e}")
        return None

# Load product master data from MySQL
@st.cache_data(ttl=3600)
def load_product_master():
    """Load product and brand master data from MySQL vietape database"""
    
    query = """
    SELECT 
        p.id as product_id,
        p.pt_code,
        p.name as product_name,
        p.package_size,
        p.uom,
        p.brand_id,
        b.brand_name,
        p.hs_code,
        p.description
    FROM products p
    LEFT JOIN brands b ON p.brand_id = b.id
    WHERE p.delete_flag = 0
    """
    
    try:
        engine = get_mysql_connection()
        if engine:
            with engine.connect() as conn:
                df = pd.read_sql(text(query), conn)
                return df
    except Exception as e:
        st.warning(f"Could not load product master from MySQL: {e}")
    
    return None

# Load sales data from PostgreSQL
@st.cache_data(ttl=3600)
def load_sales_data():
    """Load sales data from PostgreSQL"""
    
    query = """
    SELECT 
        siv.product_id,
        siv.sku,
        siv.product_name as sales_product_name,
        siv.pt_code as sales_pt_code,
        siv.brand as sales_brand,
        SUM(siv.net_amount_usd) as total_revenue,
        SUM(siv.quantity) as total_quantity,
        SUM(siv.net_amount_usd - siv.total_cost_usd) as system_gp,
        AVG(siv.unit_price_usd) as avg_selling_price,
        COUNT(DISTINCT siv.invoice_number) as invoice_count
    FROM sales_invoice_full_looker_view siv
    WHERE siv.entity_id = 43
      AND siv.invoice_date >= '2024-01-01'
      AND siv.net_amount_usd > 0
      AND siv.quantity > 0
    GROUP BY siv.product_id, siv.sku, siv.product_name, siv.pt_code, siv.brand
    """
    
    try:
        engine = get_postgres_connection()
        if engine:
            with engine.connect() as conn:
                df = pd.read_sql(text(query), conn)
                return df
    except Exception as e:
        st.warning(f"Could not load sales data from PostgreSQL: {e}")
    
    return None

# Load BOM costs from PostgreSQL
@st.cache_data(ttl=3600)
def load_bom_costs():
    """Load BOM-based costs from PostgreSQL"""
    
    query = """
    WITH bom_costs AS (
        SELECT 
            fi.product_id,
            COALESCE(SUM(
                CASE 
                    WHEN fi.material_id IS NOT NULL THEN 
                        COALESCE(fi.quantity, 0) * COALESCE(
                            (SELECT unit_price 
                             FROM purchase_invoice_line pil 
                             WHERE pil.material_id = fi.material_id 
                             ORDER BY created_at DESC
                             LIMIT 1), 0)
                    ELSE 0 
                END
            ), 0) as material_cost,
            COUNT(DISTINCT fi.material_id) as component_count
        FROM finished_goods_inventory fi
        WHERE fi.entity_id = 43
        GROUP BY fi.product_id
    )
    SELECT * FROM bom_costs WHERE material_cost > 0
    """
    
    try:
        engine = get_postgres_connection()
        if engine:
            with engine.connect() as conn:
                df = pd.read_sql(text(query), conn)
                return df
    except Exception as e:
        st.warning(f"Could not load BOM costs: {e}")
    
    return None

# Combine all data sources
@st.cache_data(ttl=3600)
def load_gp_data():
    """Load and combine GP analysis data from all sources"""
    
    # Try to load real data
    product_master = load_product_master()
    sales_data = load_sales_data()
    bom_costs = load_bom_costs()
    
    # Check if we have real data
    if sales_data is not None and not sales_data.empty:
        df = sales_data.copy()
        
        # Merge with product master from MySQL (for accurate names, brands, package sizes)
        if product_master is not None and not product_master.empty:
            df = df.merge(
                product_master[['product_id', 'product_name', 'pt_code', 'package_size', 'brand_name', 'uom']],
                on='product_id',
                how='left',
                suffixes=('_sales', '_master')
            )
            # Use master data where available, fallback to sales data
            df['product_name'] = df['product_name'].fillna(df['sales_product_name'])
            df['pt_code'] = df['pt_code'].fillna(df['sales_pt_code'])
            df['brand'] = df['brand_name'].fillna(df['sales_brand'])
        else:
            df['product_name'] = df['sales_product_name']
            df['pt_code'] = df['sales_pt_code']
            df['brand'] = df['sales_brand']
            df['package_size'] = None
        
        # Merge with BOM costs
        if bom_costs is not None and not bom_costs.empty:
            df = df.merge(bom_costs, on='product_id', how='left')
            df['material_cost'] = df['material_cost'].fillna(0)
            df['component_count'] = df['component_count'].fillna(0)
        else:
            df['material_cost'] = 0
            df['component_count'] = 0
        
        # Calculate unit costs
        df['unit_material_cost'] = np.where(
            df['total_quantity'] > 0,
            df['material_cost'] / df['total_quantity'],
            0
        )
        df['unit_freight_cost'] = df['unit_material_cost'] * 0.15
        df['unit_total_cost'] = df['unit_material_cost'] + df['unit_freight_cost']
        
        # Calculate GP
        df['total_cogs'] = df['total_quantity'] * df['unit_total_cost']
        df['calculated_gp'] = df['total_revenue'] - df['total_cogs']
        df['calculated_gp_pct'] = np.where(
            df['total_revenue'] > 0,
            (df['calculated_gp'] / df['total_revenue'] * 100).round(2),
            0
        )
        df['system_gp_pct'] = np.where(
            df['total_revenue'] > 0,
            (df['system_gp'] / df['total_revenue'] * 100).round(2),
            0
        )
        
        # BOM coverage
        df['has_bom'] = df['material_cost'] > 0
        df['bom_coverage'] = df['has_bom'].map({True: 'With BOM Cost', False: 'No BOM Cost'})
        
        return df
    
    # Fallback to sample data if no real data available
    st.info("📊 Using sample data for demonstration. Connect to databases for real data.")
    return generate_sample_data()

def generate_sample_data():
    """Generate realistic sample data for demonstration"""
    np.random.seed(42)
    n_products = 150
    
    # Realistic PT codes and brands based on vietape data
    pt_codes = ['VTI001000001', 'VTI001000002', 'VTI001000003', 'VTI001000004', 
                'VTI001000005', 'VTI001000006', 'VTI001000007', 'VTI001000008',
                'VTI015000007', 'VTI001000009']
    brands = ['Vietape', 'Inotech', '3M', 'Daesan', 'Tesa', 'Rogers', 'Vina Foam', 'F6']
    package_sizes = ['500mmx33m', '44"x50m', '44"x100m', '1260mmx33m', '50mmx45m', 
                     '47.50x33.70m', '0.13mmx18mmx18m', '25mmx50m', '100mmx33m']
    
    # Product names based on vietape
    product_names = [
        'Vietape SI3604 Kapton Tape', 'Vietape FP5302 Black PU foam', 
        'Vietape FP5301 PU White 7T', 'Vietape Paper tape', 
        'Băng keo điện PVC 3M Temflex', 'Vietape Pom7000 Ring Nhua',
        'Inotech Pa7001 Nhua Band Nylon66', 'Anh Phát Băng Keo Pvc Màu Vàng Tươi',
        'Mút xốp PU Foam 12T 44 Black', 'Băng keo giấy'
    ]
    
    df = pd.DataFrame({
        'product_id': range(1, n_products + 1),
        'sku': [f'SKU-{i:04d}' for i in range(1, n_products + 1)],
        'product_name': [np.random.choice(product_names) + f' #{i}' for i in range(1, n_products + 1)],
        'pt_code': np.random.choice(pt_codes, n_products),
        'brand': np.random.choice(brands, n_products),
        'package_size': np.random.choice(package_sizes, n_products),
        'total_revenue': np.random.exponential(15000, n_products) + 500,
        'total_quantity': np.random.randint(10, 500, n_products),
        'invoice_count': np.random.randint(1, 20, n_products),
    })
    
    # Cost simulation - mix of products
    cost_scenarios = np.random.choice(['low', 'medium', 'high', 'very_high', 'negative'], 
                                       n_products, p=[0.2, 0.35, 0.25, 0.12, 0.08])
    
    cost_multipliers = {
        'low': 0.55,
        'medium': 0.72,
        'high': 0.85,
        'very_high': 0.95,
        'negative': 1.08
    }
    
    df['avg_selling_price'] = df['total_revenue'] / df['total_quantity']
    df['unit_material_cost'] = df['avg_selling_price'] * [cost_multipliers[s] / 1.15 for s in cost_scenarios]
    df['unit_freight_cost'] = df['unit_material_cost'] * 0.15
    df['unit_total_cost'] = df['unit_material_cost'] + df['unit_freight_cost']
    
    df['total_cogs'] = df['total_quantity'] * df['unit_total_cost']
    df['calculated_gp'] = df['total_revenue'] - df['total_cogs']
    df['calculated_gp_pct'] = (df['calculated_gp'] / df['total_revenue'] * 100).round(2)
    df['system_gp'] = df['calculated_gp'] * (1 + (np.random.rand(n_products) - 0.5) * 0.1)
    df['system_gp_pct'] = (df['system_gp'] / df['total_revenue'] * 100).round(2)
    
    # BOM coverage - 80%+ have BOM
    df['has_bom'] = np.random.rand(n_products) < 0.85
    df['bom_coverage'] = df['has_bom'].map({True: 'With BOM Cost', False: 'No BOM Cost'})
    df['component_count'] = np.where(df['has_bom'], np.random.randint(3, 15, n_products), 0)
    
    return df

def classify_gp_status(gp_pct):
    """Classify GP percentage into status categories"""
    if gp_pct < 0:
        return 'NEGATIVE'
    elif gp_pct < 10:
        return 'CRITICAL'
    elif gp_pct < 20:
        return 'WARNING'
    elif gp_pct < 30:
        return 'GOOD'
    else:
        return 'EXCELLENT'

def get_status_color(status):
    """Get color for each status"""
    colors = {
        'NEGATIVE': '#e53935',
        'CRITICAL': '#FB8C00',
        'WARNING': '#FDD835',
        'GOOD': '#7CB342',
        'EXCELLENT': '#43A047'
    }
    return colors.get(status, '#9E9E9E')

def calculate_cost_increase_impact(df, material_increase_pct, freight_increase_pct):
    """Calculate impact of cost increases"""
    result = df.copy()
    
    # New costs after increase
    result['new_unit_material_cost'] = result['unit_material_cost'] * (1 + material_increase_pct / 100)
    result['new_unit_freight_cost'] = result['unit_freight_cost'] * (1 + freight_increase_pct / 100)
    result['new_unit_total_cost'] = result['new_unit_material_cost'] + result['new_unit_freight_cost']
    
    # New COGS and GP
    result['new_total_cogs'] = result['total_quantity'] * result['new_unit_total_cost']
    result['new_calculated_gp'] = result['total_revenue'] - result['new_total_cogs']
    result['new_gp_pct'] = np.where(
        result['total_revenue'] > 0,
        (result['new_calculated_gp'] / result['total_revenue'] * 100).round(2),
        0
    )
    
    # Changes
    result['gp_change'] = result['new_calculated_gp'] - result['calculated_gp']
    result['gp_pct_change'] = result['new_gp_pct'] - result['calculated_gp_pct']
    result['cogs_increase'] = result['new_total_cogs'] - result['total_cogs']
    result['cogs_increase_pct'] = np.where(
        result['total_cogs'] > 0,
        ((result['new_total_cogs'] / result['total_cogs'] - 1) * 100).round(2),
        0
    )
    
    # Status before and after
    result['status_before'] = result['calculated_gp_pct'].apply(classify_gp_status)
    result['status_after'] = result['new_gp_pct'].apply(classify_gp_status)
    result['status_changed'] = result['status_before'] != result['status_after']
    
    # Price needed to maintain margin
    result['price_for_same_gp_pct'] = np.where(
        result['calculated_gp_pct'] < 100,
        result['new_total_cogs'] / (1 - result['calculated_gp_pct']/100),
        result['new_total_cogs'] * 2
    )
    result['price_increase_needed'] = np.where(
        result['total_revenue'] > 0,
        ((result['price_for_same_gp_pct'] / result['total_revenue'] - 1) * 100).round(2),
        0
    )
    
    # Price for 15% minimum GP
    result['price_for_15pct_gp'] = result['new_total_cogs'] / 0.85
    result['price_increase_for_15pct'] = np.where(
        result['total_revenue'] > 0,
        ((result['price_for_15pct_gp'] / result['total_revenue'] - 1) * 100).round(2),
        0
    )
    
    return result

# Main App
def main():
    st.markdown('<p class="main-header">📊 GP Analysis Dashboard</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Entity 43 (Starboard/Vietape) - Cost Impact Analysis | Products with ≥80% BOM Coverage</p>', unsafe_allow_html=True)
    
    # Load data
    with st.spinner('Loading data...'):
        df = load_gp_data()
    
    if df is None or df.empty:
        st.error("No data available")
        return
    
    # Filter for products with BOM cost (≥80% coverage)
    df_with_bom = df[df['has_bom'] == True].copy()
    
    # Sidebar
    st.sidebar.header("📈 Cost Increase Simulation")
    st.sidebar.markdown("---")
    
    material_increase = st.sidebar.slider(
        "📦 Material Cost Increase (%)",
        min_value=0,
        max_value=50,
        value=10,
        step=1,
        help="Simulate material cost increase"
    )
    
    freight_increase = st.sidebar.slider(
        "🚚 Freight Cost Increase (%)",
        min_value=0,
        max_value=50,
        value=15,
        step=1,
        help="Simulate freight/logistics cost increase"
    )
    
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Filters")
    
    # PT Code filter
    pt_codes = ['All'] + sorted(df_with_bom['pt_code'].dropna().unique().tolist())
    selected_pt = st.sidebar.selectbox("PT Code", pt_codes)
    
    # Brand filter
    brands = ['All'] + sorted(df_with_bom['brand'].dropna().unique().tolist())
    selected_brand = st.sidebar.selectbox("Brand", brands)
    
    # Package Size filter (NEW)
    if 'package_size' in df_with_bom.columns:
        package_sizes = ['All'] + sorted(df_with_bom['package_size'].dropna().unique().tolist())
        selected_package = st.sidebar.selectbox("Package Size", package_sizes)
    else:
        selected_package = 'All'
    
    # Revenue filter
    min_revenue = st.sidebar.number_input(
        "Minimum Revenue (USD)",
        min_value=0,
        value=500,
        step=100
    )
    
    # Apply filters
    df_filtered = df_with_bom.copy()
    if selected_pt != 'All':
        df_filtered = df_filtered[df_filtered['pt_code'] == selected_pt]
    if selected_brand != 'All':
        df_filtered = df_filtered[df_filtered['brand'] == selected_brand]
    if selected_package != 'All' and 'package_size' in df_filtered.columns:
        df_filtered = df_filtered[df_filtered['package_size'] == selected_package]
    df_filtered = df_filtered[df_filtered['total_revenue'] >= min_revenue]
    
    # Add status column
    df_filtered['gp_status'] = df_filtered['calculated_gp_pct'].apply(classify_gp_status)
    
    # Calculate impact
    df_impact = calculate_cost_increase_impact(df_filtered, material_increase, freight_increase)
    
    # Data info
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"""
    **📊 Data Summary**
    - Total Products: {len(df_filtered):,}
    - With BOM Cost: {df_filtered['has_bom'].sum():,}
    - Date Range: 2024-01-01 to Present
    """)
    
    # Download button
    csv_data = df_impact.to_csv(index=False).encode('utf-8')
    st.sidebar.download_button(
        label="📥 Download Full Analysis (CSV)",
        data=csv_data,
        file_name="gp_impact_analysis.csv",
        mime="text/csv"
    )
    
        # Tabs
    tab1, tab2, tab3 = st.tabs(["📊 Current GP Analysis", "📈 Cost Impact Analysis", "💰 Đề Xuất Giá Bán"])
    
    # ================== TAB 1: CURRENT GP ANALYSIS ==================
    with tab1:
        st.header("Current GP Analysis (Before Cost Increase)")
        
        # Executive Summary
        col1, col2, col3, col4 = st.columns(4)
        
        total_revenue = df_filtered['total_revenue'].sum()
        total_cogs = df_filtered['total_cogs'].sum()
        total_calculated_gp = df_filtered['calculated_gp'].sum()
        total_system_gp = df_filtered['system_gp'].sum()
        
        with col1:
            st.markdown(f"""
            <div class="metric-container">
                <h3>💰 Total Revenue</h3>
                <h2>${total_revenue:,.0f}</h2>
                <p>{len(df_filtered)} products</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="metric-container negative-gp">
                <h3>📦 Total COGS</h3>
                <h2>${total_cogs:,.0f}</h2>
                <p>{(total_cogs/total_revenue*100):.1f}% of Revenue</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            gp_class = "positive-gp" if total_calculated_gp > 0 else "negative-gp"
            gp_pct = total_calculated_gp / total_revenue * 100
            st.markdown(f"""
            <div class="metric-container {gp_class}">
                <h3>📊 Calculated GP</h3>
                <h2>${total_calculated_gp:,.0f}</h2>
                <p>GP%: {gp_pct:.1f}%</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            system_gp_pct = total_system_gp / total_revenue * 100
            variance = total_calculated_gp - total_system_gp
            st.markdown(f"""
            <div class="metric-container warning-gp">
                <h3>🔄 System GP</h3>
                <h2>${total_system_gp:,.0f}</h2>
                <p>Variance: ${variance:,.0f}</p>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # GP Distribution
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🎯 GP Status Distribution")
            status_counts = df_filtered['gp_status'].value_counts()
            status_order = ['EXCELLENT', 'GOOD', 'WARNING', 'CRITICAL', 'NEGATIVE']
            status_counts = status_counts.reindex([s for s in status_order if s in status_counts.index])
            
            fig_pie = px.pie(
                values=status_counts.values,
                names=status_counts.index,
                color=status_counts.index,
                color_discrete_map={s: get_status_color(s) for s in status_order},
                hole=0.4
            )
            fig_pie.update_layout(height=350)
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with col2:
            st.subheader("📊 GP% Distribution by Range")
            
            bins = [-100, 0, 10, 20, 30, 100]
            labels = ['Negative (<0%)', 'Critical (0-10%)', 'Warning (10-20%)', 'Good (20-30%)', 'Excellent (>30%)']
            df_filtered['gp_range'] = pd.cut(df_filtered['calculated_gp_pct'], bins=bins, labels=labels)
            
            range_counts = df_filtered['gp_range'].value_counts().sort_index()
            
            fig_bar = px.bar(
                x=range_counts.index.astype(str),
                y=range_counts.values,
                color=range_counts.index.astype(str),
                color_discrete_sequence=['#e53935', '#FB8C00', '#FDD835', '#7CB342', '#43A047']
            )
            fig_bar.update_layout(
                height=350,
                showlegend=False,
                xaxis_title="GP Range",
                yaxis_title="Number of Products"
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        
        # Analysis by Category
        st.markdown("---")
        st.subheader("📈 Analysis by Category")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**By PT Code**")
            pt_analysis = df_filtered.groupby('pt_code').agg({
                'total_revenue': 'sum',
                'calculated_gp': 'sum',
                'product_id': 'count'
            }).reset_index()
            pt_analysis['gp_pct'] = (pt_analysis['calculated_gp'] / pt_analysis['total_revenue'] * 100).round(2)
            pt_analysis = pt_analysis.sort_values('total_revenue', ascending=False)
            pt_analysis.columns = ['PT Code', 'Revenue', 'GP USD', 'Products', 'GP%']
            st.dataframe(pt_analysis, use_container_width=True, hide_index=True)
        
        with col2:
            st.markdown("**By Brand**")
            brand_analysis = df_filtered.groupby('brand').agg({
                'total_revenue': 'sum',
                'calculated_gp': 'sum',
                'product_id': 'count'
            }).reset_index()
            brand_analysis['gp_pct'] = (brand_analysis['calculated_gp'] / brand_analysis['total_revenue'] * 100).round(2)
            brand_analysis = brand_analysis.sort_values('total_revenue', ascending=False)
            brand_analysis.columns = ['Brand', 'Revenue', 'GP USD', 'Products', 'GP%']
            st.dataframe(brand_analysis, use_container_width=True, hide_index=True)
        
        # Product Rankings
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        display_cols = ['pt_code', 'product_name', 'brand', 'package_size', 'total_revenue', 'calculated_gp', 'calculated_gp_pct', 'gp_status']
        display_cols = [c for c in display_cols if c in df_filtered.columns]
        
        with col1:
            st.subheader("🏆 Top 20 High GP Products")
            top_products = df_filtered.nlargest(20, 'calculated_gp_pct')[display_cols].copy()
            col_rename = {
                'pt_code': 'PT Code',
                'product_name': 'Product Name',
                'brand': 'Brand',
                'package_size': 'Package Size',
                'total_revenue': 'Revenue',
                'calculated_gp': 'GP USD',
                'calculated_gp_pct': 'GP%',
                'gp_status': 'Status'
            }
            top_products = top_products.rename(columns={k: v for k, v in col_rename.items() if k in top_products.columns})
            st.dataframe(top_products, use_container_width=True, hide_index=True)
        
        with col2:
            st.subheader("⚠️ Top 20 Low/Negative GP Products")
            bottom_products = df_filtered.nsmallest(20, 'calculated_gp_pct')[display_cols].copy()
            bottom_products = bottom_products.rename(columns={k: v for k, v in col_rename.items() if k in bottom_products.columns})
            st.dataframe(bottom_products, use_container_width=True, hide_index=True)
        
        # GP Variance Analysis
        st.markdown("---")
        st.subheader("🔍 GP Variance: System vs Calculated")
        
        fig_scatter = px.scatter(
            df_filtered,
            x='system_gp_pct',
            y='calculated_gp_pct',
            size='total_revenue',
            color='gp_status',
            color_discrete_map={s: get_status_color(s) for s in ['EXCELLENT', 'GOOD', 'WARNING', 'CRITICAL', 'NEGATIVE']},
            hover_data=['pt_code', 'product_name', 'brand', 'total_revenue'],
            labels={'system_gp_pct': 'System GP%', 'calculated_gp_pct': 'Calculated GP%'}
        )
        
        max_val = max(df_filtered['system_gp_pct'].max(), df_filtered['calculated_gp_pct'].max())
        min_val = min(df_filtered['system_gp_pct'].min(), df_filtered['calculated_gp_pct'].min())
        fig_scatter.add_trace(go.Scatter(
            x=[min_val, max_val],
            y=[min_val, max_val],
            mode='lines',
            line=dict(dash='dash', color='gray'),
            name='Perfect Match'
        ))
        
        fig_scatter.update_layout(height=500)
        st.plotly_chart(fig_scatter, use_container_width=True)
    
    # ================== TAB 2: COST IMPACT ANALYSIS ==================
    with tab2:
        st.header(f"Cost Impact Analysis: Material +{material_increase}%, Freight +{freight_increase}%")
        
        # Impact Summary
        st.subheader("📊 Impact Summary")
        
        total_new_cogs = df_impact['new_total_cogs'].sum()
        total_new_gp = df_impact['new_calculated_gp'].sum()
        total_cogs_increase = total_new_cogs - total_cogs
        total_gp_loss = total_new_gp - total_calculated_gp
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "COGS Before",
                f"${total_cogs:,.0f}",
                delta=None
            )
            st.metric(
                "COGS After",
                f"${total_new_cogs:,.0f}",
                delta=f"+${total_cogs_increase:,.0f}",
                delta_color="inverse"
            )
        
        with col2:
            st.metric(
                "GP Before",
                f"${total_calculated_gp:,.0f}",
                delta=f"{(total_calculated_gp/total_revenue*100):.1f}%"
            )
            st.metric(
                "GP After",
                f"${total_new_gp:,.0f}",
                delta=f"{total_gp_loss:,.0f}",
                delta_color="inverse"
            )
        
        with col3:
            gp_pct_before = total_calculated_gp / total_revenue * 100
            gp_pct_after = total_new_gp / total_revenue * 100
            pct_drop = gp_pct_after - gp_pct_before
            
            st.metric(
                "GP% Before",
                f"{gp_pct_before:.1f}%",
                delta=None
            )
            st.metric(
                "GP% After",
                f"{gp_pct_after:.1f}%",
                delta=f"{pct_drop:.1f} pts",
                delta_color="inverse"
            )
        
        with col4:
            products_turned_negative = len(df_impact[
                (df_impact['calculated_gp_pct'] >= 0) & (df_impact['new_gp_pct'] < 0)
            ])
            products_status_dropped = df_impact['status_changed'].sum()
            
            st.metric(
                "Products Turned Negative",
                f"{products_turned_negative}",
                delta="⚠️ Alert" if products_turned_negative > 0 else "✅ OK",
                delta_color="inverse" if products_turned_negative > 0 else "normal"
            )
            st.metric(
                "Products Status Changed",
                f"{products_status_dropped}",
                delta=f"of {len(df_impact)}"
            )
        
        # Cost Breakdown
        st.markdown("---")
        st.subheader("📦 Cost Breakdown Comparison")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Before Increase**")
            total_material_before = (df_impact['unit_material_cost'] * df_impact['total_quantity']).sum()
            total_freight_before = (df_impact['unit_freight_cost'] * df_impact['total_quantity']).sum()
            
            fig_before = px.pie(
                values=[total_material_before, total_freight_before],
                names=['Material Cost', 'Freight Cost'],
                color_discrete_sequence=['#1976D2', '#FF9800'],
                hole=0.4
            )
            fig_before.update_layout(height=300)
            st.plotly_chart(fig_before, use_container_width=True)
        
        with col2:
            st.markdown("**After Increase**")
            new_material_total = (df_impact['new_unit_material_cost'] * df_impact['total_quantity']).sum()
            new_freight_total = (df_impact['new_unit_freight_cost'] * df_impact['total_quantity']).sum()
            
            fig_after = px.pie(
                values=[new_material_total, new_freight_total],
                names=['Material Cost', 'Freight Cost'],
                color_discrete_sequence=['#1976D2', '#FF9800'],
                hole=0.4
            )
            fig_after.update_layout(height=300)
            st.plotly_chart(fig_after, use_container_width=True)
        
        # Status Migration Matrix
        st.markdown("---")
        st.subheader("🔄 Status Migration Matrix")
        
        migration = pd.crosstab(
            df_impact['status_before'], 
            df_impact['status_after'],
            margins=True
        )
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.dataframe(migration, use_container_width=True)
        
        with col2:
            st.markdown("""
            **Reading the Matrix:**
            - Rows = Status BEFORE increase
            - Columns = Status AFTER increase
            - Diagonal = Products that maintained status
            - Below diagonal = Status improved (rare)
            - Above diagonal = Status worsened
            """)
        
        # Status Change Visualization
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📉 Status Distribution Change")
            
            status_before = df_impact['status_before'].value_counts()
            status_after = df_impact['status_after'].value_counts()
            
            status_order = ['EXCELLENT', 'GOOD', 'WARNING', 'CRITICAL', 'NEGATIVE']
            
            fig_status = go.Figure()
            fig_status.add_trace(go.Bar(
                name='Before',
                x=[s for s in status_order if s in status_before.index],
                y=[status_before.get(s, 0) for s in status_order if s in status_before.index],
                marker_color='#1976D2'
            ))
            fig_status.add_trace(go.Bar(
                name='After',
                x=[s for s in status_order if s in status_after.index],
                y=[status_after.get(s, 0) for s in status_order if s in status_after.index],
                marker_color='#FF5722'
            ))
            fig_status.update_layout(barmode='group', height=400)
            st.plotly_chart(fig_status, use_container_width=True)
        
        with col2:
            st.subheader("⚡ GP% Change Distribution")
            
            fig_hist = px.histogram(
                df_impact,
                x='gp_pct_change',
                nbins=30,
                color_discrete_sequence=['#e53935']
            )
            fig_hist.update_layout(
                height=400,
                xaxis_title="GP% Change (points)",
                yaxis_title="Number of Products"
            )
            fig_hist.add_vline(x=0, line_dash="dash", line_color="gray")
            st.plotly_chart(fig_hist, use_container_width=True)
        
        # Risk Assessment
        st.markdown("---")
        st.subheader("⚠️ Risk Assessment: Products Most Affected")
        
        impact_display_cols = ['pt_code', 'product_name', 'brand', 'package_size', 'total_revenue', 
                               'calculated_gp_pct', 'new_gp_pct', 'gp_change', 'status_before', 'status_after']
        impact_display_cols = [c for c in impact_display_cols if c in df_impact.columns]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**🔴 Top 20 Products by GP Loss (USD)**")
            top_losers = df_impact.nsmallest(20, 'gp_change')[impact_display_cols].copy()
            
            impact_col_rename = {
                'pt_code': 'PT Code',
                'product_name': 'Product',
                'brand': 'Brand',
                'package_size': 'Package',
                'total_revenue': 'Revenue',
                'calculated_gp_pct': 'GP% Before',
                'new_gp_pct': 'GP% After',
                'gp_change': 'GP Loss',
                'status_before': 'Status Before',
                'status_after': 'Status After'
            }
            top_losers = top_losers.rename(columns={k: v for k, v in impact_col_rename.items() if k in top_losers.columns})
            if 'GP Loss' in top_losers.columns:
                top_losers['GP Loss'] = top_losers['GP Loss'].apply(lambda x: f"${x:,.0f}")
            st.dataframe(top_losers, use_container_width=True, hide_index=True)
        
        with col2:
            st.markdown("**🚨 Products Turned Negative GP**")
            turned_negative = df_impact[
                (df_impact['calculated_gp_pct'] >= 0) & (df_impact['new_gp_pct'] < 0)
            ]
            
            neg_display_cols = ['pt_code', 'product_name', 'brand', 'package_size', 'total_revenue', 
                               'calculated_gp_pct', 'new_gp_pct', 'price_increase_needed']
            neg_display_cols = [c for c in neg_display_cols if c in turned_negative.columns]
            
            if len(turned_negative) > 0:
                turned_negative_display = turned_negative[neg_display_cols].copy()
                neg_col_rename = {
                    'pt_code': 'PT Code',
                    'product_name': 'Product',
                    'brand': 'Brand',
                    'package_size': 'Package',
                    'total_revenue': 'Revenue',
                    'calculated_gp_pct': 'GP% Before',
                    'new_gp_pct': 'GP% After',
                    'price_increase_needed': 'Price Increase %'
                }
                turned_negative_display = turned_negative_display.rename(
                    columns={k: v for k, v in neg_col_rename.items() if k in turned_negative_display.columns}
                )
                st.dataframe(turned_negative_display, use_container_width=True, hide_index=True)
            else:
                st.success("✅ No products turned negative with this cost increase scenario!")
        
        # Summary Alert
        if products_turned_negative > 0 or gp_pct_after < 15:
            st.markdown(f"""
            <div class="alert-box">
            <h4>⚠️ ACTION REQUIRED</h4>
            <p>With Material +{material_increase}% and Freight +{freight_increase}% cost increase:</p>
            <ul>
                <li><strong>{products_turned_negative}</strong> products will have NEGATIVE gross profit</li>
                <li>Overall GP% will drop from <strong>{gp_pct_before:.1f}%</strong> to <strong>{gp_pct_after:.1f}%</strong></li>
                <li>Total GP loss: <strong>${abs(total_gp_loss):,.0f}</strong></li>
            </ul>
            </div>
            """, unsafe_allow_html=True)
    
    # ================== TAB 3: ĐỀ XUẤT GIÁ BÁN ==================
    with tab3:
        st.header("💰 Đề Xuất Giá Bán Mới")
        
        st.markdown(f"""
        <div class="info-box">
        <h4>📋 Phương pháp tính giá đề xuất</h4>
        <p>Giá bán đề xuất được tính dựa trên:</p>
        <ul>
            <li><strong>Chi phí mới</strong> = Chi phí hiện tại × (1 + % tăng Material) × (1 + % tăng Freight)</li>
            <li><strong>Giá đề xuất</strong> = Chi phí mới / (1 - Target GP%)</li>
            <li>Áp dụng kịch bản: Material +{material_increase}%, Freight +{freight_increase}%</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)
        
        # Pricing Settings
        st.subheader("⚙️ Cài đặt Target GP%")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            target_gp_1 = st.number_input("Target GP% 1", value=15, min_value=5, max_value=50, step=1)
        with col2:
            target_gp_2 = st.number_input("Target GP% 2", value=20, min_value=5, max_value=50, step=1)
        with col3:
            target_gp_3 = st.number_input("Target GP% 3", value=25, min_value=5, max_value=50, step=1)
        with col4:
            target_gp_4 = st.number_input("Target GP% 4", value=30, min_value=5, max_value=50, step=1)
        
        # Calculate recommended prices
        df_pricing = df_impact.copy()
        
        # Current average selling price
        df_pricing['current_avg_price'] = df_pricing['total_revenue'] / df_pricing['total_quantity']
        
        # New unit cost after increase
        df_pricing['new_unit_cost'] = df_pricing['new_unit_total_cost']
        
        # Calculate prices for each target GP
        df_pricing[f'price_for_{target_gp_1}pct'] = df_pricing['new_unit_cost'] / (1 - target_gp_1/100)
        df_pricing[f'price_for_{target_gp_2}pct'] = df_pricing['new_unit_cost'] / (1 - target_gp_2/100)
        df_pricing[f'price_for_{target_gp_3}pct'] = df_pricing['new_unit_cost'] / (1 - target_gp_3/100)
        df_pricing[f'price_for_{target_gp_4}pct'] = df_pricing['new_unit_cost'] / (1 - target_gp_4/100)
        
        # Calculate price increase percentages
        df_pricing[f'increase_for_{target_gp_1}pct'] = ((df_pricing[f'price_for_{target_gp_1}pct'] / df_pricing['current_avg_price']) - 1) * 100
        df_pricing[f'increase_for_{target_gp_2}pct'] = ((df_pricing[f'price_for_{target_gp_2}pct'] / df_pricing['current_avg_price']) - 1) * 100
        df_pricing[f'increase_for_{target_gp_3}pct'] = ((df_pricing[f'price_for_{target_gp_3}pct'] / df_pricing['current_avg_price']) - 1) * 100
        df_pricing[f'increase_for_{target_gp_4}pct'] = ((df_pricing[f'price_for_{target_gp_4}pct'] / df_pricing['current_avg_price']) - 1) * 100
        
        # Priority classification
        def classify_priority(row):
            if row['new_gp_pct'] < 0:
                return '🔴 CRITICAL - Lỗ'
            elif row['new_gp_pct'] < 10:
                return '🟠 HIGH - GP < 10%'
            elif row['new_gp_pct'] < 15:
                return '🟡 MEDIUM - GP < 15%'
            elif row['new_gp_pct'] < 20:
                return '🟢 LOW - GP < 20%'
            else:
                return '✅ OK - GP >= 20%'
        
        df_pricing['priority'] = df_pricing.apply(classify_priority, axis=1)
        df_pricing['priority_order'] = df_pricing['priority'].map({
            '🔴 CRITICAL - Lỗ': 1,
            '🟠 HIGH - GP < 10%': 2,
            '🟡 MEDIUM - GP < 15%': 3,
            '🟢 LOW - GP < 20%': 4,
            '✅ OK - GP >= 20%': 5
        })
        
        # Summary metrics
        st.markdown("---")
        st.subheader("📊 Tổng quan sản phẩm cần điều chỉnh giá")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        critical_count = len(df_pricing[df_pricing['new_gp_pct'] < 0])
        high_count = len(df_pricing[(df_pricing['new_gp_pct'] >= 0) & (df_pricing['new_gp_pct'] < 10)])
        medium_count = len(df_pricing[(df_pricing['new_gp_pct'] >= 10) & (df_pricing['new_gp_pct'] < 15)])
        low_count = len(df_pricing[(df_pricing['new_gp_pct'] >= 15) & (df_pricing['new_gp_pct'] < 20)])
        ok_count = len(df_pricing[df_pricing['new_gp_pct'] >= 20])
        
        with col1:
            st.metric("🔴 CRITICAL (Lỗ)", f"{critical_count}", delta="Cần xử lý ngay")
        with col2:
            st.metric("🟠 HIGH (GP<10%)", f"{high_count}", delta="Ưu tiên cao")
        with col3:
            st.metric("🟡 MEDIUM (GP<15%)", f"{medium_count}", delta="Cần review")
        with col4:
            st.metric("🟢 LOW (GP<20%)", f"{low_count}", delta="Theo dõi")
        with col5:
            st.metric("✅ OK (GP>=20%)", f"{ok_count}", delta="Ổn định")
        
        # Filter by priority
        st.markdown("---")
        st.subheader("🔍 Lọc theo mức độ ưu tiên")
        
        priority_filter = st.multiselect(
            "Chọn mức độ ưu tiên:",
            options=['🔴 CRITICAL - Lỗ', '🟠 HIGH - GP < 10%', '🟡 MEDIUM - GP < 15%', '🟢 LOW - GP < 20%', '✅ OK - GP >= 20%'],
            default=['🔴 CRITICAL - Lỗ', '🟠 HIGH - GP < 10%', '🟡 MEDIUM - GP < 15%']
        )
        
        if priority_filter:
            df_pricing_filtered = df_pricing[df_pricing['priority'].isin(priority_filter)].copy()
        else:
            df_pricing_filtered = df_pricing.copy()
        
        df_pricing_filtered = df_pricing_filtered.sort_values(['priority_order', 'new_gp_pct'])
        
        # Main pricing table
        st.markdown("---")
        st.subheader(f"📋 Bảng Đề Xuất Giá Bán ({len(df_pricing_filtered)} sản phẩm)")
        
        # Prepare display dataframe
        pricing_display = df_pricing_filtered[[
            'pt_code', 'product_name', 'brand', 'package_size',
            'total_revenue', 'total_quantity',
            'current_avg_price', 'new_unit_cost',
            'calculated_gp_pct', 'new_gp_pct',
            f'price_for_{target_gp_1}pct', f'price_for_{target_gp_2}pct', 
            f'price_for_{target_gp_3}pct', f'price_for_{target_gp_4}pct',
            f'increase_for_{target_gp_2}pct',
            'priority'
        ]].copy()
        
        # Rename columns for display
        pricing_display.columns = [
            'PT Code', 'Tên Sản Phẩm', 'Brand', 'Package',
            'Doanh Thu', 'Số Lượng',
            'Giá TB Hiện Tại', 'Chi Phí Mới/Unit',
            'GP% Hiện Tại', 'GP% Sau Tăng CP',
            f'Giá Đề Xuất ({target_gp_1}%)', f'Giá Đề Xuất ({target_gp_2}%)',
            f'Giá Đề Xuất ({target_gp_3}%)', f'Giá Đề Xuất ({target_gp_4}%)',
            f'% Tăng Giá (Target {target_gp_2}%)',
            'Mức Độ Ưu Tiên'
        ]
        
        # Format numeric columns
        for col in ['Doanh Thu', 'Giá TB Hiện Tại', 'Chi Phí Mới/Unit',
                    f'Giá Đề Xuất ({target_gp_1}%)', f'Giá Đề Xuất ({target_gp_2}%)',
                    f'Giá Đề Xuất ({target_gp_3}%)', f'Giá Đề Xuất ({target_gp_4}%)']:
            if col in pricing_display.columns:
                pricing_display[col] = pricing_display[col].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) else "N/A")
        
        for col in ['GP% Hiện Tại', 'GP% Sau Tăng CP', f'% Tăng Giá (Target {target_gp_2}%)']:
            if col in pricing_display.columns:
                pricing_display[col] = pricing_display[col].apply(lambda x: f"{x:.1f}%" if pd.notnull(x) else "N/A")
        
        st.dataframe(pricing_display, use_container_width=True, hide_index=True, height=500)
        
        # Download section
        st.markdown("---")
        st.subheader("📥 Tải xuống báo cáo đề xuất giá")
        
        # Prepare export dataframe with all data
        export_df = df_pricing_filtered[[
            'pt_code', 'product_name', 'brand', 'package_size',
            'total_revenue', 'total_quantity',
            'current_avg_price', 'unit_material_cost', 'unit_freight_cost', 'unit_total_cost',
            'new_unit_material_cost', 'new_unit_freight_cost', 'new_unit_cost',
            'calculated_gp_pct', 'new_gp_pct',
            f'price_for_{target_gp_1}pct', f'price_for_{target_gp_2}pct',
            f'price_for_{target_gp_3}pct', f'price_for_{target_gp_4}pct',
            f'increase_for_{target_gp_1}pct', f'increase_for_{target_gp_2}pct',
            f'increase_for_{target_gp_3}pct', f'increase_for_{target_gp_4}pct',
            'priority'
        ]].copy()
        
        export_df.columns = [
            'PT Code', 'Product Name', 'Brand', 'Package Size',
            'Total Revenue USD', 'Total Quantity',
            'Current Avg Price', 'Current Material Cost/Unit', 'Current Freight Cost/Unit', 'Current Total Cost/Unit',
            'New Material Cost/Unit', 'New Freight Cost/Unit', 'New Total Cost/Unit',
            'Current GP%', 'New GP% After Cost Increase',
            f'Recommended Price ({target_gp_1}% GP)', f'Recommended Price ({target_gp_2}% GP)',
            f'Recommended Price ({target_gp_3}% GP)', f'Recommended Price ({target_gp_4}% GP)',
            f'Price Increase % for {target_gp_1}% GP', f'Price Increase % for {target_gp_2}% GP',
            f'Price Increase % for {target_gp_3}% GP', f'Price Increase % for {target_gp_4}% GP',
            'Priority Level'
        ]
        
        col1, col2 = st.columns(2)
        
        with col1:
            csv_export = export_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Tải CSV - Đề Xuất Giá Đầy Đủ",
                data=csv_export,
                file_name=f"price_recommendation_{material_increase}pct_material_{freight_increase}pct_freight.csv",
                mime="text/csv"
            )
        
        with col2:
            # Summary export
            summary_data = {
                'Metric': [
                    'Total Products Analyzed',
                    'Products Need Price Adjustment',
                    'Critical (Negative GP)',
                    'High Priority (GP < 10%)',
                    'Medium Priority (GP < 15%)',
                    f'Avg Price Increase for {target_gp_2}% GP',
                    'Material Cost Increase Applied',
                    'Freight Cost Increase Applied'
                ],
                'Value': [
                    len(df_pricing),
                    len(df_pricing[df_pricing['new_gp_pct'] < 20]),
                    critical_count,
                    high_count,
                    medium_count,
                    f"{df_pricing[f'increase_for_{target_gp_2}pct'].mean():.1f}%",
                    f"{material_increase}%",
                    f"{freight_increase}%"
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_csv = summary_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Tải CSV - Tóm Tắt",
                data=summary_csv,
                file_name=f"price_recommendation_summary.csv",
                mime="text/csv"
            )
        
        # Visual: Price Increase Distribution
        st.markdown("---")
        st.subheader("📈 Phân bổ mức tăng giá đề xuất")
        
        col1, col2 = st.columns(2)
        
        with col1:
            fig_increase = px.histogram(
                df_pricing_filtered,
                x=f'increase_for_{target_gp_2}pct',
                nbins=25,
                color='priority',
                title=f"Phân bổ % Tăng Giá để đạt {target_gp_2}% GP",
                labels={f'increase_for_{target_gp_2}pct': '% Tăng Giá'},
                color_discrete_sequence=['#e53935', '#FB8C00', '#FDD835', '#7CB342', '#43A047']
            )
            fig_increase.update_layout(height=400)
            st.plotly_chart(fig_increase, use_container_width=True)
        
        with col2:
            # Scatter: Current GP vs Required Price Increase
            fig_scatter = px.scatter(
                df_pricing_filtered,
                x='new_gp_pct',
                y=f'increase_for_{target_gp_2}pct',
                size='total_revenue',
                color='priority',
                hover_data=['pt_code', 'product_name', 'brand'],
                title=f"GP% Mới vs % Tăng Giá Cần Thiết (Target {target_gp_2}%)",
                labels={
                    'new_gp_pct': 'GP% Sau Tăng Chi Phí',
                    f'increase_for_{target_gp_2}pct': '% Tăng Giá Cần Thiết'
                },
                color_discrete_sequence=['#e53935', '#FB8C00', '#FDD835', '#7CB342', '#43A047']
            )
            fig_scatter.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="Không cần tăng")
            fig_scatter.add_vline(x=target_gp_2, line_dash="dash", line_color="green", annotation_text=f"Target {target_gp_2}%")
            fig_scatter.update_layout(height=400)
            st.plotly_chart(fig_scatter, use_container_width=True)
        
        # Quick Action Items
        st.markdown("---")
        st.subheader("🎯 Hành động đề xuất")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"""
            <div class="alert-box">
            <h4>🔴 Sản phẩm cần điều chỉnh giá NGAY ({critical_count + high_count} sản phẩm)</h4>
            <ul>
                <li><strong>{critical_count}</strong> sản phẩm đang LỖ sau khi tăng chi phí</li>
                <li><strong>{high_count}</strong> sản phẩm có GP% dưới 10%</li>
                <li>Tổng doanh thu ảnh hưởng: <strong>${df_pricing[df_pricing['new_gp_pct'] < 10]['total_revenue'].sum():,.0f}</strong></li>
            </ul>
            <p><strong>➡️ Đề xuất:</strong> Tăng giá theo cột "Giá Đề Xuất ({target_gp_2}%)" hoặc đàm phán lại với nhà cung cấp</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            avg_increase_critical = df_pricing[df_pricing['new_gp_pct'] < 10][f'increase_for_{target_gp_2}pct'].mean()
            avg_increase_all = df_pricing[f'increase_for_{target_gp_2}pct'].mean()
            
            st.markdown(f"""
            <div class="info-box">
            <h4>📊 Tóm tắt điều chỉnh giá</h4>
            <table style="width:100%">
                <tr><td>Mức tăng giá TB (sản phẩm critical):</td><td><strong>{avg_increase_critical:.1f}%</strong></td></tr>
                <tr><td>Mức tăng giá TB (tất cả):</td><td><strong>{avg_increase_all:.1f}%</strong></td></tr>
                <tr><td>Sản phẩm cần tăng >20%:</td><td><strong>{len(df_pricing[df_pricing[f'increase_for_{target_gp_2}pct'] > 20])}</strong></td></tr>
                <tr><td>Sản phẩm không cần tăng:</td><td><strong>{len(df_pricing[df_pricing[f'increase_for_{target_gp_2}pct'] <= 0])}</strong></td></tr>
            </table>
            </div>
            """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()

