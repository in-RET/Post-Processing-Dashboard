# -*- coding: utf-8 -*-
"""
Created on Mon Nov 24 12:51:24 2025

@author: rbala
"""
import streamlit as st
import pandas as pd
import tempfile
from src.dashboard_utils import load_oemof_results, interpret_results, create_bus_dataframes, create_component_dataframes, extract_system_metadata, create_storage_dataframes
import os
import plotly.express as px
from datetime import datetime
from src.cost_calc import cost_calculation_from_es_and_results

def compare_scenarios(energysystem, results, bus_dfs, component_dfs, component_scalars, storage_dfs, component_bus_mapping):
    st.header("🔄 Multi-Scenario Comparison")
    
    base_scenario_name = st.text_input("Base Scenario Name", value="Base Scenario", key="base_name")
    is_regionalisation = st.checkbox(
        "Enable Regional Component Aggregation", 
        value=False,
        help="If checked, components with regional suffixes (_n, _s, _e, _m, etc.) will be aggregated together"
    )
    
    if is_regionalisation:
        st.info("🔍 Regionalisation enabled: Components with regional suffixes (_n, _s, _e, _m) will be aggregated")
    st.subheader(f"📊 {base_scenario_name} (Current)")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        total_flow = sum([df.sum().sum() for df in bus_dfs.values()])
        st.metric("Total System Flow", f"{total_flow:,.0f} MWh")
    
    with col2:
        st.metric("Number of Buses", len(bus_dfs))
    
    with col3:
        st.metric("Number of Components", len(component_dfs))
    
    # Number of comparison scenarios
    st.subheader("🔢 Comparison Setup")
    num_comparisons = st.selectbox(
        "Number of comparison scenarios", 
        options=[1, 2, 3, 4, 5, 6],
        index=0,
        help="Select how many scenarios you want to compare with the base scenario"
    )
    
    comparison_scenarios = []
    
    for i in range(num_comparisons):
        st.markdown("---")
        st.subheader(f"📁 Comparison Scenario {i+1}")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            scenario_file = st.file_uploader(
                f"Upload dump file for Scenario {i+1}", 
                type=['dump'], 
                key=f"scenario_{i}"
            )
        
        with col2:
            scenario_name = st.text_input(
                f"Scenario {i+1} Name", 
                value=f"Scenario {i+1}", 
                key=f"name_{i}"
            )
        
        comparison_scenarios.append({
            'file': scenario_file,
            'name': scenario_name,
            'index': i
        })
    
    all_files_uploaded = all(scenario['file'] is not None for scenario in comparison_scenarios)
    
    if num_comparisons > 0 and all_files_uploaded:
        try:
            comparison_data = []
            
            for scenario in comparison_scenarios:
                with st.spinner(f"Loading {scenario['name']}..."):
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.dump') as tmp_file:
                        tmp_file.write(scenario['file'].getvalue())
                        scenario_path = tmp_file.name
                    
                    energysystem_comp, results_comp = load_oemof_results(scenario_path)
                    
                    # Process results
                    bus_sequences_comp, bus_scalars_comp, component_sequences_comp, component_scalars_comp, component_bus_mapping_comp = interpret_results(results_comp)
                    bus_dfs_comp = create_bus_dataframes(bus_sequences_comp, energysystem_comp)
                    component_dfs_comp = create_component_dataframes(component_sequences_comp, energysystem_comp)
                    storage_dfs_comp = create_storage_dataframes(component_sequences_comp, energysystem_comp)
                    
                    comparison_data.append({
                        'name': scenario['name'],
                        'bus_dfs': bus_dfs_comp,
                        'component_dfs': component_dfs_comp,
                        'component_scalars': component_scalars_comp,
                        'storage_dfs': storage_dfs_comp,
                        'component_bus_mapping': component_bus_mapping_comp,
                        'energysystem': energysystem_comp,  
                        'results': results_comp,
                        'file_path': scenario_path
                    })
            
            display_comparison_tables(
                bus_dfs, component_dfs,component_scalars, storage_dfs, component_bus_mapping, base_scenario_name,
                comparison_data, energysystem, results, is_regionalisation
            )
            
            for scenario_data in comparison_data:
                os.unlink(scenario_data['file_path'])
            
        except Exception as e:
            st.error(f"Error comparing scenarios: {e}")
            import traceback
            st.error(f"Detailed error: {traceback.format_exc()}")
    
    elif num_comparisons > 0:
        st.info(f"📁 Please upload all {num_comparisons} comparison dump files")
    
    else:
        st.info("🔢 Select the number of comparison scenarios to get started")
    
def display_comparison_tables(base_bus_dfs, base_component_dfs,base_component_scalars, base_storage_dfs, base_component_bus_mapping,
                              base_name, comparison_data, base_energysystem, base_results, is_regionalisation=False):
    """Display simple comparison tables with multiindex columns (Total Flow first level, scenarios second level)"""
    
    # Create combined data for all scenarios
    all_scenarios = [{
        'name': base_name, 
        'bus_dfs': base_bus_dfs, 
        'component_dfs': base_component_dfs,
        'component_scalars': base_component_scalars,
        'storage_dfs': base_storage_dfs,
        'component_bus_mapping': base_component_bus_mapping,
        'energysystem': base_energysystem,  # Base scenario energysystem
        'results': base_results  # Base scenario results
    }]
    all_scenarios.extend(comparison_data)
    
    # Create tabs for different comparison types
    tab1, tab2, tab3 = st.tabs(["🚌 Bus Comparison", "⚙️ Component Comparison", "🔋 Storage Comparison"])
    
    with tab1:
        # Bus Summary Tables
        st.subheader("🚌 Bus Summary Comparison")
        
        # Create tabs for Total Flow and Peak Flow
        bus_tab1, bus_tab2 = st.tabs(["📊 Total Flow (MWh)", "🔝 Peak Flow (MW)"])
        
        with bus_tab1:
            st.write("**Total Energy Flow through Buses**")
            if is_regionalisation:
                bus_total_flow_data = create_regional_bus_multiindex_total_flow_table(all_scenarios)
            else:
                bus_total_flow_data = create_bus_multiindex_total_flow_table(all_scenarios)
            
            if not bus_total_flow_data.empty:
                styled_bus_total_df = format_multiindex_dataframe(bus_total_flow_data, 'total')
                st.dataframe(styled_bus_total_df, use_container_width=True, height=400)
            else:
                st.info("No bus data available for comparison")
        
        with bus_tab2:
            st.write("**Maximum Power Flow through Buses**")
            if is_regionalisation:
                bus_peak_flow_data = create_regional_bus_multiindex_peak_flow_table(all_scenarios)
            else:
                bus_peak_flow_data = create_bus_multiindex_peak_flow_table(all_scenarios)
            
            if not bus_peak_flow_data.empty:
                styled_bus_peak_df = format_multiindex_dataframe(bus_peak_flow_data, 'peak')
                st.dataframe(styled_bus_peak_df, use_container_width=True, height=400)
            else:
                st.info("No bus data available for comparison")
        
        # Download buttons for bus data
        col1, col2 = st.columns(2)
        with col1:
            if not bus_total_flow_data.empty:
                bus_total_csv = bus_total_flow_data.to_csv(index=False)
                st.download_button(
                    label="Download Bus Total Flow CSV",
                    data=bus_total_csv,
                    file_name=f"bus_total_flow_comparison_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    key="download_bus_total"
                )
        with col2:
            if not bus_peak_flow_data.empty:
                bus_peak_csv = bus_peak_flow_data.to_csv(index=False)
                st.download_button(
                    label="Download Bus Peak Flow CSV",
                    data=bus_peak_csv,
                    file_name=f"bus_peak_flow_comparison_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    key="download_bus_peak"
                )
    
    with tab2:
        # Component Summary Tables
        st.subheader("⚙️ Component Summary Comparison")
        
        # Create tabs for Total Flow and Peak Flow
        comp_tab1, comp_tab2, comp_tab3 = st.tabs(["📊 Total Flow (MWh)", "🔝 Peak Flow (MW)", "⚖️ Installed Capacity (Optimized)"])
        
        with comp_tab1:
            st.write("**Total Energy Flow from Components**")
            if is_regionalisation:
                component_total_flow_data = create_regional_component_multiindex_total_flow_table(all_scenarios)
            else:
                component_total_flow_data = create_component_multiindex_total_flow_table(all_scenarios)
            
            if not component_total_flow_data.empty:
                styled_comp_total_df = format_multiindex_dataframe(component_total_flow_data, 'total')
                st.dataframe(styled_comp_total_df, use_container_width=True, height=400)
            else:
                st.info("No component data available for comparison")
        
        with comp_tab2:
            st.write("**Maximum Power Flow from Components**")
            if is_regionalisation:
                component_peak_flow_data = create_regional_component_multiindex_peak_flow_table(all_scenarios)
            else:
                component_peak_flow_data = create_component_multiindex_peak_flow_table(all_scenarios)
            
            if not component_peak_flow_data.empty:
                styled_comp_peak_df = format_multiindex_dataframe(component_peak_flow_data, 'peak')
                st.dataframe(styled_comp_peak_df, use_container_width=True, height=400)
            else:
                st.info("No component data available for comparison")
        
        with comp_tab3:
            st.write("**Installed Capacity from Components**")
            component_capacity_data = create_component_multiindex_capacity_table(all_scenarios)
            component_capacity_data = component_capacity_data.apply(pd.to_numeric, errors='coerce')
            
            if not component_capacity_data.empty:
                # format similar to others
                styled_capacity_df = format_multiindex_dataframe(component_capacity_data, 'capacity')
                st.dataframe(styled_capacity_df, use_container_width=True, height=400)
            else:
                st.info("No component capacity data available for comparison")
        
        # Download buttons for component data
        col1, col2, col3 = st.columns(3)
        with col1:
            if not component_total_flow_data.empty:
                comp_total_csv = component_total_flow_data.to_csv(index=False)
                st.download_button(
                    label="Download Component Total Flow CSV",
                    data=comp_total_csv,
                    file_name=f"component_total_flow_comparison_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    key="download_comp_total"
                )
        with col2:
            if not component_peak_flow_data.empty:
                comp_peak_csv = component_peak_flow_data.to_csv(index=False)
                st.download_button(
                    label="Download Component Peak Flow CSV",
                    data=comp_peak_csv,
                    file_name=f"component_peak_flow_comparison_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    key="download_comp_peak"
                )
        
        with col3:
            if not component_capacity_data.empty:
                comp_cap_csv = component_capacity_data.to_csv(index=False)
                st.download_button(
                    label="Download Component Capacity CSV",
                    data=comp_cap_csv,
                    file_name=f"component_capacity_comparison_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    key="download_comp_capacity"
                )
    
    with tab3:
        # NEW: Storage Comparison Tables
        st.subheader("🔋 Storage Comparison")
        st.write("**Storage Flow to NONE buses (Storage capacity analysis)**")
        
        # Create tabs for Storage Total Flow and Peak Flow
        storage_tab1, storage_tab2 = st.tabs(["📊 Storage Flow (MWh)", "🔝 Peak Storage Flow (MWh)"])
        
        with storage_tab1:
            if is_regionalisation:
                storage_total_flow_data = create_regional_storage_multiindex_total_flow_table(all_scenarios)
            else:
                storage_total_flow_data = create_storage_multiindex_total_flow_table(all_scenarios)
            
            if not storage_total_flow_data.empty:
                styled_storage_total_df = format_multiindex_dataframe(storage_total_flow_data, 'total')
                st.dataframe(styled_storage_total_df, use_container_width=True, height=400)
            else:
                st.info("No storage data available for comparison")
        
        with storage_tab2:
            if is_regionalisation:
                storage_peak_flow_data = create_regional_storage_multiindex_peak_flow_table(all_scenarios)
            else:
                storage_peak_flow_data = create_storage_multiindex_peak_flow_table(all_scenarios)
            
            if not storage_peak_flow_data.empty:
                styled_storage_peak_df = format_multiindex_dataframe(storage_peak_flow_data, 'peak')
                st.dataframe(styled_storage_peak_df, use_container_width=True, height=400)
            else:
                st.info("No storage data available for comparison")
                
        # Download buttons for storage data
        col1, col2 = st.columns(2)
        with col1:
            if not storage_total_flow_data.empty:
                storage_total_csv = storage_total_flow_data.to_csv(index=False)
                st.download_button(
                    label="Download Storage flow CSV",
                    data=storage_total_csv,
                    file_name=f"storage_flow_comparison_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    key="download_storage_total"
                )
        with col2:
            if not storage_peak_flow_data.empty:
                storage_peak_csv = storage_peak_flow_data.to_csv(index=False)
                st.download_button(
                    label="Download Peak Storage flow CSV",
                    data=storage_peak_csv,
                    file_name=f"peak_storage_flow_comparison_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    key="download_storage_peak"
                )
    
    st.markdown("---")
    display_cost_comparison(all_scenarios)
    
def format_multiindex_dataframe(df, flow_type):
    """Format multiindex dataframe with proper number formatting"""
    # Create a copy to avoid modifying the original
    styled_df = df.copy()
    
    # Get all numeric columns (scenario columns)
    numeric_columns = []
    for col in df.columns:
        if col[0] in ['Total Flow (MWh)', 'Peak Flow (MW)', 'Installed Capacity (MW or MWh)']:
            numeric_columns.append(col)
    
    # Apply formatting based on flow type
    if flow_type == 'total':
        # Format total flow columns with commas and no decimals
        format_dict = {col: '{:,.0f}' for col in numeric_columns}
    else:  # peak flow
        # Format peak flow columns with one decimal
        format_dict = {col: '{:.1f}' for col in numeric_columns}
    
    return styled_df.style.format(format_dict)

def create_component_multiindex_capacity_table(all_scenarios):
    data = {}

    for scenario in all_scenarios:
        scenario_name = scenario['name']
        scalars = scenario.get('component_scalars', {})

        for comp, bus_dict in scalars.items():
            for bus, value in bus_dict.items():
                key = (comp, bus)

                if key not in data:
                    data[key] = {}

                data[key][scenario_name] = value

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data).T
    df.index = pd.MultiIndex.from_tuples(df.index, names=["Component", "Bus"])

    # ---- Convert to MultiIndex columns like bus table ----
    df.columns = pd.MultiIndex.from_tuples(
        [('Installed Capacity (MW or MWh)', col) for col in df.columns]
    )

    return df

def create_bus_multiindex_total_flow_table(all_scenarios):
    """Create a bus table with multiindex columns (Total Flow first level, scenarios second level)"""
    bus_data = []
    
    # Get all unique buses from all scenarios
    all_buses = set()
    for scenario in all_scenarios:
        all_buses.update(scenario['bus_dfs'].keys())
    
    # Create data for each bus
    for bus in sorted(all_buses):
        bus_row = {('Bus', ''): bus}
        
        for scenario in all_scenarios:
            scenario_name = scenario['name']
            bus_dfs = scenario['bus_dfs']
            
            if bus in bus_dfs:
                df = bus_dfs[bus]
                total_flow = df.sum().sum()
                bus_row[('Total Flow (MWh)', scenario_name)] = total_flow
            else:
                bus_row[('Total Flow (MWh)', scenario_name)] = 0
        
        bus_data.append(bus_row)
    
    df = pd.DataFrame(bus_data)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df

def create_bus_multiindex_peak_flow_table(all_scenarios):
    """Create a bus table with multiindex columns (Peak Flow first level, scenarios second level)"""
    bus_data = []
    
    # Get all unique buses from all scenarios
    all_buses = set()
    for scenario in all_scenarios:
        all_buses.update(scenario['bus_dfs'].keys())
    
    # Create data for each bus
    for bus in sorted(all_buses):
        bus_row = {('Bus', ''): bus}
        
        for scenario in all_scenarios:
            scenario_name = scenario['name']
            bus_dfs = scenario['bus_dfs']
            
            if bus in bus_dfs:
                df = bus_dfs[bus]
                peak_flow = df.max().max()
                bus_row[('Peak Flow (MW)', scenario_name)] = peak_flow
            else:
                bus_row[('Peak Flow (MW)', scenario_name)] = 0
        
        bus_data.append(bus_row)
    
    df = pd.DataFrame(bus_data)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df

def create_component_multiindex_total_flow_table(all_scenarios):
    """Create a component table with multiindex columns (Total Flow first level, scenarios second level)"""
    component_data = []
    
    # Get all unique components from all scenarios
    all_components = set()
    for scenario in all_scenarios:
        all_components.update(scenario['component_dfs'].keys())
    
    # Create data for each component
    for component in sorted(all_components):
        comp_row = {
            ('Component', ''): component
        }
        
        for scenario in all_scenarios:
            scenario_name = scenario['name']
            component_dfs = scenario['component_dfs']
            component_bus_mapping = scenario['component_bus_mapping']
            
            if component in component_dfs:
                df = component_dfs[component]
                should_include = True
                
                if component in component_bus_mapping:
                    bus_info = component_bus_mapping[component]
                    
                    if isinstance(bus_info, dict):
                        output_buses = bus_info.get('outputs', [])
                    elif isinstance(bus_info, (list, tuple)):
                        output_buses = bus_info
                    elif isinstance(bus_info, str):
                        output_buses = [bus_info]
                    else:
                        output_buses = []
                    
                    # If ALL output buses contain "none", exclude this component
                    if output_buses and all('none' in str(bus).lower() for bus in output_buses):
                        should_include = False
                if should_include:
                    total_flow = df.sum().sum()
                    comp_row[('Total Flow (MWh)', scenario_name)] = total_flow
                else:
                    comp_row[('Total Flow (MWh)', scenario_name)] = 0
            else:
                comp_row[('Total Flow (MWh)', scenario_name)] = 0
        
        component_data.append(comp_row)
    
    df = pd.DataFrame(component_data)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df

def create_component_multiindex_peak_flow_table(all_scenarios):
    """Create a component table with multiindex columns (Peak Flow first level, scenarios second level)"""
    component_data = []
    
    # Get all unique components from all scenarios
    all_components = set()
    for scenario in all_scenarios:
        all_components.update(scenario['component_dfs'].keys())
    
    # Create data for each component
    for component in sorted(all_components):
        comp_row = {
            ('Component', ''): component
        }
        
        for scenario in all_scenarios:
            scenario_name = scenario['name']
            component_dfs = scenario['component_dfs']
            component_bus_mapping = scenario['component_bus_mapping']
            
            if component in component_dfs:
                df = component_dfs[component]
                should_include = True
                
                if component in component_bus_mapping:
                    bus_info = component_bus_mapping[component]
                    
                    if isinstance(bus_info, dict):
                        output_buses = bus_info.get('outputs', [])
                    elif isinstance(bus_info, (list, tuple)):
                        output_buses = bus_info
                    elif isinstance(bus_info, str):
                        output_buses = [bus_info]
                    else:
                        output_buses = []
                    
                    # If ALL output buses contain "none", exclude this component
                    if output_buses and all('none' in str(bus).lower() for bus in output_buses):
                        should_include = False
                
                if should_include:
                    peak_flow = df.max().max()
                    comp_row[('Peak Flow (MW)', scenario_name)] = peak_flow
                else:
                    comp_row[('Peak Flow (MW)', scenario_name)] = 0
            else:
                comp_row[('Peak Flow (MW)', scenario_name)] = 0
        
        component_data.append(comp_row)
    
    df = pd.DataFrame(component_data)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df

def create_regional_component_multiindex_peak_flow_table(all_scenarios):
    """Create a regional component table with multiindex columns (Peak Flow first level, scenarios second level)"""
    component_data = []
    
    # Get all unique base component names (without regional suffixes)
    base_components = set()
    regional_suffixes = ['_n', '_s', '_e', '_m', '_north', '_swest', '_east', '_middle']
    
    for scenario in all_scenarios:
        for component_name in scenario['component_dfs'].keys():
            base_name = get_base_component_name(component_name, regional_suffixes)
            base_components.add(base_name)
    
    # Create data for each base component
    for base_component in sorted(base_components):
        comp_row = {
            ('Component', ''): base_component,
        }
        
        for scenario in all_scenarios:
            scenario_name = scenario['name']
            component_dfs = scenario['component_dfs']
            component_bus_mapping = scenario['component_bus_mapping']
            
            
            # SUM all regional peaks for this component (not max)
            total_peak_flow = 0
            regional_components = []
            
            for component_name in component_dfs.keys():
                if get_base_component_name(component_name, regional_suffixes) == base_component:
                    df = component_dfs[component_name]
                    should_include = True
                    
                    if component_name in component_bus_mapping:
                        bus_info = component_bus_mapping[component_name]
                        
                        if isinstance(bus_info, dict):
                            output_buses = bus_info.get('outputs', [])
                        elif isinstance(bus_info, (list, tuple)):
                            output_buses = bus_info
                        elif isinstance(bus_info, str):
                            output_buses = [bus_info]
                        else:
                            output_buses = []
                        
                        # If ALL output buses contain "none", exclude this component
                        if output_buses and all('none' in str(bus).lower() for bus in output_buses):
                            should_include = False
                    
                    if should_include:
                        component_peak = df.max().max()
                        total_peak_flow += component_peak
                        regional_components.append(component_name)
            
            comp_row[('Peak Flow (MW)', scenario_name)] = total_peak_flow
        
        component_data.append(comp_row)
    
    df = pd.DataFrame(component_data)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df

def create_regional_component_multiindex_total_flow_table(all_scenarios):
    """Create a regional component table with multiindex columns (Total Flow first level, scenarios second level)"""
    component_data = []
    
    # Get all unique base component names (without regional suffixes)
    base_components = set()
    regional_suffixes = ['_n', '_s', '_e', '_m', '_north', '_swest', '_east', '_middle']
    
    for scenario in all_scenarios:
        for component_name in scenario['component_dfs'].keys():
            base_name = get_base_component_name(component_name, regional_suffixes)
            base_components.add(base_name)
    
    # Create data for each base component
    for base_component in sorted(base_components):
        comp_row = {
            ('Component', ''): base_component,
        }
        
        for scenario in all_scenarios:
            scenario_name = scenario['name']
            component_dfs = scenario['component_dfs']
            component_bus_mapping = scenario['component_bus_mapping']
            
            # Sum all regional total flows for this component
            total_flow = 0
            regional_components = []
            
            for component_name in component_dfs.keys():
                if get_base_component_name(component_name, regional_suffixes) == base_component:
                    df = component_dfs[component_name]
                    should_include = True
                    
                    if component_name in component_bus_mapping:
                        bus_info = component_bus_mapping[component_name]
                        
                        if isinstance(bus_info, dict):
                            output_buses = bus_info.get('outputs', [])
                        elif isinstance(bus_info, (list, tuple)):
                            output_buses = bus_info
                        elif isinstance(bus_info, str):
                            output_buses = [bus_info]
                        else:
                            output_buses = []
                        
                        # If ALL output buses contain "none", exclude this component
                        if output_buses and all('none' in str(bus).lower() for bus in output_buses):
                            should_include = False
                    
                    if should_include:
                        total_flow += df.sum().sum()
                        regional_components.append(component_name)
            
            comp_row[('Total Flow (MWh)', scenario_name)] = total_flow
        
        component_data.append(comp_row)
    
    df = pd.DataFrame(component_data)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df

# Also update the bus peak flow calculation for regionalisation if needed
def create_regional_bus_multiindex_peak_flow_table(all_scenarios):
    """Create a regional bus table with multiindex columns (Peak Flow first level, scenarios second level)"""
    bus_data = []
    
    # Get all unique base bus names (without regional suffixes)
    base_buses = set()
    regional_suffixes = ['_n', '_s', '_e', '_m', '_north', '_swest', '_east', '_middle']
    
    for scenario in all_scenarios:
        for bus_name in scenario['bus_dfs'].keys():
            base_name = get_base_component_name(bus_name, regional_suffixes)
            base_buses.add(base_name)
    
    # Create data for each base bus
    for base_bus in sorted(base_buses):
        bus_row = {('Bus', ''): base_bus}
        
        for scenario in all_scenarios:
            scenario_name = scenario['name']
            bus_dfs = scenario['bus_dfs']
            
            # SUM all regional peaks for this bus (not max)
            total_peak_flow = 0
            regional_buses = []
            
            for bus_name in bus_dfs.keys():
                if get_base_component_name(bus_name, regional_suffixes) == base_bus:
                    df = bus_dfs[bus_name]
                    bus_peak = df.max().max()
                    total_peak_flow += bus_peak
                    regional_buses.append(bus_name)
            
            bus_row[('Peak Flow (MW)', scenario_name)] = total_peak_flow
            
        
        bus_data.append(bus_row)
    
    df = pd.DataFrame(bus_data)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df

def create_regional_bus_multiindex_total_flow_table(all_scenarios):
    """Create a regional bus table with multiindex columns (Total Flow first level, scenarios second level)"""
    bus_data = []
    
    base_buses = set()
    regional_suffixes = ['_n', '_s', '_e', '_m', '_north', '_swest', '_east', '_middle']
    
    for scenario in all_scenarios:
        for bus_name in scenario['bus_dfs'].keys():
            base_name = get_base_component_name(bus_name, regional_suffixes)
            base_buses.add(base_name)
    
    # Create data for each base bus
    for base_bus in sorted(base_buses):
        bus_row = {('Bus', ''): base_bus}
        
        for scenario in all_scenarios:
            scenario_name = scenario['name']
            bus_dfs = scenario['bus_dfs']
            
            # Sum all regional total flows for this bus
            total_flow = 0
            regional_buses = []
            
            for bus_name in bus_dfs.keys():
                if get_base_component_name(bus_name, regional_suffixes) == base_bus:
                    df = bus_dfs[bus_name]
                    total_flow += df.sum().sum()
                    regional_buses.append(bus_name)
            
            bus_row[('Total Flow (MWh)', scenario_name)] = total_flow
            
        
        bus_data.append(bus_row)
    
    df = pd.DataFrame(bus_data)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df


def get_base_component_name(component_name, regional_suffixes):
    """Extract base component name by removing regional suffixes"""
    # Remove common regional suffixes
    base_name = component_name
    for suffix in regional_suffixes:
        if component_name.endswith(suffix):
            base_name = component_name[:-len(suffix)]
            break
    
    # Also handle cases with multiple underscores
    if '_' in base_name:
        parts = base_name.split('_')
        if len(parts) > 1:
            last_part = parts[-1].lower()
            if last_part in ['n', 's', 'e','m', 'north', 'swest', 'east', 'middle']:
                base_name = '_'.join(parts[:-1])
    
    return base_name


def display_cost_comparison(all_scenarios):
    """Display cost comparison across scenarios using the exact cost calculation function"""
    st.subheader("💰 Cost Comparison")
    
    cost_data = []
    
    for scenario in all_scenarios:
        try:
            if 'energysystem' not in scenario or 'results' not in scenario:
                st.warning(f"Skipping cost calculation for {scenario['name']}: Missing energysystem or results")
                continue
            # Calculate costs for each scenario using the exact function
            cost_df = cost_calculation_from_es_and_results(scenario['energysystem'], scenario['results'])
            
            # Calculate totals
            total_investment = 0
            total_variable = 0
            total_profits = 0
            
            if not cost_df.empty:
                if 'investment costs' in cost_df.columns:
                    investment_series = cost_df['investment costs']
                    if hasattr(investment_series, 'sum'):
                        total_investment = investment_series.sum()
                    else:
                        total_investment = sum(investment_series.values) if hasattr(investment_series, 'values') else 0
                
                if 'variable costs' in cost_df.columns:
                    variable_series = cost_df['variable costs']
                    if hasattr(variable_series, 'sum'):
                        total_variable = variable_series.sum()
                    else:
                        total_variable = sum(variable_series.values) if hasattr(variable_series, 'values') else 0
                
                if 'profits' in cost_df.columns:
                    profits_series = cost_df['profits']
                    if hasattr(profits_series, 'sum'):
                        total_profits = profits_series.sum()
                    else:
                        total_profits = sum(profits_series.values) if hasattr(profits_series, 'values') else 0
            
            total_costs = total_investment + total_variable + total_profits
            
            cost_data.append({
                'Scenario': scenario['name'],
                'Total Costs (Mio. €)': total_costs / 1000000,
                'Investment Costs (Mio. €)': total_investment / 1000000,
                'Variable Costs (Mio. €)': total_variable / 1000000,
                'Profits (Mio. €)': total_profits / 1000000
            })
            
        except Exception as e:
            st.warning(f"Could not calculate costs for {scenario['name']}: {str(e)}")
            import traceback
            st.error(f"Detailed error: {traceback.format_exc()}")
            
            cost_data.append({
                'Scenario': scenario['name'],
                'Total Costs (Mio. €)': 0,
                'Investment Costs (Mio. €)': 0,
                'Variable Costs (Mio. €)': 0,
                'Profits (Mio. €)': 0
            })
    
    if cost_data:
        cost_comparison_df = pd.DataFrame(cost_data)
        
        # Display cost comparison table
        st.dataframe(
            cost_comparison_df.style.format({
                'Total Costs (Mio. €)': '{:.1f}',
                'Investment Costs (Mio. €)': '{:.1f}',
                'Variable Costs (Mio. €)': '{:.1f}',
                'Profits (Mio. €)': '{:.1f}'
            }),
            use_container_width=True
        )
        
        if len(cost_comparison_df) > 0:
            plot_df = cost_comparison_df.melt(
                id_vars=['Scenario'], 
                value_vars=['Investment Costs (Mio. €)', 'Variable Costs (Mio. €)', 'Profits (Mio. €)'],
                var_name='Cost Type', 
                value_name='Amount (Mio. €)'
            )
            
            fig = px.bar(
                plot_df,
                x='Scenario',
                y='Amount (Mio. €)',
                color='Cost Type',
                title="Cost Breakdown Comparison",
                barmode='group',
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Download cost comparison data
        cost_comp_csv = cost_comparison_df.to_csv(index=False)
        st.download_button(
            label="Download Cost Comparison CSV",
            data=cost_comp_csv,
            file_name=f"cost_comparison_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No cost data available for comparison")


def create_storage_multiindex_total_flow_table(all_scenarios):
    """Create a storage table with multiindex columns (Losses to NONE first level, scenarios second level)"""
    storage_data = []
    
    # Get all unique storages from all scenarios
    all_storages = set()
    for scenario in all_scenarios:
        if 'storage_dfs' in scenario:
            all_storages.update(scenario['storage_dfs'].keys())
    
    # Create data for each storage
    for storage in sorted(all_storages):
        storage_row = {('Storage', ''): storage}
        
        for scenario in all_scenarios:
            scenario_name = scenario['name']
            storage_dfs = scenario.get('storage_dfs', {})
            
            if storage in storage_dfs:
                df = storage_dfs[storage]
                total_losses = df.sum().sum()
                storage_row[('Flow to NONE (MWh)', scenario_name)] = round(total_losses)
            else:
                storage_row[('Flow to NONE (MWh)', scenario_name)] = 0
        
        storage_data.append(storage_row)
    
    df = pd.DataFrame(storage_data)
    if not df.empty:
        df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df

def create_storage_multiindex_peak_flow_table(all_scenarios):
    """Create a storage table with multiindex columns (Peak Losses first level, scenarios second level)"""
    storage_data = []
    
    # Get all unique storages from all scenarios
    all_storages = set()
    for scenario in all_scenarios:
        if 'storage_dfs' in scenario:
            all_storages.update(scenario['storage_dfs'].keys())
    
    # Create data for each storage
    for storage in sorted(all_storages):
        storage_row = {('Storage', ''): storage}
        
        for scenario in all_scenarios:
            scenario_name = scenario['name']
            storage_dfs = scenario.get('storage_dfs', {})
            
            if storage in storage_dfs:
                df = storage_dfs[storage]
                peak_losses = df.max().max()
                storage_row[('Peak Flow (MWh)', scenario_name)] = round(peak_losses)
            else:
                storage_row[('Peak Flow (MWh)', scenario_name)] = 0
        
        storage_data.append(storage_row)
    
    df = pd.DataFrame(storage_data)
    if not df.empty:
        df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df

def create_regional_storage_multiindex_total_flow_table(all_scenarios):
    """Create a regional storage table with multiindex columns"""
    storage_data = []
    
    regional_suffixes = ['_n', '_s', '_e', '_m', '_north', '_swest', '_east', '_middle']
    
    # Get all unique base storage names
    base_storages = set()
    for scenario in all_scenarios:
        if 'storage_dfs' in scenario:
            for storage_name in scenario['storage_dfs'].keys():
                base_name = get_base_component_name(storage_name, regional_suffixes)
                base_storages.add(base_name)
    
    # Create data for each base storage
    for base_storage in sorted(base_storages):
        storage_row = {('Storage', ''): base_storage}
        
        for scenario in all_scenarios:
            scenario_name = scenario['name']
            storage_dfs = scenario.get('storage_dfs', {})
            
            # Sum all regional losses for this storage
            total_losses = 0
            
            for storage_name in storage_dfs.keys():
                if get_base_component_name(storage_name, regional_suffixes) == base_storage:
                    df = storage_dfs[storage_name]
                    total_losses += df.sum().sum()
            
            storage_row[('Flow to NONE (MWh)', scenario_name)] = round(total_losses)
        
        storage_data.append(storage_row)
    
    df = pd.DataFrame(storage_data)
    if not df.empty:
        df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df

def create_regional_storage_multiindex_peak_flow_table(all_scenarios):
    """Create a regional storage table with multiindex columns"""
    storage_data = []
    
    regional_suffixes = ['_n', '_s', '_e', '_m', '_north', '_swest', '_east', '_middle']
    
    # Get all unique base storage names
    base_storages = set()
    for scenario in all_scenarios:
        if 'storage_dfs' in scenario:
            for storage_name in scenario['storage_dfs'].keys():
                base_name = get_base_component_name(storage_name, regional_suffixes)
                base_storages.add(base_name)
    
    # Create data for each base storage
    for base_storage in sorted(base_storages):
        storage_row = {('Storage', ''): base_storage}
        
        for scenario in all_scenarios:
            scenario_name = scenario['name']
            storage_dfs = scenario.get('storage_dfs', {})
            
            # Sum all regional peak losses for this storage
            total_peak_losses = 0
            
            for storage_name in storage_dfs.keys():
                if get_base_component_name(storage_name, regional_suffixes) == base_storage:
                    df = storage_dfs[storage_name]
                    total_peak_losses += df.max().max()
            
            storage_row[('Peak Flow (MWh)', scenario_name)] = round(total_peak_losses)
        
        storage_data.append(storage_row)
    
    df = pd.DataFrame(storage_data)
    if not df.empty:
        df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df