# -*- coding: utf-8 -*-
"""
Created on Tue Oct 28 14:00:48 2025

@author: rbala
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

def get_component_type(component_name):
    """Determine component type for color coding"""
    name_lower = component_name.lower()
    
    # Solar components
    if any(keyword in name_lower for keyword in ['solar', 'pv', 'photovoltaic']):
        return 'solar'
    # Wind components
    elif any(keyword in name_lower for keyword in ['wind', 'turbine']):
        return 'wind'
    # Storage components
    elif any(keyword in name_lower for keyword in ['storage', 'battery']):
        return 'storage'
    # Demand components
    elif any(keyword in name_lower for keyword in ['demand', 'load', 'consumption']):
        return 'demand'
    # Grid components
    elif any(keyword in name_lower for keyword in ['import', 'export', 'grid']):
        return 'grid'
    # Heat components
    elif any(keyword in name_lower for keyword in ['heat', 'thermal', 'boiler']):
        return 'heat'
    # Hydrogen components
    elif any(keyword in name_lower for keyword in ['hydrogen', 'h2', 'electrolyzer', 'fuel_cell']):
        return 'hydrogen'
    # Default
    else:
        return 'other'
    
def get_link_color(component_type, flow_direction):
    """Get color based on component type and flow direction"""
    # Color palette for different component types
    color_palette = {
        'solar': {'incoming': 'rgba(255, 215, 0, 0.7)',    'outgoing': 'rgba(255, 195, 0, 0.7)'},      # Gold/Yellow
        'wind': {'incoming': 'rgba(173, 216, 230, 0.7)',   'outgoing': 'rgba(143, 196, 220, 0.7)'},    # Light Blue
        'storage': {'incoming': 'rgba(147, 112, 219, 0.7)', 'outgoing': 'rgba(127, 92, 199, 0.7)'},     # Purple
        'demand': {'incoming': 'rgba(220, 20, 60, 0.7)',   'outgoing': 'rgba(200, 0, 40, 0.7)'},       # Red
        'grid': {'incoming': 'rgba(128, 128, 128, 0.7)',   'outgoing': 'rgba(108, 108, 108, 0.7)'},    # Gray
        'heat': {'incoming': 'rgba(255, 99, 71, 0.7)',     'outgoing': 'rgba(235, 79, 51, 0.7)'},      # Tomato Red
        'hydrogen': {'incoming': 'rgba(30, 144, 255, 0.7)', 'outgoing': 'rgba(10, 124, 235, 0.7)'},     # Dodger Blue
        'other': {'incoming': 'rgba(144, 238, 144, 0.7)',  'outgoing': 'rgba(124, 218, 124, 0.7)'}     # Light Green
    }
    
    return color_palette.get(component_type, color_palette['other'])[flow_direction]

def group_similar_components(component_dict):
    """Group components ending with _n, _s, _m, _e and sum their flows"""
    grouped_components = {}
    individual_components = {}
    
    for component_name, flow_value in component_dict.items():
        # Check if component name ends with _n, _s, _m, _e
        if component_name.endswith(('_n', '_s', '_m', '_e')):
            # Remove the last 2 characters to get base name
            base_name = component_name[:-2]
            
            # Add to grouped components
            if base_name in grouped_components:
                grouped_components[base_name] += flow_value
            else:
                grouped_components[base_name] = flow_value
        else:
            # Keep as individual component
            individual_components[component_name] = flow_value
    
    # Combine grouped and individual components
    combined = {**grouped_components, **individual_components}
    return dict(sorted(combined.items(), key=lambda x: x[1], reverse=True))

def get_component_group_name(component_name):
    if component_name.endswith(('_n', '_s', '_m', '_e')):
        return component_name[:-2]  # Remove last 2 characters
    else:
        return component_name  # Keep original name

def create_colored_sankey(bus_dfs, component_dfs, component_bus_mapping):
    """Create a Sankey diagram with colored links based on component types"""
    
    try:
        labels = []
        source = []
        target = []
        value = []
        link_colors = []
        link_labels = []
        
        # Track nodes with unified naming
        node_indices = {}
        current_idx = 0
        
        # Function to add node if not exists with unified naming
        def add_node(node_name):
            nonlocal current_idx
            unified_name = unify_bus_name(node_name)
            if unified_name not in node_indices:
                node_indices[unified_name] = current_idx
                labels.append(unified_name)
                current_idx += 1
            return node_indices[unified_name]
        
        def unify_bus_name(name):
            """Unify bus names to avoid duplicates"""
            name_lower = name.lower()
            bus_indicators = ['bus', 'node', 'grid', 'network', 'electricity', 'heat', 'hydrogen']
            for indicator in bus_indicators:
                if indicator in name_lower:
                    if ' -> ' in name:
                        parts = name.split(' -> ')
                        if len(parts) == 2:
                            for part in parts:
                                if any(ind in part.lower() for ind in bus_indicators):
                                    return part
                    return name
            return name
        
        
        
        
        # Identify all unique buses
        all_buses = set()
        all_buses.update(bus_dfs.keys())
        for component_name, df in component_dfs.items():
            for column in df.columns:
                if ' -> ' in column:
                    parts = column.split(' -> ')
                    if len(parts) == 2:
                        from_node, to_node = parts
                        if any(ind in from_node.lower() for ind in ['bus', 'node', 'grid']):
                            all_buses.add(from_node)
                        if any(ind in to_node.lower() for ind in ['bus', 'node', 'grid']):
                            all_buses.add(to_node)
        
        # Create unified bus mapping
        bus_unified_mapping = {}
        for bus in all_buses:
            unified_name = unify_bus_name(bus)
            bus_unified_mapping[bus] = unified_name
        
        # Add all unified bus nodes first
        for unified_bus in set(bus_unified_mapping.values()):
            add_node(unified_bus)
        
        # COMPONENT DataFrames (components → buses) - INCOMING FLOWS
        for component_name, df in component_dfs.items():
            add_node(component_name)
            
            for column in df.columns:
                if ' -> ' in column:
                    parts = column.split(' -> ')
                    if len(parts) == 2:
                        from_node, to_node = parts
                        if to_node == 'None':
                            continue
                        
                        unified_from_node = bus_unified_mapping.get(from_node, unify_bus_name(from_node))
                        unified_to_node = bus_unified_mapping.get(to_node, unify_bus_name(to_node))
                        
                        from_idx = add_node(unified_from_node)
                        to_idx = add_node(unified_to_node)
                        
                        total_flow = df[column].sum()
                        
                        if total_flow > 0:
                            # Component → Bus = INCOMING FLOW
                            source.append(from_idx)
                            target.append(to_idx)
                            value.append(total_flow)
                            
                            # Determine component type and get color
                            comp_type = get_component_type(component_name)
                            link_color = get_link_color(comp_type, 'incoming')
                            link_colors.append(link_color)
                            link_labels.append(f"{comp_type}_incoming")
        
        # PROCESS BUS DataFrames (buses → components) - OUTGOING FLOWS
        for bus_name, df in bus_dfs.items():
            unified_bus_name = bus_unified_mapping.get(bus_name, unify_bus_name(bus_name))
            
            for column in df.columns:
                if ' -> ' in column:
                    parts = column.split(' -> ')
                    if len(parts) == 2:
                        from_node, to_node = parts
                        
                        unified_from_node = bus_unified_mapping.get(from_node, unify_bus_name(from_node))
                        unified_to_node = bus_unified_mapping.get(to_node, unify_bus_name(to_node))
                        
                        from_idx = add_node(unified_from_node)
                        to_idx = add_node(unified_to_node)
                        
                        total_flow = df[column].sum()
                        
                        if total_flow > 0:
                            # Bus → Component = OUTGOING FLOW
                            source.append(from_idx)
                            target.append(to_idx)
                            value.append(total_flow)
                            
                            # Determine component type and get color
                            comp_type = get_component_type(to_node)
                            link_color = get_link_color(comp_type, 'outgoing')
                            link_colors.append(link_color)
                            link_labels.append(f"{comp_type}_outgoing")
        
        # Remove duplicate links
        link_dict = {}
        for i in range(len(source)):
            key = (source[i], target[i])
            if key in link_dict:
                link_dict[key]['value'] += value[i]
            else:
                link_dict[key] = {
                    'value': value[i],
                    'color': link_colors[i],
                    'label': link_labels[i]
                }
        
        # Rebuild the lists without duplicates
        source_combined = []
        target_combined = [] 
        value_combined = []
        link_colors_combined = []
        link_labels_combined = []
        
        for (s, t), data in link_dict.items():
            source_combined.append(s)
            target_combined.append(t)
            value_combined.append(data['value'])
            link_colors_combined.append(data['color'])
            link_labels_combined.append(data['label'])
       
                
        if source_combined and target_combined and value_combined:
            # Create node colors
            node_colors = []
            for label in labels:
                if any(keyword in label.lower() for keyword in ['bus', 'node', 'grid']):
                    node_colors.append('rgba(100, 149, 237, 0.8)')  # Blue for buses
                else:
                    # Color components based on type
                    comp_type = get_component_type(label)
                    type_colors = {
                        'solar': 'rgba(255, 215, 0, 0.8)',
                        'wind': 'rgba(173, 216, 230, 0.8)',
                        'storage': 'rgba(147, 112, 219, 0.8)',
                        'demand': 'rgba(220, 20, 60, 0.8)',
                        'grid': 'rgba(128, 128, 128, 0.8)',
                        'heat': 'rgba(255, 99, 71, 0.8)',
                        'hydrogen': 'rgba(30, 144, 255, 0.8)',
                        'other': 'rgba(144, 238, 144, 0.8)'
                    }
                    node_colors.append(type_colors.get(comp_type, 'rgba(144, 238, 144, 0.8)'))
            
            fig = go.Figure(data=[go.Sankey(
                node=dict(
                    pad=20,
                    thickness=25,
                    line=dict(color="black", width=1),
                    label=labels,
                    color=node_colors,
                    hovertemplate='<b>%{label}</b><extra></extra>'                    
                ),
                link=dict(
                    source=source_combined,
                    target=target_combined,
                    value=value_combined,
                    color=link_colors_combined,
                    hovertemplate='<b>%{source.label}</b> → <b>%{target.label}</b><br>Flow: %{value:.1f} MWh<extra></extra>'
                )
            )])
            
            fig.update_layout(
                title_text="Energy Flow Sankey Diagram",
                font=dict(
                            family="Arial, sans-serif",  
                            size=14,                     
                            color="black"                
                        ),
                height=800,
                margin=dict(t=100, l=50, r=50, b=50)
            )
            
            fig.update_layout(
                    font=dict(size=12),
                    height=900,
                )
                
            fig.update_traces(
                node=dict(pad=20, thickness=18),
                selector=dict(type="sankey")
            )
            return fig, labels, source_combined, target_combined, value_combined, link_colors_combined
        else:
            return None, [], [], [], [], []
            
    except Exception as e:
        print(f"Error in colored Sankey: {e}")
        return None, [], [], [], [], []


def create_colored_sankey_analysis(bus_dfs, component_dfs, component_bus_mapping):
    """Create detailed Sankey analysis with colored links"""
    try:
        # Create colored Sankey
        fig_comprehensive, labels, sources, targets, values, link_colors = create_colored_sankey(
            bus_dfs, component_dfs, component_bus_mapping
        )
        
        if fig_comprehensive is None:
            st.warning("No flow data available for Sankey diagram")
            return None
        
        # Display the main Sankey diagram
        st.plotly_chart(fig_comprehensive, use_container_width=True)
        
        # Display color legend
        st.subheader("🎨 Color Legend")
        
        legend_colors = {
            'Solar': 'rgba(255, 215, 0, 0.7)',
            'Wind': 'rgba(173, 216, 230, 0.7)',
            'Storage': 'rgba(147, 112, 219, 0.7)',
            'Demand': 'rgba(220, 20, 60, 0.7)',
            'Grid': 'rgba(128, 128, 128, 0.7)',
            'Heat': 'rgba(255, 99, 71, 0.7)',
            'Hydrogen': 'rgba(30, 144, 255, 0.7)',
            'Other': 'rgba(144, 238, 144, 0.7)',
            'Buses': 'rgba(100, 149, 237, 0.8)'
        }
        
        cols = st.columns(4)
        for i, (label, color) in enumerate(legend_colors.items()):
            with cols[i % 4]:
                st.markdown(f"""
                <div style="display: flex; align-items: center; margin: 5px 0;">
                    <div style="width: 20px; height: 20px; background-color: {color}; 
                         border: 1px solid #000; margin-right: 8px; border-radius: 3px;"></div>
                    <span>{label}</span>
                </div>
                """, unsafe_allow_html=True)
        
        # Flow statistics by component type
        st.subheader("📊 Flow Statistics by Component Type")
        
        # Calculate flows by component type
        type_flows = {}
        for i in range(len(sources)):
            source_label = labels[sources[i]]
            target_label = labels[targets[i]]
            flow_value = values[i]
            
            # Determine which node is the component
            if any(keyword in source_label.lower() for keyword in ['bus', 'node', 'grid']):
                # Target is component (outgoing flow)
                comp_type = get_component_type(target_label)
                direction = 'outgoing'
            else:
                # Source is component (incoming flow)
                comp_type = get_component_type(source_label)
                direction = 'incoming'
            
            if comp_type not in type_flows:
                type_flows[comp_type] = {'incoming': 0, 'outgoing': 0, 'total': 0}
            
            type_flows[comp_type][direction] += flow_value
            type_flows[comp_type]['total'] += flow_value
        
        # Display type statistics
        if type_flows:
            type_cols = st.columns(3)
            type_data = []
            for comp_type, flows in type_flows.items():
                type_data.append({
                    'Type': comp_type.title(),
                    'Incoming (MWh)': flows['incoming'],
                    'Outgoing (MWh)': flows['outgoing'],
                    'Total (MWh)': flows['total']
                })
            
            type_df = pd.DataFrame(type_data)
            type_df = type_df.sort_values('Total (MWh)', ascending=False)
            
            # Color the dataframe based on component type
            def color_type_row(row):
                color_map = {
                    'Solar': 'background-color: rgba(255, 215, 0, 0.2)',
                    'Wind': 'background-color: rgba(173, 216, 230, 0.2)',
                    'Storage': 'background-color: rgba(147, 112, 219, 0.2)',
                    'Fossil': 'background-color: rgba(139, 69, 19, 0.2); color: white',
                    'Demand': 'background-color: rgba(220, 20, 60, 0.2)',
                    'Grid': 'background-color: rgba(128, 128, 128, 0.2)',
                    'Heat': 'background-color: rgba(255, 99, 71, 0.2)',
                    'Hydrogen': 'background-color: rgba(30, 144, 255, 0.2)',
                    'Other': 'background-color: rgba(144, 238, 144, 0.2)'
                }
                return [color_map.get(row['Type'], '')] * len(row)
            
            styled_df = type_df.style.apply(color_type_row, axis=1)
            st.dataframe(styled_df, use_container_width=True)
        
        return fig_comprehensive
        
    except Exception as e:
        st.error(f"Error in colored Sankey analysis: {e}")
        return None

def create_grouped_sankey(bus_dfs, component_dfs, component_bus_mapping):
    """Create a Sankey diagram with grouped similar components"""
    
    try:
        labels = []
        source = []
        target = []
        value = []
        link_colors = []
        
        # Track nodes
        node_indices = {}
        current_idx = 0
        
        def add_node(node_name):
            nonlocal current_idx
            grouped_name = get_component_group_name(node_name)
            if grouped_name not in node_indices:
                node_indices[grouped_name] = current_idx
                labels.append(grouped_name)
                current_idx += 1
            return node_indices[grouped_name]
        
        # First pass: Collect all individual flows
        individual_flows = []
        
        # Process COMPONENT DataFrames (components → buses) - INCOMING FLOWS
        for component_name, df in component_dfs.items():
            for column in df.columns:
                if ' -> ' in column:
                    parts = column.split(' -> ')
                    if len(parts) == 2:
                        from_node, to_node = parts
                        if to_node == 'None':
                            continue
                        
                        total_flow = df[column].sum()
                        if total_flow > 0:
                            individual_flows.append({
                                'type': 'incoming',
                                'from_node': from_node,
                                'to_node': to_node,
                                'flow': total_flow,
                                'component_type': get_component_type(from_node)
                            })
        
        # Process BUS DataFrames (buses → components) - OUTGOING FLOWS
        for bus_name, df in bus_dfs.items():
            for column in df.columns:
                if ' -> ' in column:
                    parts = column.split(' -> ')
                    if len(parts) == 2:
                        from_node, to_node = parts
                        
                        total_flow = df[column].sum()
                        if total_flow > 0:
                            individual_flows.append({
                                'type': 'outgoing',
                                'from_node': from_node,
                                'to_node': to_node,
                                'flow': total_flow,
                                'component_type': get_component_type(to_node)
                            })
        
        # Group flows by simple naming convention for both components and buses
        grouped_flows = {}
        
        for flow in individual_flows:
            # Apply grouping to both from_node and to_node
            grouped_from = get_component_group_name(flow['from_node'])
            grouped_to = get_component_group_name(flow['to_node'])
            
            if flow['type'] == 'incoming':
                # Component → Bus flow
                key = (grouped_from, grouped_to, 'incoming', flow['component_type'])
            else:
                # Bus → Component flow
                key = (grouped_from, grouped_to, 'outgoing', flow['component_type'])
            
            if key in grouped_flows:
                grouped_flows[key] += flow['flow']
            else:
                grouped_flows[key] = flow['flow']
        
        # Add all nodes first (both buses and components, already grouped)
        all_nodes = set()
        for (from_node, to_node, flow_type, comp_type) in grouped_flows.keys():
            all_nodes.add(from_node)
            all_nodes.add(to_node)
        
        for node in all_nodes:
            add_node(node)
        
        # Create links from grouped flows
        for (from_node, to_node, flow_type, comp_type), flow_value in grouped_flows.items():
            if flow_value > 0:
                from_idx = add_node(from_node)
                to_idx = add_node(to_node)
                
                source.append(from_idx)
                target.append(to_idx)
                value.append(flow_value)
                
                # Get color based on component type and flow direction
                link_color = get_link_color(comp_type, flow_type)
                link_colors.append(link_color)
        
        if source and target and value:
            # Create node colors - identify buses vs components
            node_colors = []
            for label in labels:
                # Check if it's a bus (contains bus keywords OR was grouped from bus names)
                is_bus = (any(keyword in label.lower() for keyword in ['bus', 'node', 'grid']) or
                         any(original_bus.endswith(('_n', '_s', '_m', '_e')) and 
                             original_bus[:-2] == label for original_bus in bus_dfs.keys()))
                
                if is_bus:
                    node_colors.append('rgba(100, 149, 237, 0.8)')  # Blue for buses
                else:
                    # Color components based on type
                    comp_type = get_component_type(label)
                    type_colors = {
                        'solar': 'rgba(255, 215, 0, 0.8)',
                        'wind': 'rgba(173, 216, 230, 0.8)',
                        'storage': 'rgba(147, 112, 219, 0.8)',
                        'fossil': 'rgba(139, 69, 19, 0.8)',
                        'demand': 'rgba(220, 20, 60, 0.8)',
                        'grid': 'rgba(128, 128, 128, 0.8)',
                        'heat': 'rgba(255, 99, 71, 0.8)',
                        'hydrogen': 'rgba(30, 144, 255, 0.8)',
                        'other': 'rgba(144, 238, 144, 0.8)'
                    }
                    node_colors.append(type_colors.get(comp_type, 'rgba(144, 238, 144, 0.8)'))
            
            fig = go.Figure(data=[go.Sankey(
                node=dict(
                    pad=20,
                    thickness=25,
                    line=dict(color="black", width=1),
                    label=labels,
                    color=node_colors,
                    hovertemplate='<b>%{label}</b><extra></extra>'
                ),
                link=dict(
                    source=source,
                    target=target,
                    value=value,
                    color=link_colors,
                    hovertemplate='<b>%{source.label}</b> → <b>%{target.label}</b><br>Flow: %{value:.1f} MWh<extra></extra>'
                )
            )])
            
            fig.update_layout(
                title_text="Grouped Energy Flow Sankey Diagram",
                font=dict(
                            family="Arial, sans-serif",  
                            size=14,                     
                            color="black"                
                        ),
                height=800,
                margin=dict(t=100, l=50, r=50, b=50)
            )
            
            return fig, labels, source, target, value, link_colors
        else:
            return None, [], [], [], [], []
            
    except Exception as e:
        print(f"Error in unified grouped Sankey: {e}")
        return None, [], [], [], [], []

def create_grouped_sankey_analysis(bus_dfs, component_dfs, component_bus_mapping):
    """Create Sankey analysis with grouped components"""
    try:
        # Create unified grouped Sankey
        fig_comprehensive, labels, sources, targets, values, link_colors = create_grouped_sankey(
            bus_dfs, component_dfs, component_bus_mapping
        )
        
        if fig_comprehensive is None:
            st.warning("No flow data available for Sankey diagram")
            return None
        
        # Display the unified grouped Sankey diagram
        st.plotly_chart(fig_comprehensive, use_container_width=True)
        
        # Show unified grouping information
        st.subheader("Grouping Information")
        
        # Collect grouping examples for both components and buses
        grouped_components = {}
        grouped_buses = {}
        individual_components = []
        individual_buses = []
        
        # Check all component names
        all_components = set()
        for component_name in component_dfs.keys():
            all_components.add(component_name)
        
        # Check all bus names
        all_buses = set(bus_dfs.keys())
        
        # From bus DataFrames (components in flow descriptions)
        for bus_name, df in bus_dfs.items():
            for column in df.columns:
                if ' -> ' in column:
                    parts = column.split(' -> ')
                    if len(parts) == 2:
                        from_node, to_node = parts
                        if not any(keyword in from_node.lower() for keyword in ['bus', 'node', 'grid']):
                            all_components.add(from_node)
        
        # Analyze grouping for components
        for component in all_components:
            if component.endswith(('_n', '_s', '_m', '_e')):
                base_name = component[:-2]
                if base_name not in grouped_components:
                    grouped_components[base_name] = []
                grouped_components[base_name].append(component)
            else:
                individual_components.append(component)
        
        # Analyze grouping for buses
        for bus in all_buses:
            if bus.endswith(('_n', '_s', '_m', '_e')):
                base_name = bus[:-2]
                if base_name not in grouped_buses:
                    grouped_buses[base_name] = []
                grouped_buses[base_name].append(bus)
            else:
                individual_buses.append(bus)
        
        # Display grouping information
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**📊 Grouping Summary:**")
            total_nodes_before = len(all_components) + len(all_buses)
            total_nodes_after = (len(grouped_components) + len(individual_components) + 
                               len(grouped_buses) + len(individual_buses))
            reduction = ((total_nodes_before - total_nodes_after) / total_nodes_before) * 100
            
            st.metric("Total Nodes Before", total_nodes_before)
            st.metric("After Grouping", total_nodes_after)
            st.metric("Reduction", f"{reduction:.1f}%")
            
            st.write("**Components:**")
            st.write(f"- Individual: {len(individual_components)}")
            st.write(f"- Grouped: {len(grouped_components)}")
            
            st.write("**Buses:**")
            st.write(f"- Individual: {len(individual_buses)}")
            st.write(f"- Grouped: {len(grouped_buses)}")
        
        with col2:
            st.write("**Grouping Rule:**")
            st.write("Both **components** and **buses** ending with:")
            st.write("• **\\_n**, **\\_s**, **\\_m**, **\\_e**")
            st.write("are grouped together")
            
            if grouped_components:
                st.write("**Component Examples:**")
                for base_name, components in list(grouped_components.items())[:2]:
                    st.write(f"• **{base_name}**: {', '.join(components)}")
            
            if grouped_buses:
                st.write("**Bus Examples:**")
                for base_name, buses in list(grouped_buses.items())[:2]:
                    st.write(f"• **{base_name}**: {', '.join(buses)}")
        
        # Show all groups in expandable sections
        if grouped_components:
            with st.expander("📋 View All Grouped Components"):
                for base_name, components in sorted(grouped_components.items()):
                    st.write(f"**{base_name}** ← {', '.join(sorted(components))}")
        
        if grouped_buses:
            with st.expander("📋 View All Grouped Buses"):
                for base_name, buses in sorted(grouped_buses.items()):
                    st.write(f"**{base_name}** ← {', '.join(sorted(buses))}")
        
        return fig_comprehensive
        
    except Exception as e:
        st.error(f"Error in unified grouped Sankey analysis: {e}")
        return None

def display_colored_sankey_diagram(energysystem, results, bus_dfs, component_dfs, component_bus_mapping):
    
    st.header("Energy Flow Sankey")
    
    tab1, tab2= st.tabs(["Grouped Sankey", "Detailed Sankey"])
    
    with tab1:
        st.markdown("""
        <div style="background-color: #f0f8ff; padding: 15px; border-radius: 10px; border-left: 5px solid #4CAF50;">
        <h4 style="margin: 0; color: #2E7D32;">🎯 Grouped Sankey View</h4>
        <p style="margin: 5px 0; font-size: 0.9rem;">
        <style>.js-plotly-plot text {text-shadow: none !important;stroke: none !important;}</style>
        Similar components (e.g., PV_open_n, PV_open_s, PV_open_m) are automatically grouped together for cleaner visualization.
        </p>
        </div>
        """, unsafe_allow_html=True)
        
        # Display grouped Sankey diagram
        fig_grouped = create_grouped_sankey_analysis(bus_dfs, component_dfs, component_bus_mapping)
    
    with tab2:
        st.markdown("""
        <div style="background-color: #fff3cd; padding: 15px; border-radius: 10px; border-left: 5px solid #ffc107;">
        <h4 style="margin: 0; color: #856404;">🔍 Detailed Sankey View</h4>
        <p style="margin: 5px 0; font-size: 0.9rem;">
        <style>.js-plotly-plot text {text-shadow: none !important;stroke: none !important;}</style>
        Shows all individual components without grouping. Use this view for detailed analysis of specific components.
        </p>
        </div>
        """, unsafe_allow_html=True)
        
        # Display detailed (ungrouped) Sankey diagram
        fig_detailed = create_colored_sankey_analysis(bus_dfs, component_dfs, component_bus_mapping)
        
    # Create colored Sankey analysis
    #fig = create_colored_sankey_analysis(bus_dfs, component_dfs, component_bus_mapping)