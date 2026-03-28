import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings('ignore')

st.set_page_config(page_title="GP Analysis Dashboard - DEMO", page_icon="📊", layout="wide")

# ============================================
# DEMO DATA GENERATOR (Simulated Data)
# ============================================
@st.cache_data
def generate_demo_data():
    """Generate realistic demo data for GP Analysis"""
    np.random.seed(42)
    
    # Product categories
    brands = ['Premium Tape A', 'Standard Tape B', 'Economy Tape C', 'Industrial Tape D', 'Specialty Tape E']
    pt_codes = ['PT001', 'PT002', 'PT003', 'PT004', 'PT005', 'PT006', 'PT007', 'PT008']
    package_sizes = ['Small', 'Medium', 'Large', 'Bulk']
    
    n_products = 150
    
    data = {
        'product_id': range(1, n_products + 1),
        'product_name': [f"Product {i:03d} - {np.random.choice(['Adhesive', 'Packaging', 'Sealing', 'Mounting', 'Masking'])} Tape" for i in range(1, n_products + 1)],
        'pt_code': np.random.choice(pt_codes, n_products),
        'brand_name': np.random.choice(brands, n_products),
        'package_size': np.random.choice(package_sizes, n_products),
        'total_qty': np.random.randint(100, 50000, n_products),
    }
    
    df = pd.DataFrame(data)
    
    # Generate realistic pricing
    base_prices = {'Small': 5, 'Medium': 12, 'Large': 25, 'Bulk': 45}
    brand_multiplier = {'Premium Tape A': 1.5, 'Standard Tape B': 1.0, 'Economy Tape C': 0.7, 'Industrial Tape D': 1.3, 'Specialty Tape E': 1.8}
    
    df['unit_price'] = df.apply(lambda x: base_prices[x['package_size']] * brand_multiplier[x['brand_name']] * np.random.uniform(0.8, 1.2), axis=1)
    df['total_revenue'] = df['unit_price'] * df['total_qty']
    
    # Generate costs with varying GP margins
    # Some products have negative GP, some critical, some excellent
    gp_targets = np.random.choice([-.05, .05, .12, .18, .25, .35], n_products, p=[0.05, 0.10, 0.15, 0.25, 0.30, 0.15])
    df['gp_target'] = gp_targets
    df['total_cogs'] = df['total_revenue'] * (1 - df['gp_target'])
    df['unit_cogs'] = df['total_cogs'] / df['total_qty']
    
    # BOM breakdown (Material ~85%, Freight ~15% of COGS)
    df['material_cost_per_unit'] = df['unit_cogs'] * 0.85
    df['freight_cost_per_unit'] = df['unit_cogs'] * 0.15
    df['total_unit_cost'] = df['material_cost_per_unit'] + df['freight_cost_per_unit']
    
    # Calculate GP
    df['gp_usd'] = df['total_revenue'] - df['total_cogs']
    df['gp_pct'] = (df['gp_usd'] / df['total_revenue']) * 100
    
    # System GP (with some variance to simulate real-world differences)
    df['system_gp'] = df['gp_usd'] * np.random.uniform(0.95, 1.05, n_products)
    
    return df

def classify_gp(gp_pct):
    """Classify GP percentage into status categories"""
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

def get_status_color(status):
    """Get color for each status"""
    colors = {
        "NEGATIVE": "#FF4136",
        "CRITICAL": "#FF851B", 
        "WARNING": "#FFDC00",
        "GOOD": "#2ECC40",
        "EXCELLENT": "#0074D9"
    }
    return colors.get(status, "#AAAAAA")

# ============================================
# MAIN APPLICATION
# ============================================
def main():
    # Header
    st.title("📊 GP Analysis Dashboard")
    st.markdown("### 🏭 Starboard/Vietape - Entity 43 | **DEMO VERSION**")
    
    # Demo notice
    st.warning("⚠️ **DEMO MODE**: Đang sử dụng dữ liệu giả lập để minh họa. Không phải dữ liệu thực của công ty.")
    
    # Load demo data
    with st.spinner("Đang tải dữ liệu demo..."):
        df = generate_demo_data()
    
    # Add status classification
    df['status'] = df['gp_pct'].apply(classify_gp)
    
    # ============================================
    # SIDEBAR CONTROLS
    # ============================================
    st.sidebar.header("🎛️ Điều chỉnh Chi phí")
    st.sidebar.markdown("---")
    
    material_increase = st.sidebar.slider(
        "📦 Tăng chi phí Nguyên vật liệu (%)", 
        min_value=0, max_value=50, value=10, step=1,
        help="Mô phỏng tăng giá nguyên vật liệu"
    )
    
    freight_increase = st.sidebar.slider(
        "🚛 Tăng chi phí Vận chuyển (%)", 
        min_value=0, max_value=50, value=15, step=1,
        help="Mô phỏng tăng giá vận chuyển"
    )
    
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Bộ lọc")
    
    # Filters
    selected_brands = st.sidebar.multiselect(
        "Thương hiệu",
        options=sorted(df['brand_name'].unique()),
        default=sorted(df['brand_name'].unique())
    )
    
    selected_pt_codes = st.sidebar.multiselect(
        "PT Code",
        options=sorted(df['pt_code'].unique()),
        default=sorted(df['pt_code'].unique())
    )
    
    min_revenue = st.sidebar.number_input(
        "Doanh thu tối thiểu ($)", 
        min_value=0, max_value=1000000, value=1000, step=500
    )
    
    # Apply filters
    df_filtered = df[
        (df['brand_name'].isin(selected_brands)) &
        (df['pt_code'].isin(selected_pt_codes)) &
        (df['total_revenue'] >= min_revenue)
    ].copy()
    
    st.sidebar.markdown("---")
    st.sidebar.info(f"📊 Đang hiển thị **{len(df_filtered)}** / {len(df)} sản phẩm")
    
    # ============================================
    # MAIN TABS
    # ============================================
    tab1, tab2, tab3 = st.tabs([
        "📈 Phân tích GP Hiện tại", 
        "⚠️ Tác động Tăng chi phí",
        "📋 Chi tiết Sản phẩm"
    ])
    
    # ============================================
    # TAB 1: CURRENT GP ANALYSIS
    # ============================================
    with tab1:
        st.header("📈 Phân tích GP Hiện tại (Trước khi tăng giá)")
        
        # Executive Summary
        st.subheader("📊 Tổng quan")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        total_revenue = df_filtered['total_revenue'].sum()
        total_cogs = df_filtered['total_cogs'].sum()
        total_gp = df_filtered['gp_usd'].sum()
        avg_gp_pct = (total_gp / total_revenue * 100) if total_revenue > 0 else 0
        total_qty = df_filtered['total_qty'].sum()
        
        with col1:
            st.metric("💰 Tổng Doanh thu", f"${total_revenue:,.0f}")
        with col2:
            st.metric("📦 Tổng COGS", f"${total_cogs:,.0f}")
        with col3:
            st.metric("📈 Tổng GP", f"${total_gp:,.0f}")
        with col4:
            st.metric("📊 GP% Trung bình", f"{avg_gp_pct:.1f}%")
        with col5:
            st.metric("📦 Tổng SL bán", f"{total_qty:,.0f}")
        
        st.markdown("---")
        
        # Charts Row 1
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🎯 Phân bố theo Trạng thái GP")
            status_summary = df_filtered.groupby('status').agg({
                'product_id': 'count',
                'total_revenue': 'sum',
                'gp_usd': 'sum'
            }).reset_index()
            status_summary.columns = ['Status', 'Products', 'Revenue', 'GP']
            
            # Order by severity
            status_order = ['NEGATIVE', 'CRITICAL', 'WARNING', 'GOOD', 'EXCELLENT']
            status_summary['Status'] = pd.Categorical(status_summary['Status'], categories=status_order, ordered=True)
            status_summary = status_summary.sort_values('Status')
            
            fig = px.pie(
                status_summary, 
                values='Products', 
                names='Status',
                color='Status',
                color_discrete_map={
                    "NEGATIVE": "#FF4136",
                    "CRITICAL": "#FF851B", 
                    "WARNING": "#FFDC00",
                    "GOOD": "#2ECC40",
                    "EXCELLENT": "#0074D9"
                },
                hole=0.4
            )
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("📊 Phân bố GP%")
            fig = px.histogram(
                df_filtered, 
                x='gp_pct', 
                nbins=30,
                color_discrete_sequence=['#0074D9']
            )
            fig.add_vline(x=0, line_dash="dash", line_color="red", annotation_text="Break-even")
            fig.add_vline(x=15, line_dash="dash", line_color="orange", annotation_text="Target 15%")
            fig.add_vline(x=avg_gp_pct, line_dash="solid", line_color="green", annotation_text=f"Avg: {avg_gp_pct:.1f}%")
            fig.update_layout(
                xaxis_title="GP %",
                yaxis_title="Số sản phẩm",
                height=350
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Charts Row 2
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🏷️ GP theo Thương hiệu")
            brand_summary = df_filtered.groupby('brand_name').agg({
                'total_revenue': 'sum',
                'gp_usd': 'sum'
            }).reset_index()
            brand_summary['gp_pct'] = (brand_summary['gp_usd'] / brand_summary['total_revenue'] * 100)
            brand_summary = brand_summary.sort_values('gp_pct', ascending=True)
            
            fig = px.bar(
                brand_summary,
                x='gp_pct',
                y='brand_name',
                orientation='h',
                color='gp_pct',
                color_continuous_scale='RdYlGn',
                range_color=[-10, 40]
            )
            fig.add_vline(x=15, line_dash="dash", line_color="black")
            fig.update_layout(
                xaxis_title="GP %",
                yaxis_title="",
                height=300,
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("📦 GP theo PT Code")
            pt_summary = df_filtered.groupby('pt_code').agg({
                'total_revenue': 'sum',
                'gp_usd': 'sum'
            }).reset_index()
            pt_summary['gp_pct'] = (pt_summary['gp_usd'] / pt_summary['total_revenue'] * 100)
            pt_summary = pt_summary.sort_values('gp_pct', ascending=True)
            
            fig = px.bar(
                pt_summary,
                x='gp_pct',
                y='pt_code',
                orientation='h',
                color='gp_pct',
                color_continuous_scale='RdYlGn',
                range_color=[-10, 40]
            )
            fig.add_vline(x=15, line_dash="dash", line_color="black")
            fig.update_layout(
                xaxis_title="GP %",
                yaxis_title="",
                height=300,
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Status Summary Table
        st.subheader("📋 Tổng hợp theo Trạng thái")
        status_table = df_filtered.groupby('status').agg({
            'product_id': 'count',
            'total_revenue': 'sum',
            'total_cogs': 'sum',
            'gp_usd': 'sum'
        }).reset_index()
        status_table.columns = ['Trạng thái', 'Số SP', 'Doanh thu', 'COGS', 'GP']
        status_table['GP%'] = (status_table['GP'] / status_table['Doanh thu'] * 100)
        status_table['% Doanh thu'] = (status_table['Doanh thu'] / total_revenue * 100)
        
        # Reorder
        status_table['Trạng thái'] = pd.Categorical(status_table['Trạng thái'], categories=status_order, ordered=True)
        status_table = status_table.sort_values('Trạng thái')
        
        st.dataframe(
            status_table.style.format({
                'Doanh thu': '${:,.0f}',
                'COGS': '${:,.0f}',
                'GP': '${:,.0f}',
                'GP%': '{:.1f}%',
                '% Doanh thu': '{:.1f}%'
            }),
            use_container_width=True,
            hide_index=True
        )
    
    # ============================================
    # TAB 2: COST IMPACT ANALYSIS
    # ============================================
    with tab2:
        st.header("⚠️ Phân tích Tác động Tăng chi phí")
        
        st.info(f"""
        📊 **Mô phỏng tăng chi phí:**
        - 📦 Nguyên vật liệu: **+{material_increase}%**
        - 🚛 Vận chuyển: **+{freight_increase}%**
        """)
        
        # Calculate impact
        df_impact = df_filtered.copy()
        
        df_impact['new_material_cost'] = df_impact['material_cost_per_unit'] * (1 + material_increase/100)
        df_impact['new_freight_cost'] = df_impact['freight_cost_per_unit'] * (1 + freight_increase/100)
        df_impact['new_unit_cost'] = df_impact['new_material_cost'] + df_impact['new_freight_cost']
        df_impact['new_cogs'] = df_impact['new_unit_cost'] * df_impact['total_qty']
        df_impact['new_gp_usd'] = df_impact['total_revenue'] - df_impact['new_cogs']
        df_impact['new_gp_pct'] = (df_impact['new_gp_usd'] / df_impact['total_revenue']) * 100
        df_impact['new_status'] = df_impact['new_gp_pct'].apply(classify_gp)
        df_impact['gp_pct_change'] = df_impact['new_gp_pct'] - df_impact['gp_pct']
        df_impact['gp_usd_change'] = df_impact['new_gp_usd'] - df_impact['gp_usd']
        
        # Impact Summary
        st.subheader("📊 So sánh Trước vs Sau")
        
        col1, col2, col3, col4 = st.columns(4)
        
        old_gp = df_filtered['gp_usd'].sum()
        new_gp = df_impact['new_gp_usd'].sum()
        old_gp_pct = avg_gp_pct
        new_gp_pct = (new_gp / total_revenue * 100) if total_revenue > 0 else 0
        gp_loss = new_gp - old_gp
        
        with col1:
            st.metric("📈 GP Trước", f"${old_gp:,.0f}")
        with col2:
            st.metric("📉 GP Sau", f"${new_gp:,.0f}", delta=f"${gp_loss:,.0f}")
        with col3:
            st.metric("📊 GP% Trước", f"{old_gp_pct:.1f}%")
        with col4:
            st.metric("📊 GP% Sau", f"{new_gp_pct:.1f}%", delta=f"{new_gp_pct - old_gp_pct:.1f}%")
        
        st.markdown("---")
        
        # Status Migration
        st.subheader("🔄 Thay đổi Trạng thái")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Status migration matrix
            migration = pd.crosstab(df_impact['status'], df_impact['new_status'])
            
            # Reorder
            for col in status_order:
                if col not in migration.columns:
                    migration[col] = 0
            for idx in status_order:
                if idx not in migration.index:
                    migration.loc[idx] = 0
            
            migration = migration.reindex(index=status_order, columns=status_order, fill_value=0)
            
            fig = px.imshow(
                migration,
                labels=dict(x="Trạng thái Sau", y="Trạng thái Trước", color="Số SP"),
                color_continuous_scale='Reds',
                text_auto=True
            )
            fig.update_layout(
                title="Ma trận Chuyển đổi Trạng thái",
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Count products by status change
            before_counts = df_filtered['status'].value_counts()
            after_counts = df_impact['new_status'].value_counts()
            
            comparison_df = pd.DataFrame({
                'Trước': before_counts,
                'Sau': after_counts
            }).fillna(0).astype(int)
            
            comparison_df = comparison_df.reindex(status_order).fillna(0).astype(int)
            comparison_df['Thay đổi'] = comparison_df['Sau'] - comparison_df['Trước']
            
            fig = go.Figure()
            fig.add_trace(go.Bar(name='Trước', x=comparison_df.index, y=comparison_df['Trước'], marker_color='lightblue'))
            fig.add_trace(go.Bar(name='Sau', x=comparison_df.index, y=comparison_df['Sau'], marker_color='coral'))
            fig.update_layout(
                barmode='group',
                title="Số SP theo Trạng thái",
                xaxis_title="Trạng thái",
                yaxis_title="Số sản phẩm",
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
        
        # Products turning negative
        st.subheader("🚨 Sản phẩm chuyển sang GP Âm")
        
        turning_negative = df_impact[(df_impact['gp_pct'] >= 0) & (df_impact['new_gp_pct'] < 0)]
        
        if len(turning_negative) > 0:
            st.error(f"⚠️ **{len(turning_negative)} sản phẩm** sẽ có GP âm sau khi tăng chi phí!")
            
            turning_neg_display = turning_negative[[
                'product_name', 'brand_name', 'total_revenue', 'gp_pct', 'new_gp_pct', 'gp_usd_change'
            ]].sort_values('gp_usd_change').head(20)
            
            turning_neg_display.columns = ['Sản phẩm', 'Thương hiệu', 'Doanh thu', 'GP% Trước', 'GP% Sau', 'Mất GP ($)']
            
            st.dataframe(
                turning_neg_display.style.format({
                    'Doanh thu': '${:,.0f}',
                    'GP% Trước': '{:.1f}%',
                    'GP% Sau': '{:.1f}%',
                    'Mất GP ($)': '${:,.0f}'
                }),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.success("✅ Không có sản phẩm nào chuyển sang GP âm!")
        
        st.markdown("---")
        
        # Top 20 most affected products
        st.subheader("📉 Top 20 Sản phẩm bị ảnh hưởng nhiều nhất")
        
        worst_affected = df_impact.nsmallest(20, 'gp_usd_change')[[
            'product_name', 'brand_name', 'pt_code', 'total_revenue', 
            'gp_pct', 'new_gp_pct', 'gp_usd_change', 'status', 'new_status'
        ]]
        worst_affected.columns = ['Sản phẩm', 'Thương hiệu', 'PT Code', 'Doanh thu', 
                                   'GP% Trước', 'GP% Sau', 'Mất GP ($)', 'Status Trước', 'Status Sau']
        
        st.dataframe(
            worst_affected.style.format({
                'Doanh thu': '${:,.0f}',
                'GP% Trước': '{:.1f}%',
                'GP% Sau': '{:.1f}%',
                'Mất GP ($)': '${:,.0f}'
            }),
            use_container_width=True,
            hide_index=True
        )
        
        st.markdown("---")
        
        # Pricing recommendation
        st.subheader("💡 Đề xuất Điều chỉnh Giá")
        
        # Calculate required price increase to maintain GP
        df_impact['required_price_increase'] = ((df_impact['new_cogs'] - df_impact['total_cogs']) / df_impact['total_revenue']) * 100
        
        # Target 15% GP
        df_impact['price_for_15pct_gp'] = df_impact['new_cogs'] / 0.85
        df_impact['price_increase_for_15pct'] = ((df_impact['price_for_15pct_gp'] - df_impact['total_revenue']) / df_impact['total_revenue']) * 100
        
        col1, col2 = st.columns(2)
        
        with col1:
            avg_price_increase_maintain = df_impact['required_price_increase'].mean()
            st.metric(
                "📊 Tăng giá TB để giữ GP% hiện tại",
                f"{avg_price_increase_maintain:.1f}%"
            )
        
        with col2:
            products_need_increase = len(df_impact[df_impact['new_gp_pct'] < 15])
            st.metric(
                "⚠️ SP cần tăng giá để đạt GP 15%",
                f"{products_need_increase} sản phẩm"
            )
    
    # ============================================
    # TAB 3: PRODUCT DETAILS
    # ============================================
    with tab3:
        st.header("📋 Chi tiết Sản phẩm")
        
        # Search and sort
        col1, col2 = st.columns([2, 1])
        
        with col1:
            search = st.text_input("🔍 Tìm kiếm sản phẩm", "")
        
        with col2:
            sort_by = st.selectbox("Sắp xếp theo", ['Doanh thu', 'GP%', 'GP $', 'Số lượng'])
        
        # Prepare display data
        display_df = df_filtered[[
            'product_name', 'pt_code', 'brand_name', 'package_size',
            'total_qty', 'unit_price', 'total_revenue', 'total_cogs', 
            'gp_usd', 'gp_pct', 'status'
        ]].copy()
        
        display_df.columns = ['Sản phẩm', 'PT Code', 'Thương hiệu', 'Quy cách',
                              'Số lượng', 'Đơn giá', 'Doanh thu', 'COGS', 
                              'GP ($)', 'GP (%)', 'Trạng thái']
        
        # Apply search
        if search:
            display_df = display_df[display_df['Sản phẩm'].str.contains(search, case=False, na=False)]
        
        # Apply sort
        sort_map = {
            'Doanh thu': 'Doanh thu',
            'GP%': 'GP (%)',
            'GP $': 'GP ($)',
            'Số lượng': 'Số lượng'
        }
        display_df = display_df.sort_values(sort_map[sort_by], ascending=False)
        
        st.dataframe(
            display_df.style.format({
                'Số lượng': '{:,.0f}',
                'Đơn giá': '${:.2f}',
                'Doanh thu': '${:,.0f}',
                'COGS': '${:,.0f}',
                'GP ($)': '${:,.0f}',
                'GP (%)': '{:.1f}%'
            }),
            use_container_width=True,
            hide_index=True,
            height=600
        )
        
        # Download button
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="📥 Tải xuống CSV",
            data=csv,
            file_name="gp_analysis_demo.csv",
            mime="text/csv"
        )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: gray;'>
        📊 GP Analysis Dashboard v1.0 | Demo Version<br>
        ⚠️ Dữ liệu hiển thị là dữ liệu giả lập, không phải dữ liệu thực tế của công ty
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
