import streamlit as st
import pandas as pd
import mysql.connector
from decimal import Decimal
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="GP Analysis Dashboard", layout="wide")

def get_connection():
    return mysql.connector.connect(
        host="erp-all-production.cx1uaj6vj8s5.ap-southeast-1.rds.amazonaws.com",
        port=3306,
        database="vietape",
        user="helen_nguyen",
        password="Helen@12398!",
        consume_results=True
    )

def convert_decimals(df):
    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col] = df[col].apply(lambda x: float(x) if isinstance(x, Decimal) else x)
            except:
                pass
    return df

st.title("📊 GP Analysis Dashboard - Starboard/Vietape")

# ============== CHECK SCHEMA ==============
conn = get_connection()
cursor = conn.cursor(dictionary=True)

cursor.execute("""
    SELECT COLUMN_NAME 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = 'vietape' 
    AND TABLE_NAME = 'sales_invoice_full_looker_view'
""")
columns = [row['COLUMN_NAME'] for row in cursor.fetchall()]

# Also check products table for package_size
cursor.execute("""
    SELECT COLUMN_NAME 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = 'vietape' 
    AND TABLE_NAME = 'products'
""")
product_columns = [row['COLUMN_NAME'] for row in cursor.fetchall()]

cursor.close()
conn.close()

with st.expander("📋 View Available Columns (Debug)"):
    col1, col2 = st.columns(2)
    with col1:
        st.write("**sales_invoice_full_looker_view:**")
        st.write(sorted(columns))
    with col2:
        st.write("**products table:**")
        st.write(sorted(product_columns))

# Check if package_size exists
has_package_size_invoice = 'package_size' in columns or 'pkg_size' in columns
has_package_size_product = 'package_size' in product_columns or 'pkg_size' in product_columns
package_size_col = 'package_size' if 'package_size' in columns else 'pkg_size' if 'pkg_size' in columns else None

# ============== SIDEBAR FILTERS ==============
st.sidebar.header("🔍 Filters")

conn = get_connection()
cursor = conn.cursor(dictionary=True)

# Date filter
st.sidebar.subheader("📅 Time Period")
date_options = {
    "Last 30 days": 30,
    "Last 3 months": 90,
    "Last 6 months": 180,
    "Last 12 months": 365,
    "All time": 9999
}
selected_period = st.sidebar.selectbox("Select Period", list(date_options.keys()), index=2)
days_back = date_options[selected_period]

# Brand filter
brand_col = 'brand' if 'brand' in columns else 'brand_name' if 'brand_name' in columns else None
brand_id = None
selected_brand = "All Brands"

if brand_col:
    cursor.execute(f"""
        SELECT DISTINCT {brand_col} as brand_name
        FROM sales_invoice_full_looker_view
        WHERE legal_entity_id = 43 AND {brand_col} IS NOT NULL AND {brand_col} != ''
        ORDER BY {brand_col}
    """)
    brands = cursor.fetchall()
    brand_options = {"All Brands": None}
    brand_options.update({b['brand_name']: b['brand_name'] for b in brands if b['brand_name']})
    selected_brand = st.sidebar.selectbox("Select Brand", list(brand_options.keys()))
    brand_id = brand_options[selected_brand]

# Package Size filter - NEW
st.sidebar.subheader("📦 Package Size")
if package_size_col:
    cursor.execute(f"""
        SELECT DISTINCT {package_size_col} as pkg_size
        FROM sales_invoice_full_looker_view
        WHERE legal_entity_id = 43 AND {package_size_col} IS NOT NULL AND {package_size_col} != ''
        ORDER BY {package_size_col}
    """)
    pkg_sizes = cursor.fetchall()
    pkg_options = {"All Sizes": None}
    pkg_options.update({str(p['pkg_size']): p['pkg_size'] for p in pkg_sizes if p['pkg_size']})
    selected_pkg = st.sidebar.selectbox("Select Package Size", list(pkg_options.keys()))
    selected_pkg_size = pkg_options[selected_pkg]
else:
    selected_pkg_size = None
    st.sidebar.info("Package size not available in invoice view")

# GP Filter
st.sidebar.subheader("📊 GP Filter")
gp_filter = st.sidebar.selectbox("Filter by GP%", [
    "All",
    "Valid GP (< 100%)",
    "GP 100% (Missing Cost)",
    "Low GP (< 20%)",
    "Medium GP (20-30%)",
    "High GP (> 30%)"
])

# Product filter
product_col = 'product_pn' if 'product_pn' in columns else 'product_name' if 'product_name' in columns else None
product_pt_code = None

if product_col:
    product_query = f"""
        SELECT DISTINCT {product_col} as product_name, pt_code 
        FROM sales_invoice_full_looker_view
        WHERE legal_entity_id = 43 AND {product_col} IS NOT NULL
    """
    if brand_id and brand_col:
        product_query += f" AND {brand_col} = '{brand_id}'"
    if selected_pkg_size and package_size_col:
        product_query += f" AND {package_size_col} = '{selected_pkg_size}'"
    product_query += f" ORDER BY {product_col} LIMIT 200"
    
    cursor.execute(product_query)
    products_list = cursor.fetchall()
    product_options = {"All Products": None}
    product_options.update({f"{p['product_name']}": p['pt_code'] for p in products_list if p['product_name']})
    selected_product = st.sidebar.selectbox("Select Product", list(product_options.keys()))
    product_pt_code = product_options[selected_product]

cursor.close()
conn.close()

# Build WHERE clause
def build_where_clause():
    conditions = ["legal_entity_id = 43"]
    if days_back < 9999:
        conditions.append(f"inv_date >= DATE_SUB(CURDATE(), INTERVAL {days_back} DAY)")
    if brand_id and brand_col:
        conditions.append(f"{brand_col} = '{brand_id}'")
    if selected_pkg_size and package_size_col:
        conditions.append(f"{package_size_col} = '{selected_pkg_size}'")
    if product_pt_code:
        conditions.append(f"pt_code = '{product_pt_code}'")
    
    # GP Filter conditions
    if gp_filter == "Valid GP (< 100%)":
        conditions.append("gross_profit_percent < 100")
    elif gp_filter == "GP 100% (Missing Cost)":
        conditions.append("gross_profit_percent >= 100")
    elif gp_filter == "Low GP (< 20%)":
        conditions.append("gross_profit_percent < 20 AND gross_profit_percent >= 0")
    elif gp_filter == "Medium GP (20-30%)":
        conditions.append("gross_profit_percent >= 20 AND gross_profit_percent < 30")
    elif gp_filter == "High GP (> 30%)":
        conditions.append("gross_profit_percent >= 30 AND gross_profit_percent < 100")
    
    return " AND ".join(conditions)

# ============== TABS ==============
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 GP Overview", "⚠️ Data Quality", "💰 Cost Analysis", "🔄 Cost Simulation", "🎯 Recommendations"])

# ============== TAB 1: GP OVERVIEW ==============
with tab1:
    st.header("Gross Profit Overview")
    
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    where_clause = build_where_clause()
    
    # Build dynamic SELECT - include package_size
    select_cols = ['pt_code', 'inv_date']
    optional_cols = [
        'product_pn', 'product_name', 'brand_name', 'brand',
        'package_size', 'pkg_size',  # Added package size
        'inv_unit_price', 'selling_unit_price', 
        'average_landed_cost_usd', 'total_cogs_per_unit_usd', 
        'logistics_cost_per_unit_usd', 'gross_profit_percent',
        'adjusted_gross_profit_percent', 'invoiced_gross_profit_usd',
        'calculated_invoiced_amount_usd', 'invoiced_quantity'
    ]
    
    for col in optional_cols:
        if col in columns:
            select_cols.append(col)
    
    select_str = ", ".join(select_cols)
    
    cursor.execute(f"""
        SELECT {select_str}
        FROM sales_invoice_full_looker_view
        WHERE {where_clause}
        ORDER BY inv_date DESC
    """)
    sales_data = cursor.fetchall()
    
    if sales_data:
        df_sales = pd.DataFrame(sales_data)
        df_sales = convert_decimals(df_sales)
        df_sales['inv_date'] = pd.to_datetime(df_sales['inv_date'])
        
        prod_col = 'product_pn' if 'product_pn' in df_sales.columns else 'product_name' if 'product_name' in df_sales.columns else 'pt_code'
        brand_display_col = 'brand_name' if 'brand_name' in df_sales.columns else 'brand' if 'brand' in df_sales.columns else None
        pkg_display_col = 'package_size' if 'package_size' in df_sales.columns else 'pkg_size' if 'pkg_size' in df_sales.columns else None
        
        # ========= DATA QUALITY WARNING =========
        if 'gross_profit_percent' in df_sales.columns:
            gp_100_count = len(df_sales[df_sales['gross_profit_percent'] >= 100])
            total_count = len(df_sales)
            gp_100_pct = gp_100_count / total_count * 100 if total_count > 0 else 0
            
            if gp_100_pct > 10:
                st.warning(f"""
                    ⚠️ **Data Quality Alert**: {gp_100_count:,} transactions ({gp_100_pct:.1f}%) have GP = 100%
                    
                    This means **Cost = $0** for these items. Possible reasons:
                    - No BOM (Bill of Materials) defined
                    - Missing Costbook prices  
                    - average_landed_cost_usd = 0
                    
                    👉 Use "GP Filter" in sidebar to filter these out, or check "Data Quality" tab
                """)
        
        # KPI Metrics - EXCLUDE 100% GP for accurate metrics
        df_valid = df_sales[df_sales['gross_profit_percent'] < 100] if 'gross_profit_percent' in df_sales.columns else df_sales
        
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            if 'gross_profit_percent' in df_valid.columns and len(df_valid) > 0:
                avg_gp = df_valid['gross_profit_percent'].mean()
                st.metric("📊 Avg GP% (Valid)", f"{avg_gp:.2f}%")
            else:
                st.metric("📊 Avg GP%", "N/A")
        with col2:
            if 'invoiced_gross_profit_usd' in df_valid.columns:
                total_gp_usd = df_valid['invoiced_gross_profit_usd'].sum()
                st.metric("💵 Total GP (USD)", f"${total_gp_usd:,.2f}")
            else:
                st.metric("💵 Total GP (USD)", "N/A")
        with col3:
            if 'calculated_invoiced_amount_usd' in df_valid.columns:
                total_revenue = df_valid['calculated_invoiced_amount_usd'].sum()
                st.metric("📈 Revenue (USD)", f"${total_revenue:,.2f}")
            else:
                st.metric("📈 Revenue (USD)", "N/A")
        with col4:
            st.metric("📋 Total Transactions", f"{len(df_sales):,}")
        with col5:
            st.metric("✅ Valid (GP<100%)", f"{len(df_valid):,}")
        
        st.markdown("---")
        
        # Use df_valid for charts (exclude 100% GP)
        df_chart = df_valid if len(df_valid) > 0 else df_sales
        
        # Charts Row 1
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📈 GP% Trend Over Time")
            if 'gross_profit_percent' in df_chart.columns and len(df_chart) > 0:
                agg_dict = {'gross_profit_percent': 'mean'}
                if 'invoiced_gross_profit_usd' in df_chart.columns:
                    agg_dict['invoiced_gross_profit_usd'] = 'sum'
                if 'calculated_invoiced_amount_usd' in df_chart.columns:
                    agg_dict['calculated_invoiced_amount_usd'] = 'sum'
                
                df_monthly = df_chart.groupby(df_chart['inv_date'].dt.to_period('M')).agg(agg_dict).reset_index()
                df_monthly['inv_date'] = df_monthly['inv_date'].astype(str)
                
                fig_trend = go.Figure()
                fig_trend.add_trace(go.Scatter(
                    x=df_monthly['inv_date'], 
                    y=df_monthly['gross_profit_percent'],
                    mode='lines+markers',
                    name='GP%',
                    line=dict(color='#2E86AB', width=3),
                    marker=dict(size=8)
                ))
                fig_trend.add_hline(y=25, line_dash="dash", line_color="green", annotation_text="Target 25%")
                fig_trend.update_layout(
                    xaxis_title="Month",
                    yaxis_title="GP%",
                    hovermode='x unified',
                    height=350
                )
                st.plotly_chart(fig_trend, use_container_width=True)
            else:
                st.info("No valid GP data")
        
        with col2:
            st.subheader("💰 Revenue vs GP by Month")
            if 'calculated_invoiced_amount_usd' in df_chart.columns and 'invoiced_gross_profit_usd' in df_chart.columns and len(df_chart) > 0:
                fig_revenue = go.Figure()
                fig_revenue.add_trace(go.Bar(
                    x=df_monthly['inv_date'],
                    y=df_monthly['calculated_invoiced_amount_usd'],
                    name='Revenue (USD)',
                    marker_color='#28A745'
                ))
                fig_revenue.add_trace(go.Bar(
                    x=df_monthly['inv_date'],
                    y=df_monthly['invoiced_gross_profit_usd'],
                    name='GP (USD)',
                    marker_color='#FFC107'
                ))
                fig_revenue.update_layout(
                    barmode='group',
                    xaxis_title="Month",
                    yaxis_title="USD",
                    height=350
                )
                st.plotly_chart(fig_revenue, use_container_width=True)
            else:
                st.info("Revenue data not available")
        
        # Charts Row 2 - ADD PACKAGE SIZE ANALYSIS
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 GP% Distribution (Valid Only)")
            if 'gross_profit_percent' in df_chart.columns and len(df_chart) > 0:
                fig_dist = px.histogram(
                    df_chart, 
                    x='gross_profit_percent', 
                    nbins=30,
                    color_discrete_sequence=['#2E86AB']
                )
                fig_dist.update_layout(
                    xaxis_title="GP%",
                    yaxis_title="Count",
                    height=350
                )
                st.plotly_chart(fig_dist, use_container_width=True)
            else:
                st.info("No valid GP data")
        
        with col2:
            # Package Size Analysis - NEW
            if pkg_display_col and pkg_display_col in df_chart.columns:
                st.subheader("📦 GP% by Package Size")
                df_pkg = df_chart.groupby(pkg_display_col).agg({
                    'gross_profit_percent': 'mean',
                    'calculated_invoiced_amount_usd': 'sum' if 'calculated_invoiced_amount_usd' in df_chart.columns else 'count'
                }).reset_index()
                df_pkg = df_pkg.sort_values('gross_profit_percent', ascending=False)
                
                fig_pkg = px.bar(
                    df_pkg.head(15),
                    x=pkg_display_col,
                    y='gross_profit_percent',
                    color='gross_profit_percent',
                    color_continuous_scale='RdYlGn',
                    title='Average GP% by Package Size'
                )
                fig_pkg.update_layout(xaxis_tickangle=-45, height=350)
                st.plotly_chart(fig_pkg, use_container_width=True)
            else:
                st.subheader("🏆 Top 10 Products by GP")
                if 'invoiced_gross_profit_usd' in df_chart.columns and len(df_chart) > 0:
                    df_top = df_chart.groupby(prod_col).agg({
                        'invoiced_gross_profit_usd': 'sum'
                    }).reset_index().nlargest(10, 'invoiced_gross_profit_usd')
                    
                    fig_top = px.bar(
                        df_top,
                        x='invoiced_gross_profit_usd',
                        y=prod_col,
                        orientation='h',
                        color='invoiced_gross_profit_usd',
                        color_continuous_scale='Greens'
                    )
                    fig_top.update_layout(
                        xaxis_title="GP (USD)",
                        yaxis_title="",
                        height=350,
                        showlegend=False
                    )
                    st.plotly_chart(fig_top, use_container_width=True)
        
        # Charts Row 3 - Top Products + Brand Analysis
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🏆 Top 10 Products by GP")
            if 'invoiced_gross_profit_usd' in df_chart.columns and len(df_chart) > 0:
                df_top = df_chart.groupby(prod_col).agg({
                    'invoiced_gross_profit_usd': 'sum'
                }).reset_index().nlargest(10, 'invoiced_gross_profit_usd')
                
                fig_top = px.bar(
                    df_top,
                    x='invoiced_gross_profit_usd',
                    y=prod_col,
                    orientation='h',
                    color='invoiced_gross_profit_usd',
                    color_continuous_scale='Greens'
                )
                fig_top.update_layout(
                    xaxis_title="GP (USD)",
                    yaxis_title="",
                    height=350,
                    showlegend=False
                )
                st.plotly_chart(fig_top, use_container_width=True)
        
        with col2:
            if brand_display_col and brand_display_col in df_chart.columns:
                st.subheader("🏷️ GP% by Brand")
                df_brand = df_chart.groupby(brand_display_col).agg({
                    'gross_profit_percent': 'mean'
                }).reset_index().sort_values('gross_profit_percent', ascending=False)
                
                fig_brand_bar = px.bar(
                    df_brand.head(10),
                    x=brand_display_col,
                    y='gross_profit_percent',
                    color='gross_profit_percent',
                    color_continuous_scale='RdYlGn'
                )
                fig_brand_bar.update_layout(xaxis_tickangle=-45, height=350)
                st.plotly_chart(fig_brand_bar, use_container_width=True)
        
        # GP Table - Include Package Size
        st.markdown("---")
        st.subheader("🔍 GP Analysis by Product")
        
        # Build groupby columns
        groupby_cols = [prod_col, 'pt_code']
        if pkg_display_col and pkg_display_col in df_sales.columns:
            groupby_cols.append(pkg_display_col)
        
        agg_dict_prod = {}
        if 'gross_profit_percent' in df_sales.columns:
            agg_dict_prod['gross_profit_percent'] = 'mean'
        if 'adjusted_gross_profit_percent' in df_sales.columns:
            agg_dict_prod['adjusted_gross_profit_percent'] = 'mean'
        if 'invoiced_gross_profit_usd' in df_sales.columns:
            agg_dict_prod['invoiced_gross_profit_usd'] = 'sum'
        if 'calculated_invoiced_amount_usd' in df_sales.columns:
            agg_dict_prod['calculated_invoiced_amount_usd'] = 'sum'
        if 'invoiced_quantity' in df_sales.columns:
            agg_dict_prod['invoiced_quantity'] = 'sum'
        if 'average_landed_cost_usd' in df_sales.columns:
            agg_dict_prod['average_landed_cost_usd'] = 'mean'
        
        if agg_dict_prod:
            df_product_gp = df_sales.groupby(groupby_cols).agg(agg_dict_prod).reset_index()
            
            if 'invoiced_gross_profit_usd' in df_product_gp.columns:
                df_product_gp = df_product_gp.sort_values('invoiced_gross_profit_usd', ascending=False)
            
            # Add cost status column
            if 'gross_profit_percent' in df_product_gp.columns:
                df_product_gp['cost_status'] = df_product_gp['gross_profit_percent'].apply(
                    lambda x: '⚠️ Missing Cost' if x >= 100 else '✅ Valid'
                )
            
            def color_gp(val):
                if pd.isna(val):
                    return ''
                if val >= 100:
                    return 'background-color: #ff6b6b; color: white'
                elif val >= 30:
                    return 'background-color: #28a745; color: white'
                elif val >= 20:
                    return 'background-color: #ffc107; color: black'
                elif val >= 10:
                    return 'background-color: #fd7e14; color: white'
                else:
                    return 'background-color: #dc3545; color: white'
            
            format_dict = {}
            if 'gross_profit_percent' in df_product_gp.columns:
                format_dict['gross_profit_percent'] = '{:.2f}%'
            if 'adjusted_gross_profit_percent' in df_product_gp.columns:
                format_dict['adjusted_gross_profit_percent'] = '{:.2f}%'
            if 'invoiced_gross_profit_usd' in df_product_gp.columns:
                format_dict['invoiced_gross_profit_usd'] = '${:,.2f}'
            if 'calculated_invoiced_amount_usd' in df_product_gp.columns:
                format_dict['calculated_invoiced_amount_usd'] = '${:,.2f}'
            if 'invoiced_quantity' in df_product_gp.columns:
                format_dict['invoiced_quantity'] = '{:,.0f}'
            if 'average_landed_cost_usd' in df_product_gp.columns:
                format_dict['average_landed_cost_usd'] = '${:,.4f}'
            
            styled_df = df_product_gp.style.format(format_dict)
            if 'gross_profit_percent' in df_product_gp.columns:
                styled_df = styled_df.applymap(color_gp, subset=['gross_profit_percent'])
            
            st.dataframe(styled_df, use_container_width=True, height=400)
        
        # Insights
        st.markdown("---")
        st.subheader("💡 Key Insights")
        
        if 'gross_profit_percent' in df_sales.columns and 'invoiced_gross_profit_usd' in df_sales.columns:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.markdown("**🔴 Missing Cost (100%)**")
                missing_cost = df_product_gp[df_product_gp['gross_profit_percent'] >= 100]
                st.write(f"Count: {len(missing_cost)}")
                st.write(f"Revenue: ${missing_cost['calculated_invoiced_amount_usd'].sum():,.2f}" if 'calculated_invoiced_amount_usd' in missing_cost.columns else "N/A")
            
            with col2:
                st.markdown("**🟢 High GP (>30%)**")
                high_gp = df_product_gp[(df_product_gp['gross_profit_percent'] >= 30) & (df_product_gp['gross_profit_percent'] < 100)]
                st.write(f"Count: {len(high_gp)}")
                st.write(f"GP: ${high_gp['invoiced_gross_profit_usd'].sum():,.2f}")
            
            with col3:
                st.markdown("**🟡 Medium GP (20-30%)**")
                med_gp = df_product_gp[(df_product_gp['gross_profit_percent'] >= 20) & (df_product_gp['gross_profit_percent'] < 30)]
                st.write(f"Count: {len(med_gp)}")
                st.write(f"GP: ${med_gp['invoiced_gross_profit_usd'].sum():,.2f}")
            
            with col4:
                st.markdown("**🔴 Low GP (<20%)**")
                low_gp = df_product_gp[(df_product_gp['gross_profit_percent'] < 20) & (df_product_gp['gross_profit_percent'] >= 0)]
                st.write(f"Count: {len(low_gp)}")
                st.write(f"GP: ${low_gp['invoiced_gross_profit_usd'].sum():,.2f}")
    
    else:
        st.warning("No sales data found for selected filters")
    
    cursor.close()
    conn.close()

# ============== TAB 2: DATA QUALITY ==============
with tab2:
    st.header("⚠️ Data Quality Analysis")
    
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Build SELECT with package_size if available
    select_pkg = f", {package_size_col} as pkg_size" if package_size_col else ""
    group_pkg = f", {package_size_col}" if package_size_col else ""
    
    # Get products with GP = 100%
    cursor.execute(f"""
        SELECT 
            pt_code,
            product_pn,
            brand
            {select_pkg},
            COUNT(*) as transaction_count,
            SUM(calculated_invoiced_amount_usd) as total_revenue,
            AVG(gross_profit_percent) as avg_gp,
            AVG(average_landed_cost_usd) as avg_landed_cost,
            AVG(total_cogs_per_unit_usd) as avg_cogs
        FROM sales_invoice_full_looker_view
        WHERE legal_entity_id = 43
        AND gross_profit_percent >= 100
        GROUP BY pt_code, product_pn, brand {group_pkg}
        ORDER BY total_revenue DESC
        LIMIT 100
    """)
    missing_cost_data = cursor.fetchall()
    
    if missing_cost_data:
        df_missing = pd.DataFrame(missing_cost_data)
        df_missing = convert_decimals(df_missing)
        
        # Summary
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("🔴 Products with GP=100%", f"{len(df_missing):,}")
        with col2:
            total_revenue_missing = df_missing['total_revenue'].sum()
            st.metric("💰 Revenue Affected", f"${total_revenue_missing:,.2f}")
        with col3:
            total_trans = df_missing['transaction_count'].sum()
            st.metric("📋 Transactions Affected", f"{total_trans:,}")
        
        st.markdown("---")
        
        # Check why cost is missing
        st.subheader("🔍 Root Cause Analysis")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Check BOM existence
            pt_codes = df_missing['pt_code'].tolist()[:50]
            if pt_codes:
                pt_code_list = "','".join(pt_codes)
                cursor.execute(f"""
                    SELECT p.pt_code, 
                           CASE WHEN bh.id IS NOT NULL THEN 'Has BOM' ELSE 'No BOM' END as bom_status
                    FROM products p
                    LEFT JOIN bom_headers bh ON p.id = bh.product_id AND bh.status = 'ACTIVE' AND bh.delete_flag = 0
                    WHERE p.pt_code IN ('{pt_code_list}')
                """)
                bom_check = cursor.fetchall()
                
                if bom_check:
                    df_bom = pd.DataFrame(bom_check)
                    bom_summary = df_bom['bom_status'].value_counts()
                    
                    fig_bom = px.pie(
                        values=bom_summary.values,
                        names=bom_summary.index,
                        title='BOM Status for GP=100% Products',
                        color_discrete_map={'Has BOM': '#28a745', 'No BOM': '#dc3545'}
                    )
                    st.plotly_chart(fig_bom, use_container_width=True)
        
        with col2:
            # Check by Package Size if available
            if 'pkg_size' in df_missing.columns:
                st.subheader("📦 Missing Cost by Package Size")
                pkg_summary = df_missing.groupby('pkg_size').agg({
                    'total_revenue': 'sum',
                    'transaction_count': 'sum'
                }).reset_index().sort_values('total_revenue', ascending=False)
                
                fig_pkg = px.bar(
                    pkg_summary.head(10),
                    x='pkg_size',
                    y='total_revenue',
                    title='Revenue Affected by Package Size',
                    color='total_revenue',
                    color_continuous_scale='Reds'
                )
                fig_pkg.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_pkg, use_container_width=True)
            else:
                st.markdown("**💵 Cost Data Status**")
                avg_landed = df_missing['avg_landed_cost'].mean()
                avg_cogs = df_missing['avg_cogs'].mean()
                
                st.write(f"- Average Landed Cost: ${avg_landed:.4f}" if avg_landed else "- Average Landed Cost: $0.00")
                st.write(f"- Average COGS: ${avg_cogs:.4f}" if avg_cogs else "- Average COGS: $0.00")
                
                if avg_landed == 0 or pd.isna(avg_landed):
                    st.error("❌ Landed Cost = 0 → No Costbook prices or BOM not costed")
        
        # Products needing attention
        st.markdown("---")
        st.subheader("📋 Products Needing Cost Setup (Top 100 by Revenue)")
        
        format_dict = {
            'total_revenue': '${:,.2f}',
            'avg_gp': '{:.1f}%',
            'avg_landed_cost': '${:.4f}',
            'avg_cogs': '${:.4f}',
            'transaction_count': '{:,}'
        }
        
        st.dataframe(
            df_missing.style.format(format_dict),
            use_container_width=True,
            height=400
        )
        
        # Action items
        st.markdown("---")
        st.subheader("✅ Action Items")
        st.markdown("""
        1. **Create BOM** for products without Bill of Materials
        2. **Update Costbook** with current material prices
        3. **Review logistics costs** - ensure freight/duty allocated
        4. **Re-run cost calculation** after updates
        """)
    else:
        st.success("✅ No products with GP=100% found!")
    
    cursor.close()
    conn.close()

# ============== TAB 3: COST ANALYSIS ==============
with tab3:
    st.header("BOM Cost Analysis")
    
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Include package_size in product selection
    cursor.execute("""
        SELECT DISTINCT p.name as product_name, p.pt_code, p.package_size
        FROM bom_headers bh
        JOIN products p ON bh.product_id = p.id
        WHERE bh.status = 'ACTIVE' AND bh.delete_flag = 0
        ORDER BY p.name
    """)
    products = cursor.fetchall()
    
    if products:
        product_options = {f"{p['product_name']} ({p['pt_code']}) - {p['package_size'] or 'N/A'}": p['pt_code'] for p in products}
        selected = st.selectbox("Select Product", list(product_options.keys()))
        selected_pt_code = product_options[selected]
        
        cursor.execute("""
            WITH material_max_price AS (
                SELECT pt_code, 
                       MAX(standard_unit_price_usd) as max_price,
                       MAX(validity_status) as status
                FROM costbook_full_view
                GROUP BY pt_code
            )
            SELECT 
                p.name as finished_product,
                p.pt_code as product_code,
                p.package_size,
                m.name as material_name,
                m.pt_code as material_code,
                bd.quantity,
                bd.scrap_rate,
                mp.max_price as unit_price,
                mp.status as price_status,
                bd.quantity * (1 + COALESCE(bd.scrap_rate, 0)/100) * COALESCE(mp.max_price, 0) as material_cost
            FROM bom_headers bh
            JOIN products p ON bh.product_id = p.id
            JOIN bom_details bd ON bh.id = bd.bom_header_id
            LEFT JOIN products m ON bd.material_id = m.id
            LEFT JOIN material_max_price mp ON m.pt_code = mp.pt_code
            WHERE bh.status = 'ACTIVE' 
            AND bh.delete_flag = 0
            AND p.pt_code = %s
        """, (selected_pt_code,))
        bom_data = cursor.fetchall()
        
        if bom_data:
            df_bom = pd.DataFrame(bom_data)
            df_bom = convert_decimals(df_bom)
            
            total_material_cost = df_bom['material_cost'].sum()
            package_size = df_bom['package_size'].iloc[0] if 'package_size' in df_bom.columns else 'N/A'
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("🏭 Total BOM Cost", f"${total_material_cost:.4f}")
            with col2:
                st.metric("📦 Package Size", str(package_size))
            with col3:
                cursor.execute("""
                    SELECT AVG(average_landed_cost_usd) as avg_landed,
                           AVG(logistics_cost_per_unit_usd) as avg_logistics
                    FROM sales_invoice_full_looker_view
                    WHERE pt_code = %s AND legal_entity_id = 43
                """, (selected_pt_code,))
                cost_data = cursor.fetchone()
                if cost_data and cost_data['avg_landed']:
                    st.metric("📦 Avg Landed Cost (Invoice)", f"${float(cost_data['avg_landed']):.4f}")
                else:
                    st.metric("📦 Avg Landed Cost", "N/A (GP=100%)")
            with col4:
                st.metric("🧩 Materials Count", len(df_bom))
            
            st.markdown("---")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("📊 Cost Breakdown")
                df_chart = df_bom[df_bom['material_cost'] > 0].nlargest(10, 'material_cost')
                if not df_chart.empty:
                    fig_pie = px.pie(df_chart, values='material_cost', names='material_name')
                    fig_pie.update_layout(height=400)
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.warning("⚠️ All materials have $0 cost - check Costbook!")
            
            with col2:
                st.subheader("📈 Material Cost Comparison")
                if not df_chart.empty:
                    fig_bar = px.bar(df_chart, x='material_name', y='material_cost', color='material_cost')
                    fig_bar.update_layout(xaxis_tickangle=-45, height=400)
                    st.plotly_chart(fig_bar, use_container_width=True)
            
            # BOM Table
            st.subheader("📋 BOM Details")
            st.dataframe(
                df_bom[['material_name', 'material_code', 'quantity', 'scrap_rate', 'unit_price', 'price_status', 'material_cost']].style.format({
                    'quantity': '{:.4f}',
                    'scrap_rate': '{:.2f}%',
                    'unit_price': '${:.4f}',
                    'material_cost': '${:.4f}'
                }),
                use_container_width=True
            )
            
            # Warnings
            missing = df_bom[df_bom['unit_price'].isna() | (df_bom['unit_price'] == 0)]
            if not missing.empty:
                st.error(f"❌ {len(missing)} materials missing Costbook prices!")
                st.dataframe(missing[['material_name', 'material_code']])
        else:
            st.info("No BOM found")
    else:
        st.info("No products with BOM")
    
    cursor.close()
    conn.close()

# ============== TAB 4: COST SIMULATION ==============
with tab4:
    st.header("Cost Impact Simulation")
    
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT DISTINCT p.name as product_name, p.pt_code, p.package_size
        FROM bom_headers bh
        JOIN products p ON bh.product_id = p.id
        WHERE bh.status = 'ACTIVE' AND bh.delete_flag = 0
        ORDER BY p.name
    """)
    products = cursor.fetchall()
    
    if products:
        product_options = {f"{p['product_name']} ({p['pt_code']}) - {p['package_size'] or 'N/A'}": p['pt_code'] for p in products}
        selected = st.selectbox("Select Product for Simulation", list(product_options.keys()), key="sim_product")
        selected_pt_code = product_options[selected]
        
        col1, col2 = st.columns(2)
        with col1:
            material_adj = st.slider("Material Cost Change (%)", -50, 100, 0)
        with col2:
            logistics_adj = st.slider("Logistics Cost Change (%)", -50, 100, 0)
        
        cursor.execute("""
            WITH material_max_price AS (
                SELECT pt_code, MAX(standard_unit_price_usd) as max_price
                FROM costbook_full_view
                GROUP BY pt_code
            )
            SELECT SUM(bd.quantity * (1 + COALESCE(bd.scrap_rate, 0)/100) * COALESCE(mp.max_price, 0)) as total_material_cost
            FROM bom_headers bh
            JOIN products p ON bh.product_id = p.id
            JOIN bom_details bd ON bh.id = bd.bom_header_id
            LEFT JOIN products m ON bd.material_id = m.id
            LEFT JOIN material_max_price mp ON m.pt_code = mp.pt_code
            WHERE bh.status = 'ACTIVE' AND bh.delete_flag = 0 AND p.pt_code = %s
        """, (selected_pt_code,))
        material_result = cursor.fetchone()
        
        cursor.execute("""
            SELECT AVG(selling_unit_price) as avg_price, AVG(logistics_cost_per_unit_usd) as avg_logistics
            FROM sales_invoice_full_looker_view
            WHERE pt_code = %s AND legal_entity_id = 43
        """, (selected_pt_code,))
        sales_result = cursor.fetchone()
        
        base_material = float(material_result['total_material_cost'] or 0) if material_result else 0
        base_logistics = float(sales_result['avg_logistics'] or 0) if sales_result and sales_result['avg_logistics'] else 0
        selling_price = float(sales_result['avg_price'] or 0) if sales_result and sales_result['avg_price'] else 0
        
        adj_material = base_material * (1 + material_adj/100)
        adj_logistics = base_logistics * (1 + logistics_adj/100)
        base_total = base_material + base_logistics
        adj_total = adj_material + adj_logistics
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.subheader("📊 Base")
            st.metric("Material", f"${base_material:.4f}")
            st.metric("Logistics", f"${base_logistics:.4f}")
            st.metric("Total", f"${base_total:.4f}")
        with col2:
            st.subheader("🔄 Adjusted")
            st.metric("Material", f"${adj_material:.4f}", f"${adj_material - base_material:+.4f}")
            st.metric("Logistics", f"${adj_logistics:.4f}", f"${adj_logistics - base_logistics:+.4f}")
            st.metric("Total", f"${adj_total:.4f}", f"${adj_total - base_total:+.4f}")
        with col3:
            st.subheader("📈 GP Impact")
            if selling_price > 0:
                base_gp = (selling_price - base_total) / selling_price * 100
                adj_gp = (selling_price - adj_total) / selling_price * 100
                st.metric("Base GP%", f"{base_gp:.2f}%")
                st.metric("New GP%", f"{adj_gp:.2f}%", f"{adj_gp - base_gp:+.2f}%")
            else:
                st.info("No sales data")
    
    cursor.close()
    conn.close()

# ============== TAB 5: RECOMMENDATIONS ==============
with tab5:
    st.header("Pricing Recommendations")
    
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    target_gp = st.slider("Target GP%", 10, 40, 25)
    
    cursor.execute("""
        WITH material_max_price AS (
            SELECT pt_code, MAX(standard_unit_price_usd) as max_price
            FROM costbook_full_view
            GROUP BY pt_code
        ),
        product_costs AS (
            SELECT p.name as product_name, p.pt_code, p.package_size,
                   SUM(bd.quantity * (1 + COALESCE(bd.scrap_rate, 0)/100) * COALESCE(mp.max_price, 0)) as bom_cost
            FROM bom_headers bh
            JOIN products p ON bh.product_id = p.id
            JOIN bom_details bd ON bh.id = bd.bom_header_id
            LEFT JOIN products m ON bd.material_id = m.id
            LEFT JOIN material_max_price mp ON m.pt_code = mp.pt_code
            WHERE bh.status = 'ACTIVE' AND bh.delete_flag = 0
            GROUP BY p.id, p.name, p.pt_code, p.package_size
        )
        SELECT pc.product_name, pc.pt_code, pc.package_size, pc.bom_cost,
               AVG(s.selling_unit_price) as current_price,
               AVG(s.gross_profit_percent) as current_gp,
               SUM(s.invoiced_gross_profit_usd) as total_gp
        FROM product_costs pc
        LEFT JOIN sales_invoice_full_looker_view s ON pc.pt_code = s.pt_code AND s.legal_entity_id = 43
        GROUP BY pc.product_name, pc.pt_code, pc.package_size, pc.bom_cost
        HAVING pc.bom_cost > 0 AND current_gp < 100
        ORDER BY total_gp DESC
        LIMIT 50
    """)
    recommendations = cursor.fetchall()
    
    if recommendations:
        df_rec = pd.DataFrame(recommendations)
        df_rec = convert_decimals(df_rec)
        
        df_rec['target_price'] = df_rec['bom_cost'] / (1 - target_gp/100)
        df_rec['price_gap'] = df_rec['target_price'] - df_rec['current_price'].fillna(0)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            needs_increase = len(df_rec[df_rec['price_gap'] > 0])
            st.metric("🔴 Need Price Increase", needs_increase)
        with col2:
            on_target = len(df_rec[(df_rec['current_gp'] >= target_gp - 5) & (df_rec['current_gp'] <= target_gp + 5)])
            st.metric("🟡 Near Target", on_target)
        with col3:
            above = len(df_rec[df_rec['current_gp'] > target_gp])
            st.metric("🟢 Above Target", above)
        
        st.dataframe(
            df_rec[['product_name', 'pt_code', 'package_size', 'bom_cost', 'current_price', 'current_gp', 'target_price', 'price_gap']].style.format({
                'bom_cost': '${:.2f}',
                'current_price': '${:.2f}',
                'current_gp': '{:.1f}%',
                'target_price': '${:.2f}',
                'price_gap': '${:+.2f}'
            }),
            use_container_width=True
        )
    
    cursor.close()
    conn.close()
