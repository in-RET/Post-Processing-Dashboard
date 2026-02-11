# -*- coding: utf-8 -*-
"""
Created on Wed Oct 29 13:31:48 2025

@author: rbala
"""

import networkx as nx
import plotly.graph_objects as go
from oemof import solph
import streamlit as st
import pandas as pd

def create_interactive_network_diagram(energysystem, bus_dfs, component_dfs, component_bus_mapping):
    """Create an interactive network diagram with labels and enhanced features"""
    try:
        G = nx.DiGraph()
        
        for node in energysystem.nodes:
            node_label = str(node.label)
            
            if isinstance(node, solph.components.Source):
                G.add_node(node_label, 
                          type='source',
                          color='yellow',
                          symbol='triangle-up',
                          size=25,
                          original_class='Source')
                
            elif isinstance(node, solph.components.Sink):
                G.add_node(node_label, 
                          type='sink',
                          color='green',
                          symbol='triangle-down',
                          size=25,
                          original_class='Sink')
                
            elif isinstance(node, (solph.components.Converter, solph.components.GenericCHP)):
                G.add_node(node_label, 
                          type='converter',
                          color='gray',
                          symbol='square',
                          size=25,
                          original_class=type(node).__name__)
                
            elif isinstance(node, solph.buses.Bus):
                G.add_node(node_label, 
                          type='bus',
                          color='red',
                          symbol='diamond-tall',
                          size=30,
                          original_class='Bus')
                
            elif isinstance(node, solph.components.GenericStorage):
                G.add_node(node_label, 
                          type='storage',
                          color='black',
                          symbol='bowtie',
                          size=25,
                          original_class='GenericStorage')
                
            else:
                G.add_node(node_label, 
                          type='other',
                          color='lightblue',
                          symbol='pentagon',
                          size=20,
                          original_class=type(node).__name__)
        
        # Add edges based on component_bus_mapping
        for component_name, bus_name in component_bus_mapping.items():
            if bus_name != 'None' and component_name in G.nodes and bus_name in G.nodes:
                G.add_edge(component_name, bus_name, type='mapping', weight=1, label='Mapping')
        
        # Add edges from bus DataFrames
        for bus_name, df in bus_dfs.items():
            if bus_name in G.nodes:
                for column in df.columns:
                    if ' -> ' in column:
                        parts = column.split(' -> ')
                        if len(parts) == 2:
                            from_node, to_node = parts
                            if from_node in G.nodes and to_node in G.nodes:
                                avg_flow = df[column].mean()
                                total_flow = df[column].sum()
                                G.add_edge(from_node, to_node, type='flow', weight=avg_flow, 
                                          total_flow=total_flow, label=f'Flow: {avg_flow:.1f} MW')
        
        # Add edges from component DataFrames
        for component_name, df in component_dfs.items():
            if component_name in G.nodes:
                for column in df.columns:
                    if ' -> ' in column:
                        parts = column.split(' -> ')
                        if len(parts) == 2:
                            from_node, to_node = parts
                            if to_node != 'None' and from_node in G.nodes and to_node in G.nodes:
                                avg_flow = df[column].mean()
                                total_flow = df[column].sum()
                                G.add_edge(from_node, to_node, type='flow', weight=avg_flow,
                                          total_flow=total_flow, label=f'Flow: {avg_flow:.1f} MW')
        
        # Create layout with better spacing
        pos = nx.spring_layout(G, k=3, iterations=100, seed=42)
        
        # Store the complete graph and positions for later use
        st.session_state.network_graph = G
        st.session_state.network_positions = pos
        
        return create_network_figure(G, pos, selected_node=None)
        
    except Exception as e:
        st.error(f"Error creating interactive network diagram: {e}")
        import traceback
        st.error(f"Detailed error: {traceback.format_exc()}")
        return None, None

def create_network_figure(G, pos, selected_node=None):
    """Create network figure with optional node selection filtering"""
    
    # If a node is selected, find all connected nodes
    if selected_node and selected_node in G.nodes:
        # Get all nodes connected to the selected node (both predecessors and successors)
        connected_nodes = set()
        connected_nodes.add(selected_node)
        
        # Add all predecessors (nodes that connect TO the selected node)
        for pred in G.predecessors(selected_node):
            connected_nodes.add(pred)
        
        # Add all successors (nodes that the selected node connects TO)
        for succ in G.successors(selected_node):
            connected_nodes.add(succ)
        
        # Also include nodes that are connected through the same bus
        for node in list(connected_nodes):
            if G.nodes[node].get('type') == 'bus':
                # For bus nodes, include all their connections
                for pred in G.predecessors(node):
                    connected_nodes.add(pred)
                for succ in G.successors(node):
                    connected_nodes.add(succ)
    else:
        # Show all nodes if no selection
        connected_nodes = set(G.nodes)
    
    # Extract node positions and properties for visible nodes only
    node_x, node_y, node_colors, node_symbols, node_sizes, node_text, node_labels = [], [], [], [], [], [], []
    
    for node in G.nodes():
        if node not in connected_nodes:
            continue
            
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        
        node_data = G.nodes[node]
        
        # Highlight selected node
        if node == selected_node:
            node_colors.append('blue')  # Highlight color for selected node
            node_sizes.append(node_data['size'] * 1.5)  # Make selected node larger
        else:
            node_colors.append(node_data['color'])
            node_sizes.append(node_data['size'])
            
        node_symbols.append(node_data['symbol'])
        node_labels.append(node)  # Store label for display
        
        # Create detailed hover text
        degree = G.degree(node)
        node_type = node_data.get('type', 'unknown')
        original_class = node_data.get('original_class', 'unknown')
        
        # Count incoming and outgoing edges
        in_degree = G.in_degree(node)
        out_degree = G.out_degree(node)
        
        hover_text = f"""
        <b>🔧 {node}</b><br>
        📊 Type: {node_type.title()}<br>
        🏷️ Class: {original_class}<br>
        📥 Incoming: {in_degree} connections<br>
        📤 Outgoing: {out_degree} connections<br>
        🔗 Total: {degree} connections
        """
        if node == selected_node:
            hover_text += "<br><b>🎯 SELECTED NODE</b>"
        node_text.append(hover_text)
    
    # Create separate traces for different edge types - only show edges between visible nodes
    flow_edges_x, flow_edges_y, flow_edges_text = [], [], []
    mapping_edges_x, mapping_edges_y, mapping_edges_text = [], [], []
    
    for edge in G.edges(data=True):
        source, target, data = edge
        
        # Only show edges where both source and target are visible
        if source not in connected_nodes or target not in connected_nodes:
            continue
            
        x0, y0 = pos[source]
        x1, y1 = pos[target]
        
        # Edge hover text
        edge_type = data.get('type', 'connection')
        weight = data.get('weight', 0)
        total_flow = data.get('total_flow', 0)
        
        edge_text = f"""
        <b>🔗 Connection: {source} → {target}</b><br>
        📋 Type: {edge_type.title()}<br>
        📊 Average Flow: {weight:.1f} MW<br>
        📈 Total Energy: {total_flow:.1f} MWh<br>
        🎯 {data.get('label', 'Connection')}
        """
        
        if data.get('type') == 'mapping':
            mapping_edges_x.extend([x0, x1, None])
            mapping_edges_y.extend([y0, y1, None])
            mapping_edges_text.append(edge_text)
        else:
            flow_edges_x.extend([x0, x1, None])
            flow_edges_y.extend([y0, y1, None])
            flow_edges_text.append(edge_text)
    
    # Create edge traces with single colors
    mapping_edge_trace = go.Scatter(
        x=mapping_edges_x, y=mapping_edges_y,
        line=dict(width=2, color='#888888'),
        hoverinfo='text',
        text=mapping_edges_text,
        mode='lines',
        name='Structural Connections',
        showlegend=True
    )
    
    flow_edge_trace = go.Scatter(
        x=flow_edges_x, y=flow_edges_y,
        line=dict(width=2, color='#2E8B57'),
        hoverinfo='text',
        text=flow_edges_text,
        mode='lines',
        name='Energy Flow',
        showlegend=True
    )
    
    # Create node trace with labels
    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        hoverinfo='text',
        text=node_labels,  # Use node names as labels (not hover text)
        marker=dict(
            size=node_sizes,
            color=node_colors,
            symbol=node_symbols,
            line=dict(width=2, color='darkgray')
        ),
        textposition='middle center',
        textfont=dict(
            size=10,
            color='black',
            family='Arial, bold'
        ),
        showlegend=False
    )
    
    # Create title based on selection
    if selected_node:
        title = f'<b>Interactive Energy System Network</b><br><sub>Showing connections for: <b>{selected_node}</b>'
    else:
        title = '<b>Interactive Energy System Network</b>>'
    
    # Create the figure with all traces
    fig = go.Figure(data=[mapping_edge_trace, flow_edge_trace, node_trace],
                   layout=go.Layout(
                       title=title,
                       titlefont_size=16,
                       showlegend=True,
                       legend=dict(
                           orientation="h",
                           yanchor="bottom",
                           y=1.02,
                           xanchor="right",
                           x=1
                       ),
                       hovermode='closest',
                       margin=dict(b=20,l=5,r=5,t=60),
                       annotations=[dict(
                           text="• 🖱️ Drag to move • 🔍 Scroll to zoom",
                           showarrow=False,
                           xref="paper", yref="paper",
                           x=0.005, y=-0.002,
                           xanchor='left', yanchor='bottom',
                           font=dict(color='gray', size=10)
                       )],
                       xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                       yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                       height=700,
                       dragmode='pan',
                       hoverdistance=1
                   ))
    
    return fig

def display_interactive_network_analysis(energysystem, bus_dfs, component_dfs, component_bus_mapping):
    """Display interactive network analysis with controls"""
    
    st.header("🌐 Interactive Network Diagram")
    
    # Add interactive controls
    col1, col2 = st.columns(2)
    
    with col1:
        show_node_labels = st.checkbox("Show Node Labels", value=True, help="Display node names on the diagram")
    
    with col2:
        show_legend = st.checkbox("Show Legend", value=True, help="Display connection type legend")
    
    # Node selection for filtering
    if 'network_graph' in st.session_state:
        node_options = ["Show all nodes"] + list(st.session_state.network_graph.nodes())
        selected_node_filter = st.selectbox(
            "Filter by node:", 
            node_options,
            help="Select a node to see only its connections, or 'Show all nodes' to see everything"
        )
        
        if selected_node_filter == "Show all nodes":
            selected_node = None
        else:
            selected_node = selected_node_filter
    else:
        selected_node = None
    
    # Create the network diagram
    with st.spinner("Creating interactive network visualization..."):
       create_interactive_network_diagram(
        energysystem, bus_dfs, component_dfs, component_bus_mapping
    )

       graph = st.session_state.network_graph
       pos = st.session_state.network_positions
    
       fig = create_network_figure(graph, pos, selected_node)
    
    if fig is None:
        st.warning("Could not create network diagram. Please check your data.")
        return
    
    # Display the interactive network diagram
    st.plotly_chart(fig, use_container_width=True, config={
        'displayModeBar': True,
        'modeBarButtonsToAdd': ['pan2d', 'zoom2d', 'resetScale2d'],
        'scrollZoom': True,
        'displaylogo': False
    })
    
    # Add click functionality description
    st.info("💡 **Tip**: Select a node from the dropdown above to see only its direct connections. The selected node will be highlighted in blue and made larger.")
    
    # Interactive statistics section
    if graph:
        display_interactive_statistics(graph, selected_node)
    
    # Enhanced legend with interactivity
    if show_legend:
        display_interactive_legend()

def display_interactive_statistics(graph, selected_node=None):
    """Display interactive network statistics"""
    
    st.subheader("📊 Interactive Network Analysis")
    
    # Node selection for detailed view
    st.write("**🔍 Select a node for detailed analysis:**")
    
    node_options = list(graph.nodes())
    detailed_node = st.selectbox("Choose a node:", node_options, key="detailed_node")
    
    if detailed_node:
        display_node_details(graph, detailed_node)
    
    # Overall statistics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Nodes", len(graph.nodes()))
    
    with col2:
        st.metric("Total Connections", len(graph.edges()))
    
    with col3:
        bus_nodes = [n for n in graph.nodes() if graph.nodes[n].get('type') == 'bus']
        st.metric("Bus Nodes", len(bus_nodes))
    
    with col4:
        component_nodes = len(graph.nodes()) - len(bus_nodes)
        st.metric("Component Nodes", component_nodes)
    
    # Show connection information for selected node
    if selected_node and selected_node in graph.nodes:
        st.subheader(f"🔗 Connections for: {selected_node}")
        
        connected_nodes = set()
        connected_nodes.add(selected_node)
        
        # Get all connected nodes
        for pred in graph.predecessors(selected_node):
            connected_nodes.add(pred)
        for succ in graph.successors(selected_node):
            connected_nodes.add(succ)
        
        col_conn1, col_conn2 = st.columns(2)
        
        with col_conn1:
            st.write(f"**Direct connections:** {len(connected_nodes) - 1} nodes")
            st.write("**Connected nodes:**")
            for node in connected_nodes:
                if node != selected_node:
                    node_type = graph.nodes[node].get('type', 'unknown')
                    st.write(f"• {node} ({node_type})")
        
        with col_conn2:
            in_degree = graph.in_degree(selected_node)
            out_degree = graph.out_degree(selected_node)
            st.write(f"**Incoming connections:** {in_degree}")
            st.write(f"**Outgoing connections:** {out_degree}")
            st.write(f"**Total direct connections:** {in_degree + out_degree}")

def display_node_details(graph, node):
    """Display detailed information about a selected node"""
    
    st.subheader(f"🔧 Node Details: {node}")
    
    node_data = graph.nodes[node]
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Basic Information:**")
        st.write(f"• **Type**: {node_data.get('type', 'Unknown').title()}")
        st.write(f"• **Class**: {node_data.get('original_class', 'Unknown')}")
        st.write(f"• **Color**: {node_data.get('color', 'Unknown')}")
        st.write(f"• **Shape**: {node_data.get('symbol', 'Unknown')}")
    
    with col2:
        st.write("**Connection Analysis:**")
        in_degree = graph.in_degree(node)
        out_degree = graph.out_degree(node)
        total_degree = graph.degree(node)
        
        st.write(f"• **Incoming Connections**: {in_degree}")
        st.write(f"• **Outgoing Connections**: {out_degree}")
        st.write(f"• **Total Connections**: {total_degree}")
    
    # Show connected nodes
    st.write("**🔗 Connected Nodes:**")
    
    col_in, col_out = st.columns(2)
    
    with col_in:
        st.write("**Incoming from:**")
        predecessors = list(graph.predecessors(node))
        if predecessors:
            for pred in predecessors:
                edge_data = graph.get_edge_data(pred, node)
                edge_type = edge_data.get('type', 'connection') if edge_data else 'connection'
                st.write(f"• {pred} → {node} ({edge_type})")
        else:
            st.write("• No incoming connections")
    
    with col_out:
        st.write("**Outgoing to:**")
        successors = list(graph.successors(node))
        if successors:
            for succ in successors:
                edge_data = graph.get_edge_data(node, succ)
                edge_type = edge_data.get('type', 'connection') if edge_data else 'connection'
                st.write(f"• {node} → {succ} ({edge_type})")
        else:
            st.write("• No outgoing connections")

def display_interactive_legend():
    """Display interactive legend with enhanced information"""
    
       
    # Create expandable sections for different component types
    with st.expander("Legend", expanded=True):
        cols = st.columns(5)
        with cols[0]:
            st.markdown("""
            <div style="text-align: center; padding: 10px; border: 2px solid red; border-radius: 8px; margin: 5px 0;">
                <div style="color: red; font-size: 24px;">◆</div>
                <div style="font-weight: bold;">Bus</div>
                <div style="font-size: 0.8rem; color: #666;">Energy distribution point</div>
            </div>
            """, unsafe_allow_html=True)
    
        with cols[1]:
            st.markdown("""
            <div style="text-align: center; padding: 10px; border: 2px solid yellow; border-radius: 8px; margin: 5px 0;">
                <div style="color: yellow; font-size: 24px;">▲</div>
                <div style="font-weight: bold;">Source</div>
                <div style="font-size: 0.8rem; color: #666;">Energy generator</div>
            </div>
            """, unsafe_allow_html=True)
    
        with cols[2]:
            st.markdown("""
            <div style="text-align: center; padding: 10px; border: 2px solid green; border-radius: 8px; margin: 5px 0;">
                <div style="color: green; font-size: 24px;">▼</div>
                <div style="font-weight: bold;">Sink</div>
                <div style="font-size: 0.8rem; color: #666;">Energy consumer</div>
            </div>
            """, unsafe_allow_html=True)
    
        with cols[3]:
            st.markdown("""
            <div style="text-align: center; padding: 10px; border: 2px solid gray; border-radius: 8px; margin: 5px 0;">
                <div style="color: gray; font-size: 24px;">■</div>
                <div style="font-weight: bold;">Converter</div>
                <div style="font-size: 0.8rem; color: #666;">Energy conversion</div>
            </div>
            """, unsafe_allow_html=True)
        with cols[4]:
            st.markdown("""
            <div style="text-align: center; padding: 10px; border: 2px solid black; border-radius: 8px; margin: 5px 0;">
                <div style="color: black; font-size: 24px;">▶◀</div>
                <div style="font-weight: bold;">Storage</div>
                <div style="font-size: 0.8rem; color: #666;">Energy storage</div>
            </div>
            """, unsafe_allow_html=True)
    
    # Connection legend
    st.write("**🔗 Connection Types:**")
    col_conn1, col_conn2 = st.columns(2)
    with col_conn1:
        st.markdown("• **Gray lines**: Structural connections")
        st.markdown("• **Green lines**: Energy flow")
    with col_conn2:
        st.markdown("• **Blue highlighted node**: Selected node")
        st.markdown("• **Hover for details**: Flow values and types")