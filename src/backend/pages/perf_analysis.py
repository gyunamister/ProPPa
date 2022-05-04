import hashlib
import base64
import datetime
from datetime import date
import re
import sqlite3
import json

import subprocess

from backend.components.misc import container, single_row, button, show_title_maker, show_button_id, global_signal_id_maker, temp_jobs_store_id_maker, global_form_load_signal_id_maker
import dash_interactive_graphviz
from dash.dependencies import Input, Output, State
import dash_html_components as html
import dash_core_components as dcc
import dash_bootstrap_components as dbc
from backend.app import app
import dash_table
import dash
from backend.param.constants import PARSE_TITLE, DESIGN_TITLE, GLOBAL_FORM_SIGNAL, PERF_ANALYSIS_URL, PERF_ANALYSIS_TITLE

from dtween.available.constants import COMP_OPERATORS


from dtween.util.util import DIAGNOSTICS_NAME_MAP, PERFORMANCE_AGGREGATION_NAME_MAP

from backend import time_utils

from backend.util import run_task, read_global_signal_value, no_update, transform_config_to_datatable_dict
from backend.tasks.tasks import get_remote_data, analyze_opera
from dtween.available.available import AvailableTasks, AvailableDiagnostics, DefaultDiagnostics, AvailablePerformanceAggregation, AvailablePerformance, AvailableFrequency
from flask import request
from dateutil import parser
from ocpa.visualization.oc_petri_net import factory as ocpn_vis_factory
from ocpa.objects.log.converter import factory as ocel_converter_factory

import pickle
import redis
from time import sleep
from backend.param.settings import redis_pwd


refresh_title = "Refresh".title()
diagnostics_button_title = "compute".title()

available_diagonstics = [e.value for e in AvailableDiagnostics]
available_aggregations = [e.value for e in AvailablePerformanceAggregation]
default_diagonstics = [e.value for e in DefaultDiagnostics]

available_frequency = [e.value for e in AvailableFrequency]
available_performance = [e.value for e in AvailablePerformance]


def results_key(task_id):
    return f'result-{task_id}'


buttons = [
    button(refresh_title, show_title_maker, show_button_id),
]

tab1_content = dbc.Row(
    [
        dbc.Col(html.Div(id="selected-marking"), width=12),
        dbc.Col(html.Div(id='object-list'), width=12),
        dbc.Col(dash_table.DataTable(
            id='object-table',
            fixed_columns={'headers': True, 'data': 1},
            style_table={'minWidth': '100%'}
        ), width=12)
    ]

)

diagnostics_date_picker = html.Div([
    dcc.Store(id='diagnostics-start', storage_type='session', data=""),
    dcc.Store(id='diagnostics-end', storage_type='session', data=""),
    dcc.Store(id='diagnostics-duration', storage_type='session'),
    dcc.Store(id='diagnostics-list', storage_type='session'),
    html.H3('Object-Centric Performance Measures'),
    dbc.Checklist(
        id='diagnostics-checklist',
        options=[{'label': d, 'value': d} for d in available_diagonstics],
        value=[d for d in default_diagonstics],
        inline=True,
        switch=True
    ),
    html.Hr(),
    html.H3('Aggregations'),
    dbc.Checklist(
        id='aggregation-checklist',
        options=[{'label': d, 'value': d} for d in available_aggregations],
        value=[d for d in available_aggregations],
        inline=True,
        switch=True
    ),
    html.Hr(),
    html.H3('Time Period'),
    html.Div(id='output-container-date-picker-range'),
    dcc.DatePickerRange(
        id='my-date-picker-range',
        min_date_allowed=date(1995, 8, 5),
        max_date_allowed=date(2017, 9, 19),
        initial_visible_month=date(2017, 8, 5),
        end_date=date(2017, 8, 25),
        display_format='YYYY-MM-DD',
    ),
    html.Hr(),
    dbc.Col(html.Div(id="selected-marking"), width=12),
])

diagnostics_tab_content = dbc.Row(
    dbc.Col(
        [
            diagnostics_date_picker,
            button(diagnostics_button_title, show_title_maker, show_button_id)
        ]
    )
)

tabs = dbc.Tabs(
    [
        # dbc.Tab(tab1_content, label="State"),
        dbc.Tab(diagnostics_tab_content, label="Diagnostics"),
    ]
)

display = html.Div(
    id="perf-display",
    className="number-plate",
    children=[]
)

operational_view_content = dbc.Row(
    [
        dcc.Store(id='ocpn-operational-view-dot',
                  storage_type='session', data=""),
        dcc.Store(id='object-types', storage_type='session', data=[]),
        dbc.Col(
            dash_interactive_graphviz.DashInteractiveGraphviz(
                id="gv-operational-view"), width=6
        ),
        dbc.Col(
            display, width=6
        )
    ],
    # style=dict(position="absolute", height="100%",
    #            width="100%", display="flex"),
    style={'height': '100vh'}
)

cards = [
    dbc.Col(
        dbc.Card(
            [
                html.H2(f"Control-flow Patterns", className="card-title"),
                html.Hr(),
                html.H3("Existence", className="card-text"),
                dbc.Row(
                    [
                        dbc.Col(
                            dcc.Dropdown(
                                id='pattern-existence-dropdown'
                            ), width=8
                        ),
                        dbc.Col(
                            dcc.ConfirmDialogProvider(
                                children=html.Button(
                                    'Add'),
                                id='pattern-existence-provider',
                                message='Are you sure to add the existence pattern?'
                            ), width=2
                        ),
                    ],
                    align='center'
                ),
                html.Hr(),
                html.H3("Non-existence", className="card-text"),
                dbc.Row(
                    [
                        dbc.Col(
                            dcc.Input(id="input1", type="text", placeholder=""), width=8
                        ),
                        dbc.Col(
                            dcc.ConfirmDialogProvider(
                                children=html.Button(
                                    'Add'),
                                id='danger-danger-provider',
                                message='Are you sure to add the non-existence pattern?'
                            ), width=2
                        ),
                    ],
                    align='center'
                )
            ],
            body=True,
            color="light",
        ), width=3
    ),
    dbc.Col(
        dbc.Card(
            [
                html.H2(f"Object Patterns", className="card-title"),
                dbc.Row(
                    dbc.Col(
                        dcc.Dropdown(
                            id='object-pattern-activity-dropdown',
                        ), width=8
                    )
                ),
                html.Hr(),
                html.H3("Missing objects", className="card-text"),
                dbc.Row(
                    [
                        dbc.Col(
                            dcc.Dropdown(
                                id='pattern-missing-dropdown',
                                multi=True
                            ), width=8
                        ),
                        dbc.Col(
                            dcc.ConfirmDialogProvider(
                                children=html.Button(
                                    'Add'),
                                id='danger-danger-provider',
                                message='Are you sure to add the missing object pattern?'
                            ), width=2
                        ),
                    ],
                    align='center'
                ),
                html.Hr(),
                html.H3("Redundant objects", className="card-text"),
                dbc.Row(
                    [
                        dbc.Col(
                            dcc.Dropdown(
                                id='pattern-redundant-dropdown',
                                multi=True
                            ), width=8
                        ),
                        dbc.Col(
                            dcc.ConfirmDialogProvider(
                                children=html.Button(
                                    'Add'),
                                id='danger-danger-provider',
                                message='Are you sure to add the redundant object pattern?'
                            ), width=2
                        ),
                    ],
                    align='center'
                ),
                html.Hr(),
                html.H3("Duplicated objects", className="card-text"),
                dbc.Row(
                    [
                        dbc.Col(
                            dcc.Dropdown(
                                id='pattern-duplicated-dropdown',
                                multi=True
                            ), width=8
                        ),
                        dbc.Col(
                            dcc.ConfirmDialogProvider(
                                children=html.Button(
                                    'Add'),
                                id='danger-danger-provider',
                                message='Are you sure to add the duplicated object pattern?'
                            ), width=2
                        ),
                    ],
                    align='center'
                ),
            ],
            body=True,
            color="light"
        ), width=3
    ),
    dbc.Col(
        dbc.Card(
            [
                html.H2(f"Performance Patterns", className="card-title"),
                dbc.Row(
                    dbc.Col(
                        dcc.Dropdown(
                            id='performance-pattern-activity-dropdown',
                        ), width=9
                    )
                ),
                html.Hr(),
                html.H3("Frequency", className="card-text"),
                dbc.Row(
                    [
                        dbc.Col(
                            dcc.Dropdown(
                                id='pattern-frequency-agg-dropdown'
                            ), width=3
                        ),
                        dbc.Col(
                            dcc.Dropdown(
                                id='pattern-frequency-dropdown'
                            ), width=4
                        ),
                        dbc.Col(
                            dcc.Dropdown(
                                id='pattern-frequency-comp-dropdown',
                                options=[{'label': d, 'value': d}
                                         for d in COMP_OPERATORS],
                            ), width=1
                        ),
                        dbc.Col(
                            dcc.Input(id="input3", type="number", placeholder=0, style={'width': '70%'}), width=2
                        ),
                        dbc.Col(
                            dcc.ConfirmDialogProvider(
                                children=html.Button(
                                    'Add'),
                                id='pattern-frequency-provider',
                                message='Are you sure to add the frequency pattern?'
                            ), width=1
                        ),
                    ],
                    align='center',
                    justify='start'
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            dcc.Dropdown(
                                id='pattern-frequency-obj-dropdown'
                            ), width=6
                        )
                    ],
                    align='center'
                ),
                html.Hr(),
                html.H3("Performance", className="card-text"),
                dbc.Row(
                    [
                        dbc.Col(
                            dcc.Dropdown(
                                id='pattern-performance-agg-dropdown'
                            ), width=3
                        ),
                        dbc.Col(
                            dcc.Dropdown(
                                id='pattern-performance-dropdown'
                            ), width=4
                        ),
                        dbc.Col(
                            dcc.Dropdown(
                                id='pattern-performance-comp-dropdown',
                                options=[{'label': d, 'value': d}
                                         for d in COMP_OPERATORS],
                            ), width=1
                        ),
                        dbc.Col(
                            dcc.Input(id="input2", type="number", placeholder=0, style={'width': '70%'}), width=2),
                        dbc.Col(
                            dcc.ConfirmDialogProvider(
                                children=html.Button(
                                    'Add'),
                                id='pattern-performance-provider',
                                message='Are you sure to add the performance pattern?'
                            ), width=1
                        ),
                    ],
                    align='center',
                    justify='start'
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            dcc.Dropdown(
                                id='pattern-performance-obj-dropdown'
                            ), width=6
                        )
                    ],
                    align='center'
                ),
            ],
            body=True,
            color="light"
        ), width=6
    )
]

page_layout = container('Designing Problem Patterns',
                        [
                            single_row(html.Div(buttons)),
                            html.Hr(),
                            diagnostics_tab_content,
                            html.Hr(),
                            dbc.Row(cards),
                            html.Hr(),
                            operational_view_content
                        ]
                        )


@ app.callback(
    Output("gv-operational-view", "dot_source"),
    Output("gv-operational-view", "engine"),
    Input('url', 'pathname'),
    Input("ocpn-operational-view-dot", "data")
)
def show_ocpn(pathname, value):
    if pathname == PERF_ANALYSIS_URL and value is not None:
        return value, "dot"
    return no_update(2)


@ app.callback(
    Output(temp_jobs_store_id_maker(PERF_ANALYSIS_TITLE), 'data'),
    Output('ocpn-operational-view-dot', 'data'),
    Output('object-types', 'data'),
    Output("my-date-picker-range", "min_date_allowed"),
    Output("my-date-picker-range", "max_date_allowed"),
    Output("my-date-picker-range", "initial_visible_month"),
    Output("my-date-picker-range", "start_date"),
    Output("my-date-picker-range", "end_date"),
    Input(show_button_id(refresh_title), 'n_clicks'),
    Input(show_button_id(diagnostics_button_title), 'n_clicks'),
    State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
    State(temp_jobs_store_id_maker(PARSE_TITLE), 'data'),
    State(temp_jobs_store_id_maker(DESIGN_TITLE), 'data'),
    State(temp_jobs_store_id_maker(PERF_ANALYSIS_TITLE), 'data'),
    State('diagnostics-start', 'data'),
    State('diagnostics-end', 'data'),
    State('diagnostics-checklist', 'value'),
    State('aggregation-checklist', 'value'),
)
def load_ocpn(n_load, n_diagnosis, value, data_jobs, design_jobs, perf_jobs, start_date, end_date, diagnostics_list, aggregation_list):
    ctx = dash.callback_context
    if not ctx.triggered:
        button_id = 'No clicks yet'
    else:
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        button_value = ctx.triggered[0]['value']

    if button_id == show_button_id(refresh_title):
        user = request.authorization['username']
        log_hash, date = read_global_signal_value(value)
        data = get_remote_data(user, log_hash, data_jobs,
                               AvailableTasks.PARSE.value)
        eve_df, obj_df = ocel_converter_factory.apply(data)
        min_date = min(eve_df['event_timestamp']).to_pydatetime().date()
        max_date = max(eve_df['event_timestamp']).to_pydatetime().date()
        return dash.no_update, dash.no_update, dash.no_update, min_date, max_date, max_date, min_date, max_date

    elif button_id == show_button_id(diagnostics_button_title):
        user = request.authorization['username']
        log_hash, date = read_global_signal_value(value)
        data = get_remote_data(user, log_hash, data_jobs,
                               AvailableTasks.PARSE.value)
        eve_df, obj_df = ocel_converter_factory.apply(data)
        # +1 day to consider the selected end date
        start_date = parser.parse(start_date).date()
        end_date = parser.parse(end_date).date()
        end_date += datetime.timedelta(days=1)

        ocpn = get_remote_data(user, log_hash, design_jobs,
                               AvailableTasks.DESIGN.value)

        object_types = ocpn.object_types
        # task_id = run_task(
        #     design_jobs, log_hash, AvailableTasks.DIAGNIZE.value, generate_diagnostics, ocpn=ocpn, data=eve_df, start_date=start_date, end_date=end_date)
        # diagnostics = get_remote_data(user, log_hash, design_jobs,
        #                               AvailableTasks.DIAGNIZE.value)
        diag_params = dict()
        diag_params['measures'] = [DIAGNOSTICS_NAME_MAP[d]
                                   for d in diagnostics_list]
        diag_params['agg'] = [PERFORMANCE_AGGREGATION_NAME_MAP[a]
                              for a in aggregation_list]

        task_id = run_task(
            design_jobs, log_hash, AvailableTasks.OPERA.value, analyze_opera, ocpn=ocpn, data=eve_df, parameters=diag_params)
        diagnostics = get_remote_data(user, log_hash, design_jobs,
                                      AvailableTasks.OPERA.value)

        # diagnostics = performance_factory.apply(
        #     ocpn, eve_df, parameters=diag_params)

        diag_params['format'] = 'svg'

        gviz = ocpn_vis_factory.apply(
            ocpn, diagnostics=diagnostics, variant="annotated_with_opera", parameters=diag_params)
        ocpn_diagnostics_dot = str(gviz)
        return design_jobs, ocpn_diagnostics_dot, object_types, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    return no_update(8)


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
    Output("perf-display", "children"),
    Output("pattern-existence-dropdown", "value"),
    Output("object-pattern-activity-dropdown", "value"),
    Output("performance-pattern-activity-dropdown", "value"),
    Input("gv-operational-view", "selected_node"),
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
        diagnostics = get_remote_data(user, log_hash, perf_jobs,
                                      AvailableTasks.OPERA.value)
        selected_diag = diagnostics[selected]

        plate_frames = [html.H3(f"Performance @ {selected}")]
        if 'group_size_hist' in selected_diag:
            plate_frames.append(create_2d_plate(
                'Number of objects', selected_diag['group_size_hist']))
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


def awrite(writer, data):
    writer.write(data)
    # await writer.drain()
    writer.flush()


def group_item(name, index):
    return dbc.ListGroupItem(name, id={"type": "object-item", "index": index}, n_clicks=0, action=True)


@ app.callback(
    Output('output-container-date-picker-range', 'children'),
    Output('diagnostics-start', 'data'),
    Output('diagnostics-end', 'data'),
    Input('my-date-picker-range', 'start_date'),
    Input('my-date-picker-range', 'end_date')
)
def update_output(start_date, end_date):
    string_prefix = ''
    start_date_string = ""
    end_date_string = ""
    if start_date is not None:
        # start_date_object = date.fromisoformat(start_date)
        # start_date_string = start_date_object.strftime('%B %d, %Y')
        start_date_object = date.fromisoformat(start_date)
        start_date_string = start_date_object.strftime('%Y-%m-%d')
        string_prefix = string_prefix + 'Start Date: ' + start_date_string + ' | '
    if end_date is not None:
        end_date_object = date.fromisoformat(end_date)
        end_date_string = end_date_object.strftime('%Y-%m-%d')
        string_prefix = string_prefix + 'End Date: ' + end_date_string
    if len(string_prefix) == len('You have selected: '):
        return 'Select a date to see it displayed here', start_date_string, end_date_string
    else:
        return string_prefix, start_date_string, end_date_string


@ app.callback(Output('output-provider', 'children'),
               Input('pattern-existence-provider', 'submit_n_clicks'))
def add_constraints(submit_n_clicks):
    if not submit_n_clicks:
        return ''
    return """
        It was dangerous but we did it!
        Submitted {} times
    """.format(submit_n_clicks)


@ app.callback(
    Output('pattern-existence-dropdown', 'options'),
    Output("object-pattern-activity-dropdown", "options"),
    Output("performance-pattern-activity-dropdown", "options"),
    Output('pattern-frequency-dropdown', 'options'),
    Output('pattern-frequency-agg-dropdown', 'options'),
    Output('pattern-performance-dropdown', 'options'),
    Output('pattern-performance-agg-dropdown', 'options'),
    Input(show_button_id(refresh_title), 'n_clicks'),
    Input(show_button_id(diagnostics_button_title), 'n_clicks'),
    State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
    State(temp_jobs_store_id_maker(PARSE_TITLE), 'data'),
    State(temp_jobs_store_id_maker(DESIGN_TITLE), 'data'),
    State(temp_jobs_store_id_maker(PERF_ANALYSIS_TITLE), 'data'),
    State('diagnostics-start', 'data'),
    State('diagnostics-end', 'data'),
    State('diagnostics-checklist', 'value'),
    State('aggregation-checklist', 'value'),
)
def refresh_patterns(n_load, n_diagnosis, value, data_jobs, design_jobs, perf_jobs, start_date, end_date, diagnostics_list, aggregation_list):
    ctx = dash.callback_context
    if not ctx.triggered:
        button_id = 'No clicks yet'
    else:
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        button_value = ctx.triggered[0]['value']

    if button_id == show_button_id(refresh_title):
        user = request.authorization['username']
        log_hash, date = read_global_signal_value(value)
        data = get_remote_data(user, log_hash, data_jobs,
                               AvailableTasks.PARSE.value)
        eve_df, obj_df = ocel_converter_factory.apply(data)
        # +1 day to consider the selected end date
        start_date = parser.parse(start_date).date()
        end_date = parser.parse(end_date).date()
        end_date += datetime.timedelta(days=1)

        ocpn = get_remote_data(user, log_hash, design_jobs,
                               AvailableTasks.DESIGN.value)

        object_types = ocpn.object_types
        activities = [t.name for t in ocpn.transitions]
        dropdown_activities = [{'label': a, 'value': a} for a in activities]
        dropdown_object_types = [{'label': a, 'value': a}
                                 for a in object_types]
        dropdown_aggregations = [{'label': a, 'value': a}
                                 for a in available_aggregations]
        dropdown_performance = [{'label': a, 'value': a}
                                for a in available_performance]
        dropdown_frequency = [{'label': a, 'value': a}
                              for a in available_frequency]

        diagnostics = get_remote_data(user, log_hash, design_jobs,
                                      AvailableTasks.OPERA.value)

        return dropdown_activities, dropdown_activities, dropdown_activities, dropdown_frequency, dropdown_aggregations, dropdown_performance, dropdown_aggregations

    return no_update(7)


@ app.callback(
    Output('pattern-missing-dropdown', 'options'),
    Output('pattern-redundant-dropdown', 'options'),
    Output('pattern-duplicated-dropdown', 'options'),
    Input('object-pattern-activity-dropdown', 'value'),
    State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
    State(temp_jobs_store_id_maker(DESIGN_TITLE), 'data'),
    State(temp_jobs_store_id_maker(PERF_ANALYSIS_TITLE), 'data'),
)
def update_patterns(selected_activity, value, design_jobs, perf_jobs):

    if selected_activity is not None:
        user = request.authorization['username']
        log_hash, date = read_global_signal_value(value)

        ocpn = get_remote_data(user, log_hash, design_jobs,
                               AvailableTasks.DESIGN.value)

        selected_tr = ocpn.find_transition(selected_activity)

        object_types = ocpn.object_types
        related_object_types = [
            a.source.object_type for a in selected_tr.in_arcs]
        unrelated_object_types = [
            x for x in object_types if x not in related_object_types]
        print(unrelated_object_types)
        dropdown_unrelated_object_types = [
            {'label': a, 'value': a} for a in unrelated_object_types]
        dropdown_related_object_types = [{'label': a, 'value': a}
                                         for a in related_object_types]

        return dropdown_unrelated_object_types, dropdown_related_object_types, dropdown_related_object_types

    return no_update(3)


@ app.callback(
    Output('pattern-frequency-obj-dropdown', 'options'),
    Output('pattern-frequency-obj-dropdown', 'disable'),
    Input('pattern-frequency-dropdown', 'value'),
    State('performance-pattern-activity-dropdown', 'value'),
    State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
    State(temp_jobs_store_id_maker(DESIGN_TITLE), 'data'),
    State(temp_jobs_store_id_maker(PERF_ANALYSIS_TITLE), 'data'),
)
def update_objs(selected_freq, selected_activity, value, design_jobs, perf_jobs):

    if selected_freq is not None:
        user = request.authorization['username']
        log_hash, date = read_global_signal_value(value)

        ocpn = get_remote_data(user, log_hash, design_jobs,
                               AvailableTasks.DESIGN.value)

        selected_tr = ocpn.find_transition(selected_activity)
        related_object_types = [
            a.source.object_type for a in selected_tr.in_arcs]
        dropdown_related_object_types = [{'label': a, 'value': a}
                                         for a in related_object_types]

        if selected_freq in [DefaultDiagnostics.GROUP_SIZE.value]:
            return dropdown_related_object_types, False
        else:
            return dash.no_update, True

    return no_update(2)


@ app.callback(
    Output('pattern-performance-obj-dropdown', 'options'),
    Output('pattern-performance-obj-dropdown', 'disable'),
    Input('pattern-performance-dropdown', 'value'),
    State('performance-pattern-activity-dropdown', 'value'),
    State(global_form_load_signal_id_maker(GLOBAL_FORM_SIGNAL), 'children'),
    State(temp_jobs_store_id_maker(DESIGN_TITLE), 'data'),
    State(temp_jobs_store_id_maker(PERF_ANALYSIS_TITLE), 'data'),
)
def update_objs(selected_perf, selected_activity, value, design_jobs, perf_jobs):

    if selected_perf is not None:
        user = request.authorization['username']
        log_hash, date = read_global_signal_value(value)

        ocpn = get_remote_data(user, log_hash, design_jobs,
                               AvailableTasks.DESIGN.value)

        selected_tr = ocpn.find_transition(selected_activity)
        related_object_types = [
            a.source.object_type for a in selected_tr.in_arcs]
        dropdown_related_object_types = [{'label': a, 'value': a}
                                         for a in related_object_types]

        if selected_perf in [DefaultDiagnostics.POOLING_TIME.value, DefaultDiagnostics.LAGGING_TIME.value]:
            return dropdown_related_object_types, False
        else:
            return dash.no_update, True

    return no_update(2)
