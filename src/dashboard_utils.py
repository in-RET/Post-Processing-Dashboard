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
                bus_data[f"{component_name} -> {bus_name}"] = flow_values
            else:
                # If it's 2D, take the first column or flatten
                try:
                    if hasattr(flow_values, 'shape') and len(flow_values.shape) == 2:
                        bus_data[f"{component_name} -> {bus_name}"] = flow_values[:, 0]
                    else:
                        bus_data[f"{component_name} -> {bus_name}"] = flow_values.flatten()
                except:
                    st.warning(f"Could not process data for {component_name} -> {bus_name}")
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

def extract_system_metadata(energysystem, bus_dfs, component_dfs, component_bus_mapping):
    """Extract comprehensive system metadata"""
    metadata = {
        'buses': {},
        'components': {},
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
    
    # System summary
    metadata['system_summary'] = {
        'total_buses': len(bus_dfs),
        'total_components': len(component_dfs),
        'total_data_points': len(energysystem.timeindex),
        'simulation_duration': f"{(energysystem.timeindex[-1] - energysystem.timeindex[0]).days} days"
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
                rows=2, cols=2,
                subplot_titles=('Time Series', 'Cumulative Flow', 'Daily Profile', 'Flow Distribution'),
                specs=[[{"secondary_y": False}, {"secondary_y": False}],
                       [{"secondary_y": False}, {"secondary_y": False}]]
            )
            
            # Time series
            for flow in selected_flows:
                fig.add_trace(
                    go.Scatter(x=display_df.index, y=display_df[flow], name=flow),
                    row=1, col=1
                )
            
            # Cumulative flow
            for flow in selected_flows:
                fig.add_trace(
                    go.Scatter(x=display_df.index, y=display_df[flow].cumsum(), 
                             name=f"{flow} (cumulative)", showlegend=False),
                    row=1, col=2
                )
            
            # Daily profile (if we have hourly data)
            if len(display_df) > 24:
                daily_profile = display_df[selected_flows].groupby(display_df.index.hour).mean()
                for flow in selected_flows:
                    fig.add_trace(
                        go.Scatter(x=daily_profile.index, y=daily_profile[flow], 
                                 name=f"{flow} (hourly avg)", showlegend=False),
                        row=2, col=1
                    )
            
            # Distribution
            for flow in selected_flows:
                fig.add_trace(
                    go.Box(y=display_df[flow], name=flow, showlegend=False),
                    row=2, col=2
                )
            
            fig.update_layout(height=800, title_text=f"Bus Analysis: {selected_bus}")
            st.plotly_chart(fig, use_container_width=True)
            
            # Summary statistics
            st.subheader("Flow Statistics")
            st.dataframe(display_df[selected_flows].describe())
            
            # Download button
            csv = display_df[selected_flows].to_csv()
            st.download_button(
                label="Download Bus Data as CSV",
                data=csv,
                file_name=f"bus_{selected_bus}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv"
            )

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
        st.subheader("Flow Summary")
        st.dataframe(comp_df.describe())

def display_system_summary(bus_dfs, component_dfs, metadata):
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
        st.metric("Number of Components", metadata['system_summary']['total_components'])
    
    with col3:
        st.metric("Simulation Period", metadata['timeframe']['start'].strftime('%Y-%m-%d'))
        st.metric("Data Points", metadata['system_summary']['total_data_points'])
    
    with col4:
        st.metric("Time Resolution", f"{metadata['timeframe']['periods']} periods")
        st.metric("Duration", metadata['system_summary']['simulation_duration'])
    
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
    st.header("🔄 System Sankey Diagram")
    
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
            