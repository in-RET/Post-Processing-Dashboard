# -*- coding: utf-8 -*-
"""
Created on Tue Oct 28 12:20:24 2025

@author: rbala
"""
import streamlit as st 
import pandas as pd

class ResponsiveLayout:
    def __init__(self):
        self.inject_responsive_css()
        
    def inject_responsive_css(self):
        """Inject CSS for fully responsive design"""
        st.markdown("""
        <style>
        /* Base responsive container */
        .main .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
            padding-left: 1rem;
            padding-right: 1rem;
            max-width: 100%;
        }
        
        /* Dynamic font scaling */
        @media (max-width: 768px) {
            /* Mobile */
            .main h1 { font-size: 1.4rem !important; }
            .main h2 { font-size: 1.2rem !important; }
            .main h3 { font-size: 1.1rem !important; }
            .stDataFrame { font-size: 0.75rem !important; }
            .stMetric { padding: 0.5rem !important; }
            .element-container { margin-bottom: 0.5rem !important; }
        }
        
        @media (min-width: 769px) and (max-width: 1024px) {
            /* Tablet */
            .main h1 { font-size: 1.8rem !important; }
            .main h2 { font-size: 1.5rem !important; }
            .main h3 { font-size: 1.3rem !important; }
            .stDataFrame { font-size: 0.85rem !important; }
        }
        
        @media (min-width: 1025px) {
            /* Desktop */
            .main h1 { font-size: 2.2rem !important; }
            .main h2 { font-size: 1.8rem !important; }
            .main h3 { font-size: 1.5rem !important; }
            .stDataFrame { font-size: 0.9rem !important; }
        }
        
        /* Responsive columns */
        .row-widget.stColumns {
            gap: 0.5rem;
        }
        
        @media (max-width: 768px) {
            .row-widget.stColumns {
                flex-direction: column;
                gap: 0.25rem;
            }
        }
        
        /* Responsive tabs */
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
        }
        
        .stTabs [data-baseweb="tab"] {
            height: auto;
            white-space: pre-wrap;
            padding: 0.5rem 0.75rem;
        }
        
        @media (max-width: 768px) {
            .stTabs [data-baseweb="tab-list"] {
                flex-direction: column;
            }
            .stTabs [data-baseweb="tab"] {
                width: 100%;
            }
        }
        
        /* Responsive charts */
        .js-plotly-plot .plotly, .js-plotly-plot .plotly div {
            width: 100% !important;
        }
        
        /* Responsive sidebar */
        @media (max-width: 768px) {
            .css-1d391kg {
                width: 100%;
                position: relative;
            }
        }
        
        /* Responsive metrics */
        [data-testid="stMetricValue"] {
            font-size: 1rem;
        }
        
        @media (max-width: 768px) {
            [data-testid="stMetricValue"] {
                font-size: 0.9rem;
            }
            [data-testid="stMetricLabel"] {
                font-size: 0.8rem;
            }
        }
        
        /* Responsive dataframes */
        .dataframe {
            width: 100%;
        }
        
        @media (max-width: 768px) {
            .dataframe {
                font-size: 0.7rem;
            }
        }
        
        /* Make everything fluid */
        .element-container {
            width: 100% !important;
        }
        </style>
        """, unsafe_allow_html=True)
    
    def get_columns_config(self, num_items):
        """Dynamically determine number of columns based on content"""
        if num_items <= 2:
            return 1
        elif num_items <= 4:
            return 2
        elif num_items <= 6:
            return 3
        else:
            return 4
    
    def create_adaptive_columns(self, num_items):
        """Create columns that adapt to screen size"""
        num_cols = self.get_columns_config(num_items)
        return st.columns(num_cols)
    
    def adaptive_metric_grid(self, metrics, cols_per_row=None):
        """Create adaptive grid for metrics"""
        if not cols_per_row:
            cols_per_row = self.get_columns_config(len(metrics))
        
        cols = st.columns(cols_per_row)
        for i, (label, value) in enumerate(metrics):
            col_idx = i % cols_per_row
            with cols[col_idx]:
                st.metric(label, value)
    
    def adaptive_chart_height(self, base_height=400):
        """Calculate adaptive chart height"""
        return base_height

def create_responsive_tabs(tab_names):
    """Create responsive tabs that adapt to screen size"""
    return st.tabs(tab_names)

def responsive_display_system_summary(bus_dfs, component_dfs, metadata, layout):
    """Responsive system summary display"""
    st.header("📊 System Overview")
    
    # Adaptive metrics grid
    metrics = [
        ("Total Buses", metadata['system_summary']['total_buses']),
        ("Total Components", metadata['system_summary']['total_components']),
        ("Data Points", metadata['system_summary']['total_data_points']),
        ("Simulation Duration", metadata['system_summary']['simulation_duration'])
    ]
    
    layout.adaptive_metric_grid(metrics)
    
    # Bus summary with adaptive layout
    if bus_dfs:
        st.subheader("Bus Summary")
        bus_summary_data = []
        for bus_name, meta in metadata['buses'].items():
            bus_summary_data.append({
                'Bus Name': bus_name,
                'Total Flow [MWh]': meta['total_flow'],
                'Max Flow [MW]': meta['max_flow'],
                'Connected Components': len(meta['connected_components'])
            })
        
        if bus_summary_data:
            bus_summary_df = pd.DataFrame(bus_summary_data)
            st.dataframe(bus_summary_df.style.format({
                'Total Flow [MWh]': '{:.0f}',
                'Max Flow [MW]': '{:.1f}'
            }), use_container_width=True)