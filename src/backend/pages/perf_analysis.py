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
from backend.param.constants import PARSE_TITLE, DESIGN_TITLE, GLOBAL_FORM_SIGNAL, PERF_ANALYSIS_URL, PERF_ANALYSIS_TITLE

from dtween.available.constants import COMP_OPERATORS


from dtween.util.util import DIAGNOSTICS_NAME_MAP, PERFORMANCE_AGGREGATION_NAME_MAP

from backend.util import run_task, read_global_signal_value, no_update, create_2d_plate, create_3d_plate
from backend.tasks.tasks import get_remote_data, retrieve_eocpn, add_pattern_graph
from dtween.available.available import AvailableTasks, AvailableDiagnostics, DefaultDiagnostics, AvailablePerformanceAggregation, AvailablePerformance, AvailableFrequency
from flask import request
from dateutil import parser
from ocpa.visualization.oc_petri_net import factory as ocpn_vis_factory
from ocpa.objects.log.converter import factory as ocel_converter_factory


diagnostics_refresh_button_title = "Refresh performance analysis".title()
diagnostics_compute_button_title = "compute".title()

available_diagonstics = [e.value for e in AvailableDiagnostics]
available_aggregations = [e.value for e in AvailablePerformanceAggregation]
default_diagonstics = [e.value for e in DefaultDiagnostics]

available_frequency = [e.value for e in AvailableFrequency]
available_performance = [e.value for e in AvailablePerformance]


diagnostics_buttons = [
    button(diagnostics_refresh_button_title, show_title_maker, show_button_id),
    button(diagnostics_compute_button_title, show_title_maker, show_button_id)
]

diagnostics_parameters = html.Div([
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

page_layout = container('Designing Problem Patterns',
                        [
                            single_row(html.Div(diagnostics_buttons)),
                            html.Hr(),
                            diagnostics_parameters,
                            html.Hr(),
                            operational_view_content,
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
    Output("my-date-picker-range", "min_date_allowed"),
    Output("my-date-picker-range", "max_date_allowed"),
    Output("my-date-picker-range", "initial_visible_month"),
    Output("my-date-picker-range", "start_date"),
    Output("my-date-picker-range", "end_date"),
    Input(show_button_id(diagnostics_refresh_button_title), 'n_clicks'),
    Input(show_button_id(diagnostics_compute_button_title), 'n_clicks'),
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

    if button_id == show_button_id(diagnostics_refresh_button_title):
        user = request.authorization['username']
        log_hash, date = read_global_signal_value(value)
        data = get_remote_data(user, log_hash, data_jobs,
                               AvailableTasks.PARSE.value)
        eve_df, obj_df = ocel_converter_factory.apply(data)
        min_date = min(eve_df['event_timestamp']).to_pydatetime().date()
        max_date = max(eve_df['event_timestamp']).to_pydatetime().date()
        return dash.no_update, dash.no_update, min_date, max_date, max_date, min_date, max_date

    elif button_id == show_button_id(diagnostics_compute_button_title):
        user = request.authorization['username']
        log_hash, date = read_global_signal_value(value)
        ocel = get_remote_data(user, log_hash, data_jobs,
                               AvailableTasks.PARSE.value)
        # eve_df, obj_df = ocel_converter_factory.apply(data)
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
            design_jobs, log_hash, AvailableTasks.OPERA.value, retrieve_eocpn, ocpn=ocpn, ocel=ocel, parameters=diag_params)
        eocpn = get_remote_data(user, log_hash, design_jobs,
                                AvailableTasks.OPERA.value)

        # diagnostics = performance_factory.apply(
        #     ocpn, eve_df, parameters=diag_params)

        gviz = ocpn_vis_factory.apply(
            eocpn.ocpn, diagnostics=eocpn.diagnostics, variant="annotated_with_opera", parameters=diag_params)
        ocpn_diagnostics_dot = str(gviz)
        return design_jobs, ocpn_diagnostics_dot, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    return no_update(7)


@ app.callback(
    Output("perf-display", "children"),
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
        eocpn = get_remote_data(user, log_hash, perf_jobs,
                                AvailableTasks.OPERA.value)
        selected_diag = eocpn.diagnostics[selected]

        plate_frames = [html.H3(f"Performance @ {selected}")]
        if 'group_size_hist' in selected_diag:
            plate_frames.append(create_2d_plate(
                'Number of objects', selected_diag['group_size_hist'], time_measure=False))
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
