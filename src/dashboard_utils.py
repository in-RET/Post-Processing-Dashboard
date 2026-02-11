# -*- coding: utf-8 -*-
"""
Created on Fri Oct 24 15:21:22 2025

@author: rbala

'Interactive dashboard for post processing'
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pickle
import tempfile
import os
from datetime import datetime
from oemof import network, solph
import shutil
from oemof.solph import processing
from src.cost_calc import cost_calculation_from_es_and_results

my_path = os.path.abspath(os.path.dirname(__file__))
def load_oemof_results(dump_file_path):
    """Load oemof dump file and extract results"""
    energysystem = solph.EnergySystem()
    energysystem.restore(my_path, dump_file_path)
        
    return energysystem, energysystem.results["main"]

    
def interpret_results(results):          
    bus_sequences = {}
    bus_scalars = {}
    component_sequences = {}
    component_scalars = {}
    component_bus_mapping = {}
    
    # Iterate through results to classify flows for Bus, Source, Converter, etc.
    for key, value in results.items():
        component_name = str(key[1].label) if key[1] else "None"  # Extract component name (e.g., Source, Converter, etc.)
        
        if isinstance(key[0], solph.Bus):
            bus_name = str(key[0].label)  # Extract bus name
            
            if component_name != "None":
                component_bus_mapping[component_name] = bus_name
            
            # Extract sequences for Bus
            if isinstance(value, dict) and "sequences" in value:
                if bus_name not in bus_sequences:
                    bus_sequences[bus_name] = {}
                bus_sequences[bus_name][component_name] = value["sequences"]
    
            # Extract scalar values for Bus
            elif isinstance(value, (int, float)):
                if bus_name not in bus_scalars:
                    bus_scalars[bus_name] = {}
                bus_scalars[bus_name][component_name] = value["scalars"]["total"]
    
        
        elif isinstance(key[0], (solph.components.Source, solph.components.Link, solph.components.Converter, solph.components.Sink, solph.components.GenericStorage)):
            component_name = str(key[0].label)  # Extract component name
            component_obj = key[0]
            connected_bus = "None"
            
            if hasattr(component_obj, 'outputs'):
                # Sources, Converters - connected via outputs
                output_buses = list(component_obj.outputs.keys())
                if output_buses:
                    connected_bus = str(output_buses[0].label)
            
            elif hasattr(component_obj, 'inputs'):
                # Sinks - connected via inputs  
                input_buses = list(component_obj.inputs.keys())
                if input_buses:
                    connected_bus = str(input_buses[0].label)
            
            component_bus_mapping[component_name] = connected_bus
            
            # Extract sequences for Component
            if isinstance(value, dict):
                if "scalars" in value:
                    # Accessing the total scalar value from the 'scalars' pandas Series
                    total_value = value["scalars"].get("total", 0)
            
                    if component_name not in component_scalars:
                        component_scalars[component_name] = {}
            
                    component_scalars[component_name][str(key[1].label) if key[1] else "None"] = total_value
            
                # Handling 'sequences' part (if needed)
                if "sequences" in value:
                    sequence_data = value["sequences"]
            
                    # You can choose to store sequences in a separate dictionary or process as needed
                    if component_name not in component_sequences:
                        component_sequences[component_name] = {}
            
                    component_sequences[component_name][str(key[1].label) if key[1] else "None"] = sequence_data

    return bus_sequences, bus_scalars, component_sequences, component_scalars, component_bus_mapping

def create_bus_dataframes(bus_sequences, energysystem):
    """Convert bus sequences to DataFrames with proper time index"""
    bus_dfs = {}
    
    for bus_name, components in bus_sequences.items():
        bus_data = {}
        
        for component_name, sequence_data in components.items():
            # Extract the actual flow values from the sequence data
            if hasattr(sequence_data, 'values'):
                # If it's a pandas Series or similar with .values attribute
                flow_values = sequence_data.values
            elif isinstance(sequence_data, dict):
                # If it's a dictionary, get the flow data
                flow_data = sequence_data.get('flow', None)
                if flow_data is not None and hasattr(flow_data, 'values'):
                    flow_values = flow_data.values
                else:
                    continue  # Skip if no valid flow data
            else:
                continue  # Skip if we can't extract values
            
            # Ensure we have a 1D array
            if hasattr(flow_values, 'shape') and len(flow_values.shape) == 1:
                bus_data[f"{bus_name} -> {component_name}"] = flow_values
            else:
                # If it's 2D, take the first column or flatten
                try:
                    if hasattr(flow_values, 'shape') and len(flow_values.shape) == 2:
                        bus_data[f"{bus_name} -> {component_name}"] = flow_values[:, 0]
                    else:
                        bus_data[f"{bus_name} -> {component_name}"] = flow_values.flatten()
                except:
                    st.warning(f"Could not process data for {bus_name} -> {component_name}")
                    continue
        
        if bus_data:
            # Use energysystem timeindex
            time_index = energysystem.timeindex
            
            # Ensure all arrays have the same length
            min_length = min(len(arr) for arr in bus_data.values())
            if min_length != len(time_index):
                st.warning(f"Data length mismatch for bus {bus_name}. Truncating to {min_length} points.")
                time_index = time_index[:min_length]
                
            # Truncate all arrays to the same length
            for key in bus_data.keys():
                bus_data[key] = bus_data[key][:min_length]
            
            # Create DataFrame
            bus_dfs[bus_name] = pd.DataFrame(bus_data, index=time_index[:min_length])
    
    return bus_dfs

def create_component_dataframes(component_sequences, energysystem):
    """Convert component sequences to DataFrames"""
    component_dfs = {}
    
    for component_name, targets in component_sequences.items():
        component_data = {}
        
        for target_name, sequence_data in targets.items():
            if str(target_name) == 'None':
                continue
            
            if hasattr(sequence_data, 'values'):
                # If it's a pandas Series or similar with .values attribute
                flow_values = sequence_data.values
            elif isinstance(sequence_data, dict):
                # If it's a dictionary, get the flow data
                flow_data = sequence_data.get('flow', None)
                if flow_data is not None and hasattr(flow_data, 'values'):
                    flow_values = flow_data.values
                else:
                    continue  # Skip if no valid flow data
            else:
                continue  # Skip if we can't extract values
            
            # Ensure we have a 1D array
            if hasattr(flow_values, 'shape') and len(flow_values.shape) == 1:
                component_data[f"{component_name} -> {target_name}"] = flow_values
            else:
                # If it's 2D, take the first column or flatten
                try:
                    if hasattr(flow_values, 'shape') and len(flow_values.shape) == 2:
                        component_data[f"{component_name} -> {target_name}"] = flow_values[:, 0]
                    else:
                        component_data[f"{component_name} -> {target_name}"] = flow_values.flatten()
                except:
                    print(f"Could not process data for {component_name} -> {target_name}")
                    continue
        
        if component_data:
            # Use energysystem timeindex
            time_index = energysystem.timeindex
            
            # Ensure all arrays have the same length
            min_length = min(len(arr) for arr in component_data.values())
            if min_length != len(time_index):
                print(f"Data length mismatch for component {component_name}. Truncating to {min_length} points.")
                time_index = time_index[:min_length]
                
            # Truncate all arrays to the same length
            for key in component_data.keys():
                component_data[key] = component_data[key][:min_length]
            
            # Create DataFrame
            component_dfs[component_name] = pd.DataFrame(component_data, index=time_index[:min_length])
    
    return component_dfs

def create_storage_dataframes(component_sequences, energysystem):
    """Convert component sequences to DataFrames for STORAGES ONLY that flow to 'NONE'"""
    storage_dfs = {}
    
    for component_name, targets in component_sequences.items():
        is_storage = any(keyword in component_name.lower() 
                        for keyword in ['storage', 'battery'])
        
        if not is_storage:
            continue
            
        component_data = {}
        
        for target_name, sequence_data in targets.items():
            if str(target_name).upper() != 'NONE':
                continue
            
            if hasattr(sequence_data, 'values'):
                flow_values = sequence_data.values
            elif isinstance(sequence_data, dict):
                flow_data = sequence_data.get('flow', None)
                if flow_data is not None and hasattr(flow_data, 'values'):
                    flow_values = flow_data.values
                else:
                    continue  
            else:
                continue  
            
            if hasattr(flow_values, 'shape') and len(flow_values.shape) == 1:
                component_data[f"{component_name} -> {target_name}"] = flow_values
            else:
                try:
                    if hasattr(flow_values, 'shape') and len(flow_values.shape) == 2:
                        component_data[f"{component_name} -> {target_name}"] = flow_values[:, 0]
                    else:
                        component_data[f"{component_name} -> {target_name}"] = flow_values.flatten()
                except:
                    print(f"Could not process data for {component_name} -> {target_name}")
                    continue
        
        if component_data:
            time_index = energysystem.timeindex
            min_length = min(len(arr) for arr in component_data.values())
            if min_length != len(time_index):
                print(f"Data length mismatch for storage {component_name}. Truncating to {min_length} points.")
                time_index = time_index[:min_length]
            
            for key in component_data.keys():
                component_data[key] = component_data[key][:min_length]
            storage_dfs[component_name] = pd.DataFrame(component_data, index=time_index[:min_length])
    
    return storage_dfs

def extract_system_metadata(energysystem, bus_dfs, component_dfs, storage_dfs, component_bus_mapping):
    """Extract comprehensive system metadata"""
    metadata = {
        'buses': {},
        'components': {},
        'storages': {},
        'timeframe': {
            'start': energysystem.timeindex[0],
            'end': energysystem.timeindex[-1],
            'periods': len(energysystem.timeindex)
        },
        'system_summary': {}
    }
    
    # Bus metadata
    for bus_name, df in bus_dfs.items():
        metadata['buses'][bus_name] = {
            'connected_components': list(component_bus_mapping.keys()),
            'data_columns': df.columns.tolist(),
            'total_flow': df.sum().sum(),
            'max_flow': df.max().max(),
            'data_points': len(df)
        }
    
    # Component metadata
    for component_name, df in component_dfs.items():
        metadata['components'][component_name] = {
            'connected_bus': component_bus_mapping.get(component_name, 'Unknown'),
            'data_columns': df.columns.tolist(),
            'total_flow': df.sum().sum(),
            'max_flow': df.max().max(),
            'data_points': len(df)
        }
    
    # Storage metadata
    for component_name, df in storage_dfs.items():
        metadata['storages'][component_name] = {
            'connected_bus': component_bus_mapping.get(component_name, 'Unknown'),
            'data_columns': df.columns.tolist(),
            'total_flow': df.sum().sum(),
            'max_flow': df.max().max(),
            'data_points': len(df)
        }
    
    # System summary
    metadata['system_summary'] = {
        'total_buses': len(bus_dfs),
        'total_components': len(component_dfs)-len(storage_dfs),
        'total_storages': len(storage_dfs),
        'total_data_points': len(energysystem.timeindex),
        'simulation_duration': f"{((energysystem.timeindex[-1] - energysystem.timeindex[0]).days) + 1} days"
    }
    
    return metadata

def display_bus_analysis(bus_dfs, metadata):
    st.header("Bus Analysis")
    
    if not bus_dfs:
        st.warning("No bus data available")
        return
    
    selected_bus = st.selectbox("Select Bus", list(bus_dfs.keys()))
    
    if selected_bus:
        bus_df = bus_dfs[selected_bus]
        bus_meta = metadata['buses'][selected_bus]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader(f"Bus: {selected_bus}")
            st.metric("Total Flow", f"{bus_meta['total_flow']:.0f} MWh")
            st.metric("Total Flow in TWh", f"{bus_meta['total_flow']/1000000:.2f} TWh" )
            st.metric("Max Flow", f"{bus_meta['max_flow']:.1f} MW")
            st.metric("Connected Components", len(bus_meta['connected_components']))
        
        with col2:
            # Time resolution selection
            resolution = st.selectbox("Resolution", ["Raw", "Daily", "Weekly", "Monthly"])
            
            # Date range filter
            min_date = bus_df.index.min()
            max_date = bus_df.index.max()
            date_range = st.date_input(
                "Select date range:",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date
            )
        
        if len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = bus_df.loc[start_date:end_date]
        else:
            filtered_df = bus_df
        
        if resolution == "Daily":
            display_df = filtered_df.resample('D').sum()
        elif resolution == "Weekly":
            display_df = filtered_df.resample('W').sum()
        elif resolution == "Monthly":
            display_df = filtered_df.resample('M').sum()
        else:
            display_df = filtered_df
        
        # Flow selection
        selected_flows = st.multiselect(
            "Select Flows to Display",
            options=display_df.columns.tolist(),
            default=display_df.columns.tolist()[:min(5, len(display_df.columns))]
        )
        
        if selected_flows:
            fig = make_subplots(
                rows=2, cols=1,
                subplot_titles=('Time Series', 'Daily Profile'),
                specs=[[{"secondary_y": False}],
                       [{"secondary_y": False}]]
            )
            
            # Time series
            for flow in selected_flows:
                fig.add_trace(
                    go.Scatter(x=display_df.index, y=display_df[flow], name=flow),
                    row=1, col=1
                )
            
      
            if len(display_df) > 24:
                daily_profile = display_df[selected_flows].groupby(display_df.index.hour).mean()
                for flow in selected_flows:
                    fig.add_trace(
                        go.Scatter(x=daily_profile.index, y=daily_profile[flow], 
                                 name=f"{flow} (hourly avg)", showlegend=False),
                        row=2, col=1
                    )
            
          
            
            fig.update_layout(height=800, title_text=f"Bus Analysis: {selected_bus}")
            st.plotly_chart(fig, use_container_width=True)
            
        

def display_component_analysis(component_dfs, metadata):
    st.header("⚙️ Component Analysis")
    
    if not component_dfs:
        st.info("No component data available")
        return
    
    # Component selection
    selected_component = st.selectbox("Select Component", list(component_dfs.keys()))
    
    if selected_component:
        comp_df = component_dfs[selected_component]
        comp_meta = metadata['components'][selected_component]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader(f"Component: {selected_component}")
            st.metric("Total Flow", f"{comp_meta['total_flow']:.0f} MWh")
            st.metric("Total Flow in TWh", f"{comp_meta['total_flow']/1000000:.2f} TWh" )
            st.metric("Max Flow", f"{comp_meta['max_flow']:.1f} MW")
            st.metric("Connected Bus", comp_meta['connected_bus'])
        
        with col2:
            # Display all flows for this component
            st.subheader("Component Flows")
            for col in comp_df.columns:
                total_flow = comp_df[col].sum()
                st.write(f"**{col}**: {total_flow:.0f} MWh")
        
        # Time series plot
        fig = px.line(comp_df, title=f"Component Flows: {selected_component}")
        st.plotly_chart(fig, use_container_width=True)
        
        # Flow summary
        #st.subheader("Flow Summary")
        #st.dataframe(comp_df.describe())

def display_storage_analysis(storage_dfs, metadata):
    st.header("⚙️ Storage Analysis")
    
    if not storage_dfs:
        st.info("No Storage data available")
        return
    
    # Component selection
    selected_component = st.selectbox("Select Component", list(storage_dfs.keys()), key="storage_analysis_selectbox")
    
    if selected_component:
        comp_df = storage_dfs[selected_component]
        comp_meta = metadata['storages'][selected_component]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader(f"Component: {selected_component}")
            st.metric("Total Flow", f"{comp_meta['total_flow']:.0f} MWh")
            st.metric("Total Flow in TWh", f"{comp_meta['total_flow']/1000000:.2f} TWh" )
            st.metric("Max Flow", f"{comp_meta['max_flow']:.1f} MWh")
            st.metric("Connected Bus", comp_meta['connected_bus'])
        
        with col2:
            # Display all flows for this component
            st.subheader("Component Flows")
            for col in comp_df.columns:
                total_flow = comp_df[col].sum()
                st.write(f"**{col}**: {total_flow:.0f} MWh")
        
        # Time series plot
        fig = px.line(comp_df, title=f"Component Flows: {selected_component}")
        st.plotly_chart(fig, use_container_width=True)
        
        # Flow summary
        #st.subheader("Flow Summary")
        #st.dataframe(comp_df.describe())
def format_currency(value):
    """Format currency with dynamic units."""
    abs_val = abs(value)

    if abs_val >= 1e9:
        return f"{value/1e9:,.2f} B€"
    elif abs_val >= 1e6:
        return f"{value/1e6:,.2f} M€"
    else:
        return f"{value:,.2f} €"        
        
def display_cost_analysis(energysystem, results):
    """Display cost analysis in system summary using the exact cost calculation function"""
    st.subheader("💰 Cost Analysis")
    
    try:
        # Calculate costs using the exact function
        cost_df = cost_calculation_from_es_and_results(energysystem, results)
        
        # Calculate totals
        total_investment = cost_df['investment costs'].sum() if 'investment costs' in cost_df.columns else 0
        total_variable = cost_df['variable costs'].sum() if 'variable costs' in cost_df.columns else 0
        total_profits = cost_df['profits'].sum() if 'profits' in cost_df.columns else 0
        total_costs = total_investment + total_variable + total_profits
        
        # Display total cost metrics
        col1, col2, col3, col4 = st.columns(4)
    
        with col1:
            st.metric("Total System Costs", format_currency(total_costs), delta = None, delta_color = 'inverse')
        
        with col2:
            st.metric("Investment Costs", format_currency(total_investment), delta = None, delta_color = 'inverse')
        
        with col3:
            st.metric("Variable Costs",format_currency(total_variable), delta = None, delta_color = 'inverse')
        
        with col4:
            st.metric("Profits/Revenues", format_currency(total_profits), delta = None, delta_color = 'normal')
        
        # Display detailed cost breakdown
        st.subheader("📊 Detailed Cost Breakdown")
        
        # Create tabs for different cost types
        tab1, tab2, tab3 = st.tabs(["🏗️ Investment Costs", "⚡ Variable Costs", "💰 Profits"])
        
        with tab1:
            if 'investment costs' in cost_df.columns and not cost_df['investment costs'].empty:
                investment_data = []
                for component, cost in cost_df['investment costs'].items():
                    if cost > 0:
                        investment_data.append({
                            'Component Connection': str(component),
                            'Investment Cost (€)': cost
                        })
                if investment_data:
                    investment_df = pd.DataFrame(investment_data)
                    st.dataframe(
                        investment_df.style.format({'Investment Cost (€)': '{:,.0f}'}),
                        use_container_width=True
                    )
                else:
                    st.info("No investment costs found")
            else:
                st.info("No investment costs data available")
        
        with tab2:
            if 'variable costs' in cost_df.columns and not cost_df['variable costs'].empty:
                variable_data = []
                for component, cost in cost_df['variable costs'].items():
                    if cost > 0:
                        variable_data.append({
                            'Component Connection': str(component),
                            'Variable Cost (€)': cost
                        })
                if variable_data:
                    variable_df = pd.DataFrame(variable_data)
                    st.dataframe(
                        variable_df.style.format({'Variable Cost (€)': '{:,.0f}'}),
                        use_container_width=True
                    )
                else:
                    st.info("No variable costs found")
            else:
                st.info("No variable costs data available")
        
        with tab3:
            if 'profits' in cost_df.columns and not cost_df['profits'].empty:
                profit_data = []
                for component, profit in cost_df['profits'].items():
                    if profit < 0:
                        profit_data.append({
                            'Component Connection': str(component),
                            'Profit/Revenue (€)': profit
                        })
                if profit_data:
                    profit_df = pd.DataFrame(profit_data)
                    st.dataframe(
                        profit_df.style.format({'Profit/Revenue (€)': '{:,.0f}'}),
                        use_container_width=True
                    )
                else:
                    st.info("No profits/revenues found")
            else:
                st.info("No profits data available")
        
        # Download cost data
        st.subheader("📥 Export Cost Data")
        cost_csv = cost_df.to_csv()
        st.download_button(
            label="Download Cost Breakdown CSV",
            data=cost_csv,
            file_name=f"cost_breakdown_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )
        
    except Exception as e:
        st.error(f"Error calculating costs: {e}")
        import traceback
        st.error(f"Detailed error: {traceback.format_exc()}")

def display_system_summary(bus_dfs, component_dfs, metadata, energysystem, results):
    st.header("📊 System Overview")
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_bus_flow = sum([meta['total_flow'] for meta in metadata['buses'].values()])
        st.metric("Total System Flow", f"{total_bus_flow:.0f} MWh")
        st.metric("Number of Buses", metadata['system_summary']['total_buses'])
    
    with col2:
        total_component_flow = sum([meta['total_flow'] for meta in metadata['components'].values()])
        st.metric("Total Component Flow", f"{total_component_flow:.0f} MWh")
        st.metric("Number of Components", metadata['system_summary']['total_components']+metadata['system_summary']['total_storages'])
    
    with col3:
        st.metric("Simulation Start Period", metadata['timeframe']['start'].strftime('%Y-%m-%d'))
        st.metric("Simulation End Period", metadata['timeframe']['end'].strftime('%Y-%m-%d'))
    
    with col4:
        st.metric("Time Resolution", f"{metadata['timeframe']['periods']} periods")
        st.metric("Duration", metadata['system_summary']['simulation_duration'])
        
    display_cost_analysis(energysystem, results)
    
    # Bus summary table
    st.subheader("Bus Summary")
    bus_summary_data = []
    for bus_name, meta in metadata['buses'].items():
        bus_summary_data.append({
            'Bus Name': bus_name,
            'Total Flow [MWh]': meta['total_flow'],
            'Max Flow [MW]': meta['max_flow'],
            'Connected Components': len(meta['connected_components']),
            'Data Columns': len(meta['data_columns'])
        })
    
    if bus_summary_data:
        bus_summary_df = pd.DataFrame(bus_summary_data)
        st.dataframe(bus_summary_df.style.format({
            'Total Flow [MWh]': '{:.0f}',
            'Max Flow [MW]': '{:.1f}'
        }))
    
    # Component summary table
    st.subheader("Component Summary")
    component_summary_data = []
    for comp_name, meta in metadata['components'].items():
        component_summary_data.append({
            'Component Name': comp_name,
            'Connected Bus': meta['connected_bus'],
            'Total Flow [MWh]': meta['total_flow'],
            'Max Flow [MW]': meta['max_flow'],
            'Data Columns': len(meta['data_columns'])
        })
    
    if component_summary_data:
        comp_summary_df = pd.DataFrame(component_summary_data)
        st.dataframe(comp_summary_df.style.format({
            'Total Flow [MWh]': '{:.0f}',
            'Max Flow [MW]': '{:.1f}'
        }))
    
    # Bus flow comparison
    if bus_dfs:
        st.subheader("Bus Flow Comparison")
        bus_totals = {bus: df.sum().sum() for bus, df in bus_dfs.items()}
        fig = px.pie(values=list(bus_totals.values()), names=list(bus_totals.keys()), 
                    title="Total Flow Distribution by Bus")
        st.plotly_chart(fig, use_container_width=True)
        

def create_simple_sankey(bus_dfs, component_bus_mapping):
    """Create a simplified Sankey diagram from bus data"""
    try:
        labels = []
        source = []
        target = []
        value = []
        
        # Track nodes
        node_indices = {}
        current_idx = 0
        
        # Collect all flows from bus DataFrames
        all_flows = []
        
        for bus_name, df in bus_dfs.items():
            # Add bus to nodes
            if bus_name not in node_indices:
                node_indices[bus_name] = current_idx
                labels.append(bus_name)
                current_idx += 1
            
            # Process each flow in this bus
            for column in df.columns:
                # Parse flow direction: "component -> bus" or "bus -> component"
                if ' -> ' in column:
                    parts = column.split(' -> ')
                    if len(parts) == 2:
                        from_node, to_node = parts
                        
                        # Add nodes if not exists
                        if from_node not in node_indices:
                            node_indices[from_node] = current_idx
                            labels.append(from_node)
                            current_idx += 1
                        
                        if to_node not in node_indices:
                            node_indices[to_node] = current_idx
                            labels.append(to_node)
                            current_idx += 1
                        
                        # Calculate total flow
                        total_flow = df[column].sum()
                        
                        if total_flow > 0:
                            source.append(node_indices[from_node])
                            target.append(node_indices[to_node])
                            value.append(total_flow)
        
        if source and target and value:
            fig = go.Figure(data=[go.Sankey(
                node=dict(
                    pad=15,
                    thickness=20,
                    line=dict(color="black", width=0.5),
                    label=labels
                ),
                link=dict(
                    source=source,
                    target=target,
                    value=value
                )
            )])
            
            fig.update_layout(
                title_text="Energy Flow Sankey Diagram",
                font_size=10,
                height=600
            )
            
            return fig
        else:
            return None
            
    except Exception as e:
        print(f"Error in simple Sankey: {e}")
        return None

def display_sankey_diagram(energysystem, results, bus_dfs, component_bus_mapping):
    """Display Sankey diagram in the dashboard"""
    st.header("🦍 System Sankey Diagram")
    
    # Create Sankey diagram
    sankey_fig = create_simple_sankey(bus_dfs, component_bus_mapping)
    
    if sankey_fig:
        st.plotly_chart(sankey_fig, use_container_width=True)
        
        # Add some statistics
        st.subheader("Flow Statistics")
        total_flow = sum(sankey_fig.data[0].link.value)
        num_flows = len(sankey_fig.data[0].link.value)
        num_nodes = len(sankey_fig.data[0].node.label)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Energy Flow", f"{total_flow:.0f} MWh")
        with col2:
            st.metric("Number of Flows", num_flows)
        with col3:
            st.metric("Number of Nodes", num_nodes)
    else:
        st.warning("Could not generate Sankey diagram with available data")
        
        # Alternative: Show system structure
        st.subheader("System Structure")
        for bus_name, df in bus_dfs.items():
            with st.expander(f"Bus: {bus_name}"):
                st.write(f"Connected flows: {len(df.columns)}")
                for flow in df.columns:
                    total_flow = df[flow].sum()
                    st.write(f"- {flow}: {total_flow:.1f} MWh")
            
def create_combined_bus_component_dfs(bus_sequences, component_sequences, energysystem):
    """Create combined DataFrames showing flows to/from each bus"""
    combined_dfs = {}
    
    for bus_name, components in bus_sequences.items():
        combined_data = {}
        
        # Add flows FROM bus TO components (outputs)
        for component_name, sequence_data in components.items():
            flow_values = extract_flow_values(sequence_data)
            if flow_values is not None:
                # Output from bus to component
                combined_data[f"OUT: {bus_name} → {component_name}"] = flow_values
        
        # Add flows FROM components TO bus (inputs)
        for component_name, targets in component_sequences.items():
            for target_name, sequence_data in targets.items():
                if str(target_name) == bus_name:
                    flow_values = extract_flow_values(sequence_data)
                    if flow_values is not None:
                        # Input from component to bus
                        combined_data[f"IN: {component_name} → {bus_name}"] = flow_values
        
        if combined_data:
            time_index = energysystem.timeindex
            min_length = min(len(arr) for arr in combined_data.values())
            
            if min_length != len(time_index):
                time_index = time_index[:min_length]

            for key in combined_data.keys():
                combined_data[key] = combined_data[key][:min_length]
            
            combined_dfs[bus_name] = pd.DataFrame(combined_data, index=time_index[:min_length])
    
    return combined_dfs

def extract_flow_values(sequence_data):
    """Helper function to extract flow values from sequence data"""
    if hasattr(sequence_data, 'values'):
        flow_values = sequence_data.values
    elif isinstance(sequence_data, dict):
        flow_data = sequence_data.get('flow', None)
        if flow_data is not None and hasattr(flow_data, 'values'):
            flow_values = flow_data.values
        else:
            return None
    else:
        return None
    
    # Ensure we have a 1D array
    if hasattr(flow_values, 'shape'):
        if len(flow_values.shape) == 1:
            return flow_values
        elif len(flow_values.shape) == 2:
            return flow_values[:, 0]
        else:
            try:
                return flow_values.flatten()
            except:
                return None
    return None

def display_combined_bus_component_analysis(combined_dfs, metadata=None):
    """Display combined bus and component analysis with stacked plots only"""
    st.header("Flow Analysis")
    
    if not combined_dfs:
        st.warning("No combined flow data available")
        return
    
    # Bus selection
    selected_bus = st.selectbox("Select Bus", list(combined_dfs.keys()), 
                                key="combined_bus_select")
    
    if selected_bus:
        df = combined_dfs[selected_bus]
        
        # Create summary metrics
        col1, col2, col3, col4 = st.columns(4)
        
        # Separate IN and OUT flows
        in_flows = [col for col in df.columns if col.startswith("IN:")]
        out_flows = [col for col in df.columns if col.startswith("OUT:")]
        
        with col1:
            total_in = df[in_flows].sum().sum()
            st.metric("Total Inflows", f"{total_in:,.0f} MWh")
            st.metric("Avg Inflow", f"{total_in/len(df):.1f} MW")
        
        with col2:
            total_out = df[out_flows].sum().sum()
            st.metric("Total Outflows", f"{total_out:,.0f} MWh")
            st.metric("Avg Outflow", f"{total_out/len(df):.1f} MW")
        
        with col3:
            net_flow = total_in - total_out
            st.metric("Net Flow", f"{net_flow:,.0f} MWh")
            st.metric("Peak Inflow", f"{df[in_flows].max().max():.1f} MW")
        
        with col4:
            balance_error = abs(net_flow) / max(total_in + total_out, 1) * 100
            st.metric("Balance Error", f"{balance_error:.2f}%")
            st.metric("Peak Outflow", f"{df[out_flows].max().max():.1f} MW")
        
        # Controls
        col5, col6 = st.columns(2)
        
        with col5:
            # Date range selection
            min_date = df.index.min()
            max_date = df.index.max()
            date_range = st.date_input(
                "Select date range:",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
                key="combined_date_range"
            )
        
        with col6:
            # Time resolution
            resolution = st.selectbox("Time Resolution", 
                                     ["Hourly", "Daily", "Weekly", "Monthly"],
                                     index=1,  # Default to Daily
                                     key="combined_resolution")
        
        # Filter data by date range
        if len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = df.loc[start_date:end_date]
        else:
            filtered_df = df
        
        # Apply resolution
        if resolution == "Hourly":
            display_df = filtered_df
        elif resolution == "Daily":
            display_df = filtered_df.resample('D').sum()
        elif resolution == "Weekly":
            display_df = filtered_df.resample('W').sum()
        elif resolution == "Monthly":
            display_df = filtered_df.resample('M').sum()
        
        # Get all flows (automatically include all)
        selected_in_flows = in_flows
        selected_out_flows = out_flows
        
        # Create color palettes
        if selected_in_flows:
            in_colors = px.colors.qualitative.Set3[:len(selected_in_flows)]
            if len(selected_in_flows) > len(in_colors):
                in_colors = px.colors.qualitative.Alphabet[:len(selected_in_flows)]
        
        if selected_out_flows:
            out_colors = px.colors.qualitative.Set2[:len(selected_out_flows)]
            if len(selected_out_flows) > len(out_colors):
                out_colors = px.colors.qualitative.Dark24[:len(selected_out_flows)]
        
        # Create stacked subplots
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=(f"Input Flows to {selected_bus} Bus", 
                          f"Output Flows from {selected_bus} Bus"),
            vertical_spacing=0.12,
            shared_xaxes=True
        )
        
        # Stack IN flows (top plot)
        if selected_in_flows:
            for i, flow_col in enumerate(selected_in_flows):
                if flow_col in display_df.columns:
                    # Clean flow name for legend
                    flow_name = flow_col.replace("IN: ", "")
                    fig.add_trace(
                        go.Scatter(
                            x=display_df.index,
                            y=display_df[flow_col],
                            name=flow_name,
                            stackgroup='in',
                            mode='none',
                            fillcolor=in_colors[i % len(in_colors)],
                            opacity=0.8,
                            hoverinfo='x+y+name',
                            hoverlabel=dict(namelength=-1)
                        ),
                        row=1, col=1
                    )
        
        # Stack OUT flows (bottom plot)
        if selected_out_flows:
            for i, flow_col in enumerate(selected_out_flows):
                if flow_col in display_df.columns:
                    # Clean flow name for legend
                    flow_name = flow_col.replace("OUT: ", "")
                    fig.add_trace(
                        go.Scatter(
                            x=display_df.index,
                            y=display_df[flow_col],
                            name=flow_name,
                            stackgroup='out',
                            mode='none',
                            fillcolor=out_colors[i % len(out_colors)],
                            opacity=0.8,
                            hoverinfo='x+y+name',
                            hoverlabel=dict(namelength=-1)
                        ),
                        row=2, col=1
                    )
        
        # Add total flow lines on top of stacks
        if selected_in_flows and len(selected_in_flows) > 0:
            total_in_series = display_df[selected_in_flows].sum(axis=1)
            fig.add_trace(
                go.Scatter(
                    x=display_df.index,
                    y=total_in_series,
                    name="Total Input",
                    line=dict(color='black', width=2, dash='dash'),
                    mode='lines',
                    showlegend=True
                ),
                row=1, col=1
            )
        
        if selected_out_flows and len(selected_out_flows) > 0:
            total_out_series = display_df[selected_out_flows].sum(axis=1)
            fig.add_trace(
                go.Scatter(
                    x=display_df.index,
                    y=total_out_series,
                    name="Total Output",
                    line=dict(color='black', width=2, dash='dash'),
                    mode='lines',
                    showlegend=True
                ),
                row=2, col=1
            )
        
        # Update layout
        fig.update_layout(
            height=700,
            title_text=f"Bus Flow Analysis: {selected_bus}",
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.25,
                xanchor="center",
                x=0.5,
                bgcolor="rgba(255, 255, 255, 0.8)",
                bordercolor="lightgray",
                borderwidth=1,
                font=dict(size=14)
            ),
            hovermode='x unified',
            plot_bgcolor='white'
        )
        
        # Update y-axes labels and grid
        fig.update_yaxes(title_text="Power (MW)", row=1, col=1, gridcolor='lightgray')
        fig.update_yaxes(title_text="Power (MW)", row=2, col=1, gridcolor='lightgray')
        
        # Update x-axis
        fig.update_xaxes(title_text="Time", row=2, col=1, gridcolor='lightgray')
        fig.update_xaxes(showticklabels=False, row=1, col=1, gridcolor='lightgray')
        
        st.plotly_chart(fig, use_container_width=True)
        
def display_detailed_flow_anlaysis(bus_dfs, component_dfs, storage_dfs, metadata):
    st.header("📊 Detailed Flow Analysis")
    
    tab_bus, tab_component, tab_storage = st.tabs([
        "🔌 Bus Analysis", 
        "⚙️ Component Analysis", 
        "🔋 Storage Analysis"
    ])
    
    with tab_bus:
        display_bus_analysis(bus_dfs, metadata)
    
    with tab_component:
        display_component_analysis(component_dfs, metadata)
    
    with tab_storage:
        display_storage_analysis(storage_dfs, metadata)