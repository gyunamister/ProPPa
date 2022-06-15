import base64
import datetime
from datetime import date
import hashlib

from backend.components.misc import container, single_row, button, show_title_maker, show_button_id, global_signal_id_maker, temp_jobs_store_id_maker, global_form_load_signal_id_maker
import dash_interactive_graphviz
from dash.dependencies import Input, Output, State
import dash_html_components as html
import dash_core_components as dcc
import dash_bootstrap_components as dbc
from backend.app import app
import dash
from backend.param.constants import PATTERN_TITLE, GLOBAL_FORM_SIGNAL, PATTERN_URL, PERF_ANALYSIS_TITLE, MONITORING_TITLE, JSON, NA
from dtween.util.util import DIAGNOSTICS_NAME_MAP, PERFORMANCE_AGGREGATION_NAME_MAP
from dtween.available.constants import COMP_OPERATORS

from backend.util import run_task, read_global_signal_value, no_update, pattern_graph_stylesheet, parse_contents, build_json_param
from backend.tasks.tasks import get_remote_data, evaluate_pattern_graphs, parse_data, discover_ocpn, retrieve_eocpn
from dtween.available.available import AvailableTasks, AvailableDiagnostics, DefaultDiagnostics, AvailablePerformanceAggregation, AvailablePerformance, AvailableFrequency
from flask import request
from ocpa.visualization.oc_petri_net import factory as ocpn_vis_factory
from ocpa.objects.log.converter import factory as ocel_converter_factory
from ocpa.visualization.pattern_graph import algorithm as pattern_graph_viz_factory
from backend.param.styles import LINK_CONTENT_STYLE, CENTER_DASHED_BOX_STYLE

import dash_cytoscape as cyto
import dash_daq as daq


monitoring_load_event_log_button_title = "load event log".title()
monitoring_load_pattern_graphs_button_title = "load pattern graphs".title()
monitoring_evaluate_button_title = "evaluate".title()

available_diagonstics = [e.value for e in AvailableDiagnostics]
available_aggregations = [e.value for e in AvailablePerformanceAggregation]
default_diagonstics = [e.value for e in DefaultDiagnostics]

available_frequency = [e.value for e in AvailableFrequency]
available_performance = [e.value for e in AvailablePerformance]

display = html.Div(
    id="monitoring-perf-display",
    className="number-plate",
    children=[]
)

monitoring_ecopn_view = dbc.Row(
    [
        dcc.Store(id='gv-monitoring-eocpn-view-dot',
                  storage_type='session', data=""),
        dbc.Col(
            [
                html.H2('Process Analysis Results',
                        id='monitoring-analysis-results-label'),
                dash_interactive_graphviz.DashInteractiveGraphviz(
                    id="gv-monitoring-ecopn-view")
            ], width=6
        ),
        dbc.Col(
            display, width=6
        )
    ],
    # style=dict(position="absolute", height="100%",
    #            width="100%", display="flex"),
    style={'height': '100vh'}
)

monitoring_buttons = [
    # dcc.Upload(button(monitoring_load_event_log_button_title,
    #                   show_title_maker, show_button_id)),
    dcc.Upload(
        id='upload-monitoring-data',
        children=html.Div([
            'Drag and Drop or ', html.A(
                'Select a OCEL JSON File')
        ],
            style=LINK_CONTENT_STYLE),
        style=CENTER_DASHED_BOX_STYLE,
        multiple=False
    ),
    html.H4(id='monitoring-data-label'),
    button(monitoring_load_pattern_graphs_button_title,
           show_title_maker, show_button_id),
    button(monitoring_evaluate_button_title, show_title_maker, show_button_id),
]


def create_result_card(pg_name, exist, messages):
    if exist:
        printed_message = ""
        for message in messages:
            printed_message += f'- {message} \n'
        result_card = dbc.Card(
            dbc.CardBody(
                [
                    html.H2(f"{pg_name}", className="card-title"),
                    daq.Indicator(
                        label=f"Exist",
                        color='#cc3300',
                        value=True
                    ),
                    # html.P(
                    #     f"{printed_message}",
                    #     className="card-text",
                    # ),
                    dcc.Markdown(
                        f"{printed_message}"
                    )
                ]
            )
        )
    else:
        result_card = dbc.Card(
            dbc.CardBody(
                [
                    html.H2(f"{pg_name}", className="card-title"),
                    daq.Indicator(
                        label=f"Not exist",
                        color='#339900',
                        value=False
                    )
                ]
            )
        )
    return dbc.Col(result_card)


monitoring_results_and_search_pattern_graph = dbc.Row(
    [
        dbc.Col(
            [
                html.H2('Monitoring Results', id='monitoring-results-label'),
                html.Div(id='monitoring-results'),

            ], width=6
        ),
        dbc.Col(
            [
                html.H2('Loaded Pattern Graphs',
                        id='search-pattern-graph-label'),
                dcc.Dropdown(
                    id='selected-monitoring-pattern-graph-dropdown',
                    placeholder='Select Pattern Graph'
                ),
                cyto.Cytoscape(
                    id='monitoring-selected-pattern-graph-view',
                    style={
                        'height': '45vh',
                        'width': '100%'
                    },
                    stylesheet=pattern_graph_stylesheet
                )
            ], width=6)
    ]
)


page_layout = container('Monitoring Process-Centric Problem Patterns',
                        [
                            single_row(html.Div(monitoring_buttons)),
                            html.Hr(),
                            monitoring_results_and_search_pattern_graph,
                            html.Hr(),
                            monitoring_ecopn_view,
                        ]
                        )


@ app.callback(
    Output("gv-monitoring-ecopn-view", "dot_source"),
    Output("gv-monitoring-ecopn-view", "engine"),
    Input("gv-monitoring-eocpn-view-dot", "data")
)
def show_ocpn(value):
    if value is not None:
        return value, "dot"
    return dash.no_update


def create_1d_plate(title, value):
    return html.Div(
        className='number-plate-single',
        style={'border-top': '#292929 solid .2rem', },
        children=[
            html.H5(
                style={'color': '#292929', },
                children=title
            ),
            html.H3(
                style={'color': '#292929'},
                children=[
                    '{}'.format(value),
                    html.P(
                        style={'color': '#ffffff', },
                        children='xxxx xx xxx xxxx xxx xxxxx'
                    ),
                ]
            ),
        ]
    )


def create_2d_plate(title, diag):
    num_plates = len(diag.keys())
    plate_width = (100 / num_plates) - 1

    def create_number_plate(plate_width, name, val):
        return html.Div(  # small block upper most
            className='number-plate-single',
            children=[
                html.H3(f'{name}'),
                html.H3('{}'.format(val))
            ], style={'width': f'{plate_width}%', 'display': 'inline-block'})

    plates = []
    for agg in diag:
        plates.append(create_number_plate(plate_width, agg, diag[agg]))

    return html.Div(
        className='number-plate-single',
        style={'border-top': '#292929 solid .2rem', },
        children=[
            html.H5(
                style={'color': '#292929', },
                children=title
            ),
            html.Div(
                style={'color': '#292929'},
                children=plates
            ),
        ]
    )


def create_3d_plate(title, diag):

    def create_number_plate(plate_width, name, val):
        return html.Div(  # small block upper most
            className='number-plate-single',
            children=[
                html.H3(f'{name}'),
                html.H3('{}'.format(val))
            ], style={'width': f'{plate_width}%', 'display': 'inline-block'})

    first_plates = []
    for ot in diag:
        second_plates = []
        num_plates = len(diag[ot].keys())
        plate_width = (100 / num_plates) - 1
        for agg in diag[ot]:
            second_plates.append(create_number_plate(
                plate_width, agg, diag[ot][agg]))
        first_plate = html.Div(
            className='number-plate-single',
            style={'border-top': '#292929 solid .2rem', },
            children=[
                html.H5(
                    style={'color': '#292929', },
                    children=ot
                ),
                html.Div(
                    style={'color': '#292929'},
                    children=second_plates
                ),
            ]
        )
        first_plates.append(first_plate)

    return html.Div(
        className='number-plate-single',
        style={'border-top': '#292929 solid .2rem', },
        children=[
            html.H5(
                style={'color': '#292929', },
                children=title
            ),
            html.Div(
                style={'color': '#292929'},
                children=first_plates
            ),
        ]
    )


@ app.callback(
    Output("monitoring-perf-display", "children"),
    Input("gv-monitoring-ecopn-view", "selected_node"),
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
                'Number of objects', selected_diag['object_count']))
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
        return plate_frames

    else:
        return dash.no_update


@ app.callback(
    Output("monitoring-selected-pattern-graph-view", "elements"),
    Input('selected-monitoring-pattern-graph-dropdown', 'value'),
    State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
    State(temp_jobs_store_id_maker(PATTERN_TITLE), 'data'),
)
def callback_viz_selected_pattern(selected, value, pattern_jobs):
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


@ app.callback(
    Output('selected-monitoring-pattern-graph-dropdown', 'options'),
    Input(show_button_id(monitoring_load_pattern_graphs_button_title), 'n_clicks'),
    State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
    State(temp_jobs_store_id_maker(PATTERN_TITLE), 'data')
)
def add_pattern(n_load_pg, value, pattern_jobs):
    ctx = dash.callback_context
    if not ctx.triggered:
        button_id = 'No clicks yet'
        button_value = None
    else:
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        button_value = ctx.triggered[0]['value']

    if button_value is None:
        return dash.no_update

    if button_id == show_button_id(monitoring_load_pattern_graphs_button_title):
        user = request.authorization['username']
        log_hash, date = read_global_signal_value(value)
        pattern_graphs = get_remote_data(user, log_hash, pattern_jobs,
                                         AvailableTasks.DESIGN_PROBLEM_PATTERN.value)
        pattern_names = [pg.name for pg in pattern_graphs]
        pg_options = [{'label': a, 'value': a}
                      for a in pattern_names]
        return pg_options

    return dash.no_update


@ app.callback(
    Output(temp_jobs_store_id_maker(MONITORING_TITLE), 'data'),
    Output('monitoring-data-label', 'children'),
    Output('monitoring-results', 'children'),
    Output('gv-monitoring-eocpn-view-dot', 'data'),
    Input(show_button_id(monitoring_evaluate_button_title), 'n_clicks'),
    Input('upload-monitoring-data', 'contents'),
    State('upload-monitoring-data', 'filename'),
    State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
    State(temp_jobs_store_id_maker(PATTERN_TITLE), 'data'),
    State(temp_jobs_store_id_maker(MONITORING_TITLE), 'data'),
)
def monitor(n_load_pg, content, filename, value, pattern_jobs, monitoring_jobs):
    ctx = dash.callback_context
    if not ctx.triggered:
        button_id = 'No clicks yet'
        button_value = None
    else:
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        button_value = ctx.triggered[0]['value']

    if button_value is None:
        return no_update(4)

    if button_id == show_button_id(monitoring_evaluate_button_title):
        user = request.authorization['username']
        log_hash, date = read_global_signal_value(value)
        ocel = get_remote_data(user, log_hash, monitoring_jobs,
                               AvailableTasks.UPLOAD_MONITORING_DATA.value)
        print(ocel)

        task_id = run_task(
            monitoring_jobs, log_hash, AvailableTasks.DESIGN.value, discover_ocpn, data=ocel)
        ocpn = get_remote_data(user, log_hash, monitoring_jobs,
                               AvailableTasks.DESIGN.value)
        print(ocpn)
        diag_params = dict()
        diag_params['measures'] = [DIAGNOSTICS_NAME_MAP[d]
                                   for d in [e.value for e in AvailableDiagnostics]]
        diag_params['agg'] = [PERFORMANCE_AGGREGATION_NAME_MAP[a]
                              for a in [e.value for e in AvailablePerformanceAggregation]]

        task_id = run_task(
            monitoring_jobs, log_hash, AvailableTasks.OPERA.value, retrieve_eocpn, ocpn=ocpn, ocel=ocel, parameters=diag_params)
        eocpn = get_remote_data(user, log_hash, monitoring_jobs,
                                AvailableTasks.OPERA.value)
        print(eocpn)
        pattern_graphs = get_remote_data(user, log_hash, pattern_jobs,
                                         AvailableTasks.DESIGN_PROBLEM_PATTERN.value)
        task_id = run_task(
            monitoring_jobs, log_hash, AvailableTasks.EVALUATE_PATTERN.value, evaluate_pattern_graphs, pattern_graphs=pattern_graphs, ocel=ocel, eocpn=eocpn)

        results = get_remote_data(user, log_hash, monitoring_jobs,
                                  AvailableTasks.EVALUATE_PATTERN.value)
        print(results)
        monitoring_results = []
        for i, pg_name in enumerate(results):
            exist = results[pg_name][0]
            message = results[pg_name][1]
            monitoring_results.append(
                create_result_card(pg_name, exist, message))

        gviz = ocpn_vis_factory.apply(
            eocpn.ocpn, diagnostics=eocpn.diagnostics, variant="annotated_with_opera")
        eocpn_dot = str(gviz)

        return dash.no_update, dash.no_update, monitoring_results, eocpn_dot
    elif content is not None:
        user = request.authorization['username']
        log_hash, date = read_global_signal_value(value)
        # compute value and send a signal when done
        content_type, content_string = content.split(',')

        data_format = JSON
        out, success = parse_contents(content, data_format)
        if success:
            json_param = build_json_param(NA)
            task_id = run_task(pattern_jobs, log_hash, AvailableTasks.UPLOAD_MONITORING_DATA.value, parse_data,
                               data=out,
                               data_type=data_format,
                               parse_param=json_param)
        monitoring_data_label = f'Currently uploaded: {filename}'
        return pattern_jobs, monitoring_data_label, *no_update(2)

    return no_update(4)
