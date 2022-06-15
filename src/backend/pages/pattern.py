import datetime
from datetime import date

from backend.components.misc import container, single_row, button, show_title_maker, show_button_id, global_signal_id_maker, temp_jobs_store_id_maker, global_form_load_signal_id_maker
import dash_interactive_graphviz
from dash.dependencies import Input, Output, State
import dash_html_components as html
import dash_core_components as dcc
import dash_bootstrap_components as dbc
from backend.app import app
import dash_table
import dash
from backend.param.constants import PATTERN_TITLE, GLOBAL_FORM_SIGNAL, PATTERN_URL, PERF_ANALYSIS_TITLE

from dtween.available.constants import COMP_OPERATORS, UNITS


from dtween.util.util import DIAGNOSTICS_NAME_MAP, PERFORMANCE_AGGREGATION_NAME_MAP, DIAGNOSTICS_SHOW_NAME_MAP

from backend.util import run_task, read_global_signal_value, no_update, create_2d_plate, create_3d_plate, pattern_graph_stylesheet
from backend.tasks.tasks import get_remote_data, retrieve_eocpn, add_pattern_graph, clear_all_pattern_graphs
from dtween.available.available import AvailableTasks, AvailableDiagnostics, DefaultDiagnostics, AvailablePerformanceAggregation, AvailablePerformance, AvailableFrequency
from flask import request
from dateutil import parser
from ocpa.visualization.oc_petri_net import factory as ocpn_vis_factory
from ocpa.objects.log.converter import factory as ocel_converter_factory
from ocpa.visualization.pattern_graph import algorithm as pattern_graph_viz_factory

import dash_cytoscape as cyto
import pandas as pd


pattern_load_eocpn_button_title = "load existing design".title()
pattern_refresh_button_title = "start new design".title()
pattern_design_button_title = "edit new".title()
pattern_add_button_title = "add new".title()


available_diagonstics = [e.value for e in AvailableDiagnostics]
available_aggregations = [e.value for e in AvailablePerformanceAggregation]
default_diagonstics = [e.value for e in DefaultDiagnostics]

available_frequency = [e.value for e in AvailableFrequency]
available_performance = [e.value for e in AvailablePerformance]

display = html.Div(
    id="pattern-perf-display",
    className="number-plate",
    children=[]
)

pattern_ecopn_view = dbc.Row(
    [
        dcc.Store(id='gv-pattern-eocpn-view-dot',
                  storage_type='session', data=""),
        dbc.Col(
            dash_interactive_graphviz.DashInteractiveGraphviz(
                id="gv-pattern-ecopn-view"), width=6
        ),
        dbc.Col(
            display, width=6
        )
    ],
    # style=dict(position="absolute", height="100%",
    #            width="100%", display="flex"),
    style={'height': '100vh'}
)

loading_buttons = [
    button(pattern_refresh_button_title, show_title_maker, show_button_id)
]

pattern_buttons = [
    button(pattern_design_button_title, show_title_maker, show_button_id),
    button(pattern_add_button_title, show_title_maker, show_button_id)
]

pattern_parameters = [
    dbc.Modal(
        [
            dbc.ModalHeader("Edit Pattern Graph"),
            dbc.ModalBody(
                [
                    dbc.Label("Name:"),
                    dbc.Input(id="pattern-graph-name",
                              type="text", debounce=True),
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Button("OK", color="primary",
                               id="ok-pattern-name"),
                    dbc.Button(
                        "Cancel", id="cancel-pattern-name"),
                ]
            ),
        ],
        id="edit-pattern-graph-modal",
    ),
    dcc.Store(id='edit-pattern-graph', storage_type='session', data={}),
    dbc.Col(
        dbc.Card(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.H2(f"Control-flow Patterns",
                                        className="card-title"),
                            ]
                        ),
                        dbc.Col(
                            [
                                dbc.Button(
                                    'Add', 'add-control-flow-edge', className="mb-3")
                            ]
                        )
                    ], align='center'
                ),
                html.Hr(),
                dbc.Col(
                    dcc.Dropdown(
                        id='cf-source-dropdown',
                        placeholder="Select Source Activity"
                    )
                ),
                dbc.Col(
                    dcc.Dropdown(
                        id='cf-target-dropdown',
                        placeholder="Select Target Activity"
                    )
                ),
                dbc.Col(
                    dcc.Dropdown(
                        id='cf-label-dropdown',
                        placeholder="Select Control-flow Label",
                        options=[{'label': a, 'value': a}
                                 for a in ['causal', 'concur', 'choice', 'skip']]
                    )
                ),
                dbc.Col(
                    dcc.Dropdown(
                        id='cf-object-type-dropdown',
                        placeholder="Select Object Type"
                    )
                ),
                dbc.Col(
                    html.Div(
                        [dbc.Label("Select Threshold"),
                         dcc.Slider(min=0, max=100, step=1, value=50,
                                    id='cf-threshold-slider'),
                         dbc.FormText(id='cf-threshold-slider-text')]
                    )
                ),
            ],
            body=True,
            color="light",
        ), width=4
    ),
    dbc.Col(
        dbc.Card(
            [
                dbc.Row(
                    [
                        dbc.Col(html.H2(f"Object Involvement Patterns",
                                className="card-title")),
                        dbc.Col(
                            dbc.Button(
                                'Add', 'add-object-involvement-edge', className="mb-3")
                        )
                    ], align='center'
                ),
                html.Hr(),
                dbc.Col(
                    dcc.Dropdown(
                        id='or-source-dropdown',
                        placeholder="Select Object Type"
                    )
                ),
                dbc.Col(
                    dcc.Dropdown(
                        id='or-target-dropdown',
                        placeholder="Select Target Activity"
                    )
                ),
                dbc.Col(
                    dcc.Dropdown(
                        id='or-label-dropdown',
                        placeholder="Select Involvement Label",
                        options=[{'label': a, 'value': a}
                                 for a in ['absent', 'present', 'singular', 'multiple']]
                    )
                ),
                dbc.Col(
                    html.Div(
                        [dbc.Label("Select Threshold"),
                         dcc.Slider(min=0, max=100, step=1, value=50,
                                    id='or-threshold-slider'),
                         dbc.FormText(id='or-threshold-slider-text')]
                    )
                ),
            ],
            body=True,
            color="light"
        ), width=4
    ),
    dbc.Col(
        dbc.Card(
            [
                dbc.Row(
                    [
                        dbc.Col(html.H2(f"Performance Patterns",
                                className="card-title")),
                        dbc.Col(
                            dbc.Button(
                                'Add', 'add-perf-edge', className="mb-3")
                        )
                    ], align='center'
                ),
                html.Hr(),
                dbc.Row(
                    dbc.Col(
                        dcc.Dropdown(
                            id='perf-target-dropdown',
                            placeholder="Select Target Activity"
                        )
                    ), align='center'
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            dcc.Dropdown(
                                id='formula-agg-dropdown',
                                placeholder="Agg."
                            ), width=4
                        ),
                        dbc.Col(
                            dcc.Dropdown(
                                id='formula-diag-dropdown',
                                placeholder="Diagnostics"
                            ), width=4
                        ),
                        dbc.Col(
                            dcc.Dropdown(
                                id='formula-obj-dropdown',
                                placeholder="Object Type"
                            ), width=4
                        )
                    ],
                    align='center'
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            dcc.Dropdown(
                                id='formula-comp-dropdown',
                                placeholder="Comparator",
                                options=[{'label': d, 'value': d}
                                         for d in COMP_OPERATORS],
                            ), width=4
                        ),
                        dbc.Col(
                            dcc.Input(id="formula-threshold", type="number", placeholder="Threshold", style={'width': '80%'}), width=4
                        ),
                        dbc.Col(
                            dcc.Dropdown(
                                id='formula-unit-dropdown',
                                placeholder="Unit",
                                options=[{'label': d, 'value': d}
                                         for d in UNITS],
                            ), width=4
                        ),
                    ],
                    align='center'
                ),
            ],
            body=True,
            color="light"
        ), width=4
    )
]

pattern_graph_view = dbc.Card(
    children=[
        html.H2(
            'Existing Pattern Graphs:',
            id='pattern-graph-label'
        ),
        dcc.Dropdown(id='selected-pattern-graph-dropdown',
                     placeholder="Select Pattern Graph"),
        cyto.Cytoscape(
            id='selected-pattern-graph-view',
            style={
                'height': '45vh',
                'width': '100%'
            },
            stylesheet=pattern_graph_stylesheet
        )
    ],
    body=True,
    color="light",
)

edit_pattern_graph_view = dbc.Card(
    children=[
        html.H2('Designing a new pattern '),
        html.H2('Click Edit New', id='edit-pattern-graph-label'),
        cyto.Cytoscape(
            id='edit-pattern-graph-view',
            elements=[],
            style={
                'height': '45vh',
                'width': '100%'
            },
            stylesheet=pattern_graph_stylesheet
        )
    ],
    body=True,
    color="light",
)

pattern_graph_content = dbc.Row(
    [
        dbc.Col(
            [
                edit_pattern_graph_view
            ], width=6),
        dbc.Col(
            [
                pattern_graph_view
            ], width=6)
    ]
)


page_layout = container('Designing Process-Centric Problem Patterns',
                        [
                            dcc.Location(id='pattern-url', refresh=False),
                            single_row(html.Div(loading_buttons)),
                            single_row(html.Div(pattern_buttons)),
                            dbc.Row(pattern_parameters),
                            html.Hr(),
                            pattern_graph_content,
                            pattern_ecopn_view,
                        ]
                        )


@app.callback(
    Output('cf-threshold-slider-text', 'children'),
    Input('cf-threshold-slider', 'value')
)
def callback_viz_cf_threshold(value):
    return f'Threshold set to {value/100}'


@app.callback(
    Output('or-threshold-slider-text', 'children'),
    Input('or-threshold-slider', 'value')
)
def callback_viz_or_threshold(value):
    return f'Threshold set to {value/100}'


@ app.callback(
    Output("gv-pattern-ecopn-view", "dot_source"),
    Output("gv-pattern-ecopn-view", "engine"),
    Input('pattern-url', 'pathname'),
    Input("gv-pattern-eocpn-view-dot", "data")
)
def show_ocpn(pathname, value):
    if pathname == PATTERN_URL and value is not None:
        return value, "dot"
    return no_update(2)


# @ app.callback(
#     Output('gv-pattern-eocpn-view-dot', 'data'),
#     Input(show_button_id(pattern_load_eocpn_button_title), 'n_clicks'),
#     State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
#     State(temp_jobs_store_id_maker(PERF_ANALYSIS_TITLE), 'data')
# )
# def load_eocpn(n_load, value, perf_jobs):
#     ctx = dash.callback_context
#     if not ctx.triggered:
#         button_id = 'No clicks yet'
#         button_value = None
#     else:
#         button_id = ctx.triggered[0]['prop_id'].split('.')[0]
#         button_value = ctx.triggered[0]['value']

#     if button_value is None:
#         return dash.no_update

#     if button_id == show_button_id(pattern_load_eocpn_button_title):
#         user = request.authorization['username']
#         log_hash, date = read_global_signal_value(value)
#         eocpn = get_remote_data(user, log_hash, perf_jobs,
#                                 AvailableTasks.OPERA.value)
#         gviz = ocpn_vis_factory.apply(
#             eocpn.ocpn, diagnostics=eocpn.diagnostics, variant="annotated_with_opera")
#         eocpn_dot = str(gviz)
#         return eocpn_dot

#     return dash.no_update


@ app.callback(
    Output('gv-pattern-eocpn-view-dot', 'data'),
    Output('cf-source-dropdown', 'options'),
    Output('cf-target-dropdown', 'options'),
    Output('cf-object-type-dropdown', 'options'),
    Output('or-source-dropdown', 'options'),
    Output("or-target-dropdown", "options"),
    Output("perf-target-dropdown", "options"),
    Output('formula-diag-dropdown', 'options'),
    Output('formula-agg-dropdown', 'options'),
    Output('formula-obj-dropdown', 'options'),
    Input('pattern-url', 'pathname'),
    State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
    State(temp_jobs_store_id_maker(PERF_ANALYSIS_TITLE), 'data'),
)
def refresh_patterns(pathname, value, perf_jobs):
    if pathname == PATTERN_URL:
        user = request.authorization['username']
        log_hash, date = read_global_signal_value(value)

        eocpn = get_remote_data(user, log_hash, perf_jobs,
                                AvailableTasks.OPERA.value)

        gviz = ocpn_vis_factory.apply(
            eocpn.ocpn, diagnostics=eocpn.diagnostics, variant="annotated_with_opera")
        eocpn_dot = str(gviz)

        object_types = eocpn.ocpn.object_types
        activities = [
            t.name for t in eocpn.ocpn.transitions if t.silent == False]
        dropdown_activities = [{'label': a, 'value': a} for a in activities]
        dropdown_object_types = [{'label': a, 'value': a}
                                 for a in object_types]
        dropdown_aggregations = [{'label': a, 'value': a}
                                 for a in available_aggregations]
        dropdown_performance = [{'label': a, 'value': a}
                                for a in available_performance]
        dropdown_frequency = [{'label': a, 'value': a}
                              for a in available_frequency+available_performance]

        return eocpn_dot, dropdown_activities, dropdown_activities, dropdown_object_types, dropdown_object_types, dropdown_activities, dropdown_activities, dropdown_frequency, dropdown_aggregations, dropdown_object_types

    return no_update(10)


@ app.callback(
    Output("pattern-perf-display", "children"),
    Output("cf-source-dropdown", "value"),
    Output("or-target-dropdown", "value"),
    Output("perf-target-dropdown", "value"),
    Input("gv-pattern-ecopn-view", "selected_node"),
    State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
    State(temp_jobs_store_id_maker(PERF_ANALYSIS_TITLE), 'data'),
)
def show_selected(selected, value, perf_jobs):
    if selected is not None:
        # selected_tokens = [[pl, oi]
        #                    for pl, oi in tokens if str(value) == str(pl)]
        log_hash, date = read_global_signal_value(value)
        user = request.authorization['username']
        if '(t)' in selected:
            selected = selected.replace('(t)', '')
        elif ('p') in selected:
            return no_update(4)
        ocpn = get_remote_data(user, log_hash, perf_jobs,
                               AvailableTasks.OPERA.value)
        selected_diag = ocpn.diagnostics[selected]

        plate_frames = [html.H3(f"Performance @ {selected}")]
        if 'object_count' in selected_diag:
            plate_frames.append(create_2d_plate(
                'Number of objects', selected_diag['object_count'], time_measure=False))
            plate_frames.append(html.Br())

        if 'waiting_time' in selected_diag:
            plate_frames.append(create_2d_plate(
                'Waiting Time', selected_diag['waiting_time']))
            plate_frames.append(html.Br())

        if 'service_time' in selected_diag:
            plate_frames.append(create_2d_plate(
                'Service Time', selected_diag['service_time']))
            plate_frames.append(html.Br())

        if 'sojourn_time' in selected_diag:
            plate_frames.append(create_2d_plate(
                'Sojourn Time', selected_diag['sojourn_time']))
            plate_frames.append(html.Br())

        if 'synchronization_time' in selected_diag:
            plate_frames.append(create_2d_plate(
                'Synchronization Time', selected_diag['synchronization_time']))
            plate_frames.append(html.Br())

        if 'lagging_time' in selected_diag:
            plate_frames.append(create_3d_plate(
                'Lagging Time', selected_diag['lagging_time']))
            plate_frames.append(html.Br())

        if 'pooling_time' in selected_diag:
            plate_frames.append(create_3d_plate(
                'Pooling Time', selected_diag['pooling_time']))
            plate_frames.append(html.Br())

        if 'flow_time' in selected_diag:
            plate_frames.append(create_2d_plate(
                'Flow Time', selected_diag['flow_time']))
            plate_frames.append(html.Br())
        return plate_frames, selected, selected, selected

    else:
        return no_update(4)


# @ app.callback(
#     Output('formula-obj-dropdown', 'options'),
#     Output('formula-obj-dropdown', 'disable'),
#     Input('formula-diag-dropdown', 'value'),
#     State('perf-target-dropdown', 'value'),
#     State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
#     State(temp_jobs_store_id_maker(DESIGN_TITLE), 'data'),
#     State(temp_jobs_store_id_maker(PERF_ANALYSIS_TITLE), 'data'),
# )
# def update_objs(selected_freq, selected_activity, value, design_jobs, perf_jobs):

#     if selected_freq is not None:
#         user = request.authorization['username']
#         log_hash, date = read_global_signal_value(value)

#         ocpn = get_remote_data(user, log_hash, design_jobs,
#                                AvailableTasks.DESIGN.value)

#         selected_tr = ocpn.find_transition(selected_activity)
#         related_object_types = [
#             a.source.object_type for a in selected_tr.in_arcs]
#         dropdown_related_object_types = [{'label': a, 'value': a}
#                                          for a in related_object_types]

#         if selected_freq in [DefaultDiagnostics.GROUP_SIZE.value]:
#             return dropdown_related_object_types, False
#         else:
#             return dash.no_update, True

#     return no_update(2)


# @ app.callback(
#     Output('pattern-performance-obj-dropdown', 'options'),
#     Output('pattern-performance-obj-dropdown', 'disable'),
#     Input('pattern-performance-dropdown', 'value'),
#     State('perf-target-dropdown', 'value'),
#     State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
#     State(temp_jobs_store_id_maker(DESIGN_TITLE), 'data'),
#     State(temp_jobs_store_id_maker(PERF_ANALYSIS_TITLE), 'data'),
# )
# def update_objs(selected_perf, selected_activity, value, design_jobs, perf_jobs):

#     if selected_perf is not None:
#         user = request.authorization['username']
#         log_hash, date = read_global_signal_value(value)

#         ocpn = get_remote_data(user, log_hash, design_jobs,
#                                AvailableTasks.DESIGN.value)

#         selected_tr = ocpn.find_transition(selected_activity)
#         related_object_types = [
#             a.source.object_type for a in selected_tr.in_arcs]
#         dropdown_related_object_types = [{'label': a, 'value': a}
#                                          for a in related_object_types]

#         if selected_perf in [DefaultDiagnostics.POOLING_TIME.value, DefaultDiagnostics.LAGGING_TIME.value]:
#             return dropdown_related_object_types, False
#         else:
#             return dash.no_update, True

#     return no_update(2)


@ app.callback(
    Output('edit-pattern-graph', 'data'),
    Output("edit-pattern-graph-modal", "is_open"),
    Output("edit-pattern-graph-label", "children"),
    Input(show_button_id(pattern_design_button_title), 'n_clicks'),
    Input(show_button_id(pattern_add_button_title), 'n_clicks'),
    Input('add-control-flow-edge', 'n_clicks'),
    Input('add-object-involvement-edge', 'n_clicks'),
    Input('add-perf-edge', 'n_clicks'),
    Input("ok-pattern-name", "n_clicks"),
    Input("cancel-pattern-name", "n_clicks"),
    State('edit-pattern-graph', 'data'),
    State("pattern-graph-name", "value"),
    State('cf-source-dropdown', 'value'),
    State('cf-target-dropdown', 'value'),
    State('cf-label-dropdown', 'value'),
    State('cf-object-type-dropdown', 'value'),
    State('cf-threshold-slider', 'value'),
    State('or-source-dropdown', 'value'),
    State('or-target-dropdown', 'value'),
    State('or-label-dropdown', 'value'),
    State('or-threshold-slider', 'value'),
    State('formula-agg-dropdown', 'value'),
    State('formula-diag-dropdown', 'value'),
    State('formula-obj-dropdown', 'value'),
    State('formula-comp-dropdown', 'value'),
    State('formula-unit-dropdown', 'value'),
    State('formula-threshold', 'value'),
    State('perf-target-dropdown', 'value'),
    State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
    State(temp_jobs_store_id_maker(PERF_ANALYSIS_TITLE), 'data'),
)
def start_editing_patterns(n_edit, n_add, n_cf, n_or, n_perf, n_name_ok, n_name_cancel, edit_pattern_graph, pg_name, cf_source, cf_target, cf_label, cf_object_type, cf_threshold, or_source, or_target, or_label, or_threshold, formula_agg, formula_diag, formula_obj, formula_comp, formula_unit, formula_thre, perf_target, value, perf_jobs):
    ctx = dash.callback_context
    if not ctx.triggered:
        button_id = 'No clicks yet'
        button_value = None
    else:
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        button_value = ctx.triggered[0]['value']

    if button_value is None:
        return no_update(3)

    if button_id == show_button_id(pattern_design_button_title):

        return dash.no_update, True, dash.no_update

    elif button_id == show_button_id(pattern_add_button_title):
        return edit_pattern_graph, False, f'Click Edit New'

    elif button_id == 'ok-pattern-name':
        edit_pattern_graph = {}
        edit_pattern_graph['cf_edges'] = []
        edit_pattern_graph['or_edges'] = []
        edit_pattern_graph['perf_edges'] = []
        edit_pattern_graph['name'] = pg_name
        return edit_pattern_graph, False, f'Current Pattern Name: {pg_name}'

    elif button_id == 'cancel-pattern-name':
        return dash.no_update, False, dash.no_update

    elif button_id == 'add-control-flow-edge':
        edit_pattern_graph['cf_edges'].append(
            {'type': 'cf', 'source': cf_source,
                'target': cf_target, 'label': cf_label, 'object_type': cf_object_type, 'threshold': cf_threshold/100}
        )
        return edit_pattern_graph, False, dash.no_update

    elif button_id == 'add-object-involvement-edge':
        edit_pattern_graph['or_edges'].append(
            {'type': 'or', 'source': or_source,
                'target': or_target, 'label': or_label, 'threshold': or_threshold/100}
        )
        return edit_pattern_graph, False, dash.no_update

    elif button_id == 'add-perf-edge':
        formula_diag = DIAGNOSTICS_NAME_MAP[formula_diag]
        if formula_agg is not None:
            formula_agg = PERFORMANCE_AGGREGATION_NAME_MAP[formula_agg]
        if formula_unit == 'day(s)':
            formula_thre = formula_thre * 60 * 60 * 24
        elif formula_unit == 'hour(s)':
            formula_thre = formula_thre * 60 * 60
        elif formula_unit == 'minute(s)':
            formula_thre = formula_thre * 60
        elif formula_unit == 'second(s)':
            formula_thre = formula_thre
        else:
            formula_thre = formula_thre
        edit_pattern_graph['perf_edges'].append(
            {'type': 'perf', 'formula_agg': formula_agg, 'formula_diag': formula_diag, 'formula_obj': formula_obj, 'formula_comp': formula_comp, 'formula_thre': formula_thre,
                'target': perf_target}
        )
        return edit_pattern_graph, False, dash.no_update

    return no_update(3)


@ app.callback(
    Output('edit-pattern-graph-view', 'elements'),
    Input('edit-pattern-graph', 'data'),
)
def callback_viz_pattern_edit(edit_pattern_graph):
    nodes = set()
    pg_edges = []
    pg_nodes = []
    for elem in edit_pattern_graph['cf_edges']:
        source, target = elem['source'], elem['target']
        if source not in nodes:
            nodes.add(source)
            pg_nodes.append(
                {"data": {"id": source, "label": source}, "classes": 'activity'})
        if target not in nodes:
            nodes.add(target)
            pg_nodes.append(
                {"data": {"id": target, "label": target}, "classes": 'activity'})
        if elem['label'] == 'skip':
            pg_edges.append(
                {"data": {"source": source, "target": target, "label": f'{elem["label"]} \n {elem["object_type"]},{elem["threshold"]}'}, "classes": 'loop'})
        else:
            pg_edges.append(
                {"data": {"source": source, "target": target, "label": f'{elem["label"]} \n {elem["object_type"]},{elem["threshold"]}'}})
    for elem in edit_pattern_graph['or_edges']:
        source, target = elem['source'], elem['target']
        if source not in nodes:
            nodes.add(source)
            pg_nodes.append(
                {"data": {"id": source, "label": source}, "classes": 'object_type'})
        if target not in nodes:
            nodes.add(target)
            pg_nodes.append(
                {"data": {"id": target, "label": target}, "classes": 'activity'})
        pg_edges.append(
            {"data": {"source": source, "target": target, "label": f'{elem["label"]} \n {elem["threshold"]}'}})
    for elem in edit_pattern_graph['perf_edges']:
        if elem['formula_agg'] is not None and elem['formula_obj'] is not None:
            source = f"{elem['formula_agg']} {DIAGNOSTICS_SHOW_NAME_MAP[elem['formula_diag']]} of {elem['formula_obj']} {elem['formula_comp']} {elem['formula_thre']}"
        elif elem['formula_agg'] is None and elem['formula_obj'] is not None:
            source = f"{DIAGNOSTICS_SHOW_NAME_MAP[elem['formula_diag']]} of {elem['formula_obj']} {elem['formula_comp']} {elem['formula_thre']}"
        elif elem['formula_agg'] is not None and elem['formula_obj'] is None:
            source = f"{elem['formula_agg']} {DIAGNOSTICS_SHOW_NAME_MAP[elem['formula_diag']]} {elem['formula_comp']} {elem['formula_thre']}"
        else:
            raise ValueError(
                f'Provide 1) diagnostics, 2) comparators, 3) threshold')
        target = elem['target']
        if source not in nodes:
            nodes.add(source)
            pg_nodes.append(
                {"data": {"id": source, "label": source}, "classes": 'formula'})
        if target not in nodes:
            nodes.add(target)
            pg_nodes.append(
                {"data": {"id": target, "label": target}, "classes": 'activity'})
        pg_edges.append(
            {"data": {"source": source, "target": target}})
    elements = pg_nodes + pg_edges
    return elements


@ app.callback(
    Output(temp_jobs_store_id_maker(PATTERN_TITLE), 'data'),
    Output('selected-pattern-graph-dropdown', 'options'),
    Input('pattern-url', 'pathname'),
    Input(show_button_id(pattern_refresh_button_title), 'n_clicks'),
    Input(show_button_id(pattern_add_button_title), 'n_clicks'),
    State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
    State(temp_jobs_store_id_maker(PERF_ANALYSIS_TITLE), 'data'),
    State(temp_jobs_store_id_maker(PATTERN_TITLE), 'data'),
    State('edit-pattern-graph', 'data'),


)
def add_pattern(pathname, n_refresh, n_add, value, perf_jobs, pattern_jobs, edit_pattern_graph):
    ctx = dash.callback_context
    if not ctx.triggered:
        button_id = 'No clicks yet'
        button_value = None
    else:
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        button_value = ctx.triggered[0]['value']

    if button_value is None:
        return no_update(2)
    if button_id == show_button_id(pattern_refresh_button_title):
        user = request.authorization['username']
        log_hash, date = read_global_signal_value(value)
        task_id = run_task(
            perf_jobs, log_hash, AvailableTasks.DESIGN_PROBLEM_PATTERN.value, clear_all_pattern_graphs)
        return perf_jobs, dash.no_update

    elif button_value == PATTERN_URL:
        user = request.authorization['username']
        log_hash, date = read_global_signal_value(value)
        pattern_graphs = get_remote_data(user, log_hash, pattern_jobs,
                                         AvailableTasks.DESIGN_PROBLEM_PATTERN.value)
        if pattern_graphs is None:
            pattern_names = []
        else:
            pattern_names = [pg.name for pg in pattern_graphs]
        pg_options = [{'label': a, 'value': a}
                      for a in pattern_names]
        return pattern_jobs, pg_options

    elif button_id == show_button_id(pattern_add_button_title):
        user = request.authorization['username']
        log_hash, date = read_global_signal_value(value)
        pattern_graphs = get_remote_data(user, log_hash, pattern_jobs,
                                         AvailableTasks.DESIGN_PROBLEM_PATTERN.value)
        task_id = run_task(
            pattern_jobs, log_hash, AvailableTasks.DESIGN_PROBLEM_PATTERN.value, add_pattern_graph, pattern_graphs=pattern_graphs, edit_pattern_graph=edit_pattern_graph)
        pattern_graphs = get_remote_data(user, log_hash, pattern_jobs,
                                         AvailableTasks.DESIGN_PROBLEM_PATTERN.value)
        pattern_names = [pg.name for pg in pattern_graphs]
        pg_options = [{'label': a, 'value': a}
                      for a in pattern_names]
        return pattern_jobs, pg_options

    return no_update(2)


# @ app.callback(
#     Output('selected-pattern-graph-dropdown', 'options'),
#     Input(show_button_id(pattern_add_button_title), 'n_clicks'),
#     State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
#     State(temp_jobs_store_id_maker(PATTERN_TITLE), 'data'),
# )
# def show_selected(selected, value, pattern_jobs):
#     if selected is not None:
#         user = request.authorization['username']
#         log_hash, date = read_global_signal_value(value)
#         pattern_graphs = get_remote_data(user, log_hash, pattern_jobs,
#                                          AvailableTasks.DESIGN_PROBLEM_PATTERN.value)
#         pattern_names = [pg.name for pg in pattern_graphs]
#         pg_options = [{'label': a, 'value': a}
#                       for a in pattern_names]
#         return pg_options

#     else:
#         return dash.no_update


@ app.callback(
    Output("selected-pattern-graph-view", "elements"),
    Input('selected-pattern-graph-dropdown', 'value'),
    State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
    State(temp_jobs_store_id_maker(PATTERN_TITLE), 'data'),
)
def show_selected(selected, value, pattern_jobs):
    if selected is not None:
        user = request.authorization['username']
        log_hash, date = read_global_signal_value(value)
        pattern_graphs = get_remote_data(user, log_hash, pattern_jobs,
                                         AvailableTasks.DESIGN_PROBLEM_PATTERN.value)
        for pg in pattern_graphs:
            if pg.name == selected:
                cy_nodes, cy_edges = pattern_graph_viz_factory.apply(pg)
                return cy_nodes + cy_edges
        return dash.no_update

    else:
        return dash.no_update
