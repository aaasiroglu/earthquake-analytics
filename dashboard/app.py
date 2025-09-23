import dash
from dash import dcc, html, Input, Output
import requests
import pandas as pd
import plotly.express as px

API_URL = "http://localhost:8000/earthquakes"

# İlk veri çekme
def get_data(source="all"):
    r = requests.get(f"{API_URL}?source={source}")
    df = pd.DataFrame(r.json())
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"])
    return df

app = dash.Dash(__name__)

df = get_data()

app.layout = html.Div([
    html.H1("Deprem Analytics Dashboard"),
    html.Div([
        html.Label("Veri Kaynağı"),
        dcc.Dropdown(
            id="source-dropdown",
            options=[
                {"label": "Hepsi (USGS+AFAD)", "value": "all"},
                {"label": "USGS", "value": "usgs"},
                {"label": "AFAD", "value": "afad"},
            ],
            value="all",
            clearable=False
        ),
        html.Label("Şehir/yer seçimi (örnek)"),
        dcc.Dropdown(
            id="place-dropdown",
            options=[{"label": "Tümü", "value": "all"}] + [
                {"label": p, "value": p} for p in sorted(df["place"].dropna().unique())
            ],
            value="all"
        ),
        html.Label("Büyüklük filtresi"),
        dcc.Slider(
            id="mag-slider",
            min=0,
            max=8,
            value=0,
            marks={i: str(i) for i in range(0, 9)},
            step=0.1
        ),
    ], style={"width": "25%", "display": "inline-block", "vertical-align": "top"}),
    html.Div([
        dcc.Graph(id="map-graph"),
        html.Label("Zaman Aralığı"),
        dcc.RangeSlider(
            id="time-slider",
            min=0, max=len(df)-1,
            value=[0, len(df)-1],
            marks={
                i: df.iloc[i]["time"].strftime("%Y-%m-%d")
                for i in range(0, len(df), max(len(df)//10, 1))
            } if not df.empty else {},
            allowCross=False
        ),
        dcc.Graph(id="timeline-graph")
    ], style={"width": "70%", "display": "inline-block", "padding": "0 20"})
])

@app.callback(
    Output("map-graph", "figure"),
    Output("timeline-graph", "figure"),
    Output("place-dropdown", "options"),
    Output("time-slider", "min"),
    Output("time-slider", "max"),
    Output("time-slider", "value"),
    Output("time-slider", "marks"),
    Input("source-dropdown", "value"),
    Input("place-dropdown", "value"),
    Input("mag-slider", "value"),
    Input("time-slider", "value")
)
def update_dashboard(source, place, min_mag, time_range):
    df = get_data(source)
    if df.empty:
        return {}, {}, [{"label": "Tümü", "value": "all"}], 0, 0, [0, 0], {}

    places = [{"label": "Tümü", "value": "all"}] + [
        {"label": p, "value": p} for p in sorted(df["place"].dropna().unique())
    ]
    if place != "all":
        df = df[df["place"] == place]
    df = df[df["mag"] >= min_mag]
    df = df.sort_values("time").reset_index(drop=True)
    min_idx, max_idx = 0, len(df)-1
    marks = {
        i: df.iloc[i]["time"].strftime("%Y-%m-%d")
        for i in range(0, len(df), max(len(df)//10, 1))
    } if not df.empty else {}
    # Zaman sliderı ile filtre
    if isinstance(time_range, list) and len(time_range) == 2 and not df.empty:
        df = df.iloc[time_range[0]:time_range[1]+1]
    # Harita
    fig_map = px.scatter_mapbox(
        df, lat="lat", lon="lon", color="mag", size="mag",
        hover_data=["place", "mag", "time", "source"], zoom=3,
        mapbox_style="open-street-map"
    )
    # Zaman serisi
    timeline = df.groupby(df["time"].dt.date).size()
    fig_timeline = px.line(x=timeline.index, y=timeline.values, labels={'x': 'Tarih', 'y': 'Deprem Adedi'})
    return fig_map, fig_timeline, places, min_idx, max_idx, [min_idx, max_idx], marks

if __name__ == "__main__":
    app.run_server(debug=True)