# Import client to access the Open-Meteo weather API service
import openmeteo_requests
# Import pandas for data manipulation and tabular structuring
import pandas as pd
# Caches API responses to reduce redundant calls and improve speed
import requests_cache
# Automatically retries failed API requests for resilience
from retry_requests import retry
# Dash components for building the web interface (charts, inputs, layout)
from dash import Dash, html, dcc, Input, Output, State, dash_table
# Bootstrap components for responsive, styled UI layout
import dash_bootstrap_components as dbc
# Used for creating interactive visualizations (e.g., line charts)
import plotly.graph_objects as go # For plotting temperature trends

import logging

logging.basicConfig(
    filename='api_pull.log',  # Log file name
    level=logging.INFO,       # Log level
    format='%(asctime)s - %(levelname)s - %(message)s'  # Log format
)

# Setup Open-Meteo API
# Cache data for 24 hours (3600 seconds * 24)
# Cache API data for 24 hours to prevent repeated API calls
cache_session = requests_cache.CachedSession('.cache', expire_after=3600 * 24)
# Set up automatic retries with a small delay for reliability
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
# Create a weather API client using the retry-enabled session
openmeteo = openmeteo_requests.Client(session=retry_session)

# City coordinates and display names
# Predefined city metadata with coordinates and image URLs for UI display
city_info = {
    "Honolulu": {"coords": (21.31, -157.86), "display_name": "Honolulu, HI",
                 "image_url": "/assets/honolulu.jpg"},
    "New York": {"coords": (40.71, -74.01), "display_name": "New York, NY",
                 "image_url": "/assets/new_york.jpg"},
    "Chicago": {"coords": (41.88, -87.63), "display_name": "Chicago, IL",
                "image_url": "/assets/chicago.jpg"},
    "San Francisco": {"coords": (37.77, -122.42), "display_name": "San Francisco, CA",
                      "image_url": "/assets/san_francisco.jpg"}
}

# Helper functions
# Returns the correct ordinal suffix for a given day (e.g., '1st', '2nd')
def suffix(day):
    return (
        "st" if day % 10 == 1 and day != 11 else
        "nd" if day % 10 == 2 and day != 12 else
        "rd" if day % 10 == 3 and day != 13 else
        "th"
    )

# Format datetime object into a readable label with day suffix
def format_date(d):
    return d.strftime('%A, %B ') + str(d.day) + suffix(d.day)

# Map Open-Meteo weather codes to descriptive emojis and text
def get_weather_icon(code):
    code = int(code)
    if code == 0: return "☀️ Sunny"
    elif code == 1: return "🌤️ Mostly Clear"
    elif code == 2: return "⛅ Partly Cloudy"
    elif code == 3: return "☁️ Cloudy"
    elif code in [45, 48]: return "🌫️ Fog"
    elif 51 <= code <= 67: return "🌦️ Rain/Drizzle"
    elif 71 <= code <= 77: return "❄️ Snow"
    elif 80 <= code <= 82: return "🌧️ Showers"
    elif 95 <= code <= 99: return "⛈️ Thunderstorm"
    else: return "🌈"

# Fetches and processes 7-day forecast data for the selected city
def get_city_data(city_key):
    lat, lon = city_info[city_key]["coords"]
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": [
            "temperature_2m_max", "temperature_2m_min",
            "rain_sum", "wind_speed_10m_max", "weather_code"
        ],
        "timezone": "auto", "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch", "wind_speed_unit": "mph"
    }
    logging.info(f"Pulling weather data for {city_key} at lat/lon: {lat}, {lon}")
    responses = openmeteo.weather_api(url, params=params)
    response = responses[0]
    daily = response.Daily()
    timezone_str = response.Timezone().decode('utf-8')
    dates = pd.date_range(
        start=pd.to_datetime(daily.Time(), unit="s", utc=True).tz_convert(timezone_str),
        end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True).tz_convert(timezone_str),
        freq=pd.Timedelta(seconds=daily.Interval()), inclusive="left"
    )
    date_labels = [format_date(d) for d in dates]
    weather_descriptions = [get_weather_icon(code) for code in daily.Variables(4).ValuesAsNumpy().astype(int)]

    df = pd.DataFrame({
        "Date": date_labels,
        "Max Temp (°F)": daily.Variables(0).ValuesAsNumpy().round().astype(int),
        "Min Temp (°F)": daily.Variables(1).ValuesAsNumpy().round().astype(int),
        "Rain (in)": daily.Variables(2).ValuesAsNumpy().round(2),
        "Wind (mph)": daily.Variables(3).ValuesAsNumpy().round().astype(int),
        "Weather Code": daily.Variables(4).ValuesAsNumpy().astype(int),
        "Description": weather_descriptions
    })
    return df

# Generates summary metric cards (temp, rain, wind) for the next 3 days
def create_metric_cards(city_key):
    city_df_full = get_city_data(city_key)
    df = city_df_full.head(3)
    dates = list(df["Date"])

    date_cards = dbc.Row([
        dbc.Col(dbc.Card([dbc.CardBody([html.H4(date, className="card-title", style={"textAlign": "center", "fontSize": "1.25rem", "margin": "0"})])
        ], style={"height": "80px", "margin": "5px", "textAlign": "center"}), width=4) for date in dates
    ], justify="center")

    weather_row = [
        dbc.Card([dbc.CardBody([html.Div(df.iloc[i]["Description"], style={"fontSize": "1.5rem", "margin": "0.5rem 0", "textAlign": "center"})])
        ], style={"width": "100%", "margin": "5px"}) for i in range(3)
    ]
    forecast_row = dbc.Row([dbc.Col(card, width=4) for card in weather_row], justify="center")

    metrics = [
        ("Max Temp (°F)", "Max Temp (°F)", "°F", "🌡️"),
        ("Rain (in)", "Rain (in)", "in", "💧"),
        ("Wind (mph)", "Wind (mph)", "mph", "🌬️")
    ]
    rows = []
    for display_metric, col_metric, unit, icon in metrics:
        row_items = [
            dbc.Card([dbc.CardBody([
                html.H5(display_metric, className="card-subtitle"),
                html.H2(
    f"{df.iloc[i][col_metric]:.2f} {unit}" if display_metric == "Rain (in)"
    else f"{df.iloc[i][col_metric]} {unit if display_metric != 'Max Temp (°F)' else ''}",
    style={"fontSize": "1.5rem", "marginTop": "0.5rem"}
),                
                html.Div(icon, style={"fontSize": "1.5rem", "marginTop": "0.5rem"})
            ])], style={"width": "100%", "margin": "5px"}) for i in range(3)
        ]
        rows.append(dbc.Row([dbc.Col(card, width=4) for card in row_items], justify="center"))
    return html.Div([date_cards, forecast_row] + rows)

# Unique identifier for the summary page container in Dash
summary_page_content_id = 'summary-page-content-wrapper'
# Unique identifier for the summary page container in Dash
summary_layout = html.Div(id=summary_page_content_id, children=[
    html.H2("City 3-Day Forecast Summary", style={"textAlign": "center", "marginTop": "20px", "color": "white", "textShadow": "1px 1px 2px black"}), # Added text shadow
    html.Div([dcc.Link("← Back to Detailed Forecast", href="/", style={"marginLeft": "20px", "color": "lightblue", "fontWeight": "bold"})]), # Made link bolder
    html.Br(),
    html.Div([
        dcc.Dropdown(
            id='city-dropdown-summary',
            options=[{"label": city_info[key]["display_name"], "value": key} for key in city_info],
            value="Honolulu", clearable=False, style={'width': '300px', 'margin': '0 auto'}
        )], style={'textAlign': 'center'}),
    html.Br(),
    html.Div(id='summary-cards', style={"marginTop": "30px", "padding": "0 40px", "backgroundColor": "rgba(0,0,0,0.3)", "borderRadius": "10px"}) # Darker semi-transparent bg for cards
], style={
    "padding": "20px", "minHeight": "100vh", "backgroundSize": "cover",
    "backgroundPosition": "center", "transition": "background-image 0.5s ease-in-out"
})

# Unique ID for detailed forecast section
detailed_forecast_page_content_id = 'detailed-forecast-page-content'
# Define a generic background image URL for the detailed forecast page
detailed_forecast_background_url = "/assets/blue_sky.jpg"

# Layout for the 7-day detailed forecast page, including dropdown, chart, and table
def detailed_forecast_layout():
# Unique ID for detailed forecast section
    return html.Div(id=detailed_forecast_page_content_id, children=[
        # Applied style for background image here
        html.H2("7-Day Detailed Weather Forecast", style={"textAlign": "center", "marginTop": "20px", "color": "white", "textShadow": "1px 1px 2px black"}),
        html.Div([
            dcc.Link("→ Go to 3-Day City Summary", href="/summary", style={"marginLeft": "20px", "color": "lightblue", "fontWeight": "bold"})
        ]),
        html.Br(),
        dcc.Dropdown(
            id='city-dropdown-detailed',
            options=[{"label": city_info[key]["display_name"], "value": key} for key in city_info],
            value="Honolulu",
            clearable=False,
            style={'width': '300px', 'margin': '10px auto'}
        ),
        # Wrap graph and table in a div with some background for readability
        html.Div([
            dcc.Graph(id='temp-trend-graph'),
            html.Div(id='detailed-forecast-table-div')
        ], style={"backgroundColor": "rgba(255,255,255,0.8)", "padding": "20px", "borderRadius": "10px", "marginTop": "20px"})

    ], style={ # Style for the main page container
        "padding": "20px",
        "minHeight": "100vh",
        "backgroundImage": f'url("{detailed_forecast_background_url}")',
        "backgroundSize": "cover",
        "backgroundPosition": "center"
    })

# Initialize Dash app with Bootstrap styling and support for routing
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
# Define the global layout: router, dynamic content, and refresh trigger
app.layout = html.Div([
    dcc.Location(id='url'),
    html.Div(id='page-content'),
    dcc.Interval(id='interval-component', interval=24*60*60*1000, n_intervals=0)
])

@app.callback(Output('page-content', 'children'), Input('url', 'pathname'))
# Handles page routing between the summary and detailed forecast pages
def display_page(pathname):
    if pathname == "/summary":
        return summary_layout
    return detailed_forecast_layout()

@app.callback(
# Unique identifier for the summary page container in Dash
    [Output('summary-cards', 'children'), Output(summary_page_content_id, 'style')],
    Input('city-dropdown-summary', 'value'),
# Unique identifier for the summary page container in Dash
    State(summary_page_content_id, 'style')
)
# Updates the 3-day card layout and background based on city selection
def update_city_summary(city_key, current_style):
    cards = create_metric_cards(city_key)
    image_url = city_info[city_key]["image_url"]
    new_style = current_style.copy()
    new_style['backgroundImage'] = f'url("{image_url}")'
    return cards, new_style

@app.callback(
    [Output('temp-trend-graph', 'figure'), Output('detailed-forecast-table-div', 'children')],
    Input('city-dropdown-detailed', 'value'),
    Input('interval-component', 'n_intervals')
)
# Updates the temperature trend chart and 7-day data table
def update_detailed_forecast(city_key, n_intervals):
    print(f"Updating detailed forecast for {city_info[city_key]['display_name']} due to dropdown or interval (n={n_intervals})")
    df_city = get_city_data(city_key)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_city["Date"], y=df_city["Max Temp (°F)"], name='Max Temp', mode='lines+markers'))
    fig.add_trace(go.Scatter(x=df_city["Date"], y=df_city["Min Temp (°F)"], name='Min Temp', mode='lines+markers'))
    fig.update_layout(
        title=f'7-day Temperature Trend for {city_info[city_key]["display_name"]}',
        xaxis_title='Date', yaxis_title='Temperature (°F)',
        legend_title_text='Temperature',
        paper_bgcolor='rgba(0,0,0,0)', # Transparent background for graph
        plot_bgcolor='rgba(0,0,0,0)',  # Transparent background for plot area
        font=dict(color="black") # Ensure graph text is readable on a light bg (from the semi-transparent div)
    )

    table_df = df_city[["Date", "Description", "Rain (in)", "Wind (mph)"]].copy()
    table_df["Rain (in)"] = table_df["Rain (in)"].round(2)
    detailed_table = dash_table.DataTable(
        data=table_df.to_dict("records"),
        columns=[
    {"name": "Date", "id": "Date"},
    {"name": "Description", "id": "Description"},
    {"name": "Rain (in)", "id": "Rain (in)", "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "Wind (mph)", "id": "Wind (mph)"}
],
        style_table={'overflowX': 'auto', 'padding': '10px', 'marginTop': '20px'},
        style_cell={'textAlign': 'left', 'padding': '8px', 'fontFamily': 'Arial', 'fontSize': '14px', 'backgroundColor': 'white'}, # Ensure cells have solid bg
        style_header={'backgroundColor': '#f2f2f2', 'fontWeight': 'bold', 'color': 'black'} # Ensure header text is visible
    )
    return fig, html.Div([
        html.H4(f"7-Day Forecast Details for {city_info[city_key]['display_name']}", style={"textAlign": "center", "marginTop": "20px", "color": "black"}), # Changed color for readability
        detailed_table
        ])

# Start the Dash app and ensure the cache is closed on exit
if __name__ == '__main__':
    try:
        app.run(debug=True)
    finally:
        if 'cache_session' in globals() and cache_session:
            cache_session.close()