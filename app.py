# -*- coding: utf-8 -*-
import dash
from dash import dcc, html, dash_table, Input, Output, clientside_callback, ctx, Patch
import dash_leaflet as dl
import dash_bootstrap_components as dbc
import pandas as pd
import os
import plotly.express as px
import requests
import datetime
import time

# POBIERACZ DANYCH Z GIOŚ
def pobierz_dzisiejsze_dane():
    file_path = 'baza_powietrza_polska3.csv'
    dzisiejsza_data = datetime.date.today().strftime('%Y-%m-%d')
    
    if os.path.exists(file_path):
        try:
            df_check = pd.read_csv(file_path)
            if 'date' in df_check.columns and dzisiejsza_data in df_check['date'].values:
                return "Aktualne dane są już pobrane."
        except Exception:
            pass 

    print("\n--- ROZPOCZĘTO POBIERANIE W TLE (CAŁA POLSKA) ---")
    API_BASE = "https://api.gios.gov.pl/pjp-api/v1/rest"
    HEADERS = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    def wyciagnij_liste(dane):
        if isinstance(dane, list): return dane
        if isinstance(dane, dict):
            for k, v in dane.items():
                if isinstance(v, list): return v
        return []

    def znajdz_wartosc(slownik, fragmenty):
        if not isinstance(slownik, dict): return None
        for k, v in slownik.items():
            k_lower = str(k).lower()
            if any(frag in k_lower for frag in fragmenty):
                if v is not None and str(v).strip() != "" and not isinstance(v, (dict, list)):
                    return v
            if isinstance(v, dict):
                res = znajdz_wartosc(v, fragmenty)
                if res is not None: return res
        return None

    try:
        print("Łączenie z serwerem i pobieranie listy stacji...")
        res = requests.get(f"{API_BASE}/station/findAll?size=500", headers=HEADERS)
        res.raise_for_status()
        stations = wyciagnij_liste(res.json())

        data = []
        total_stations = len(stations)

        if total_stations == 0:
            return "Błąd: Pusta odpowiedź z API GIOŚ!"

        for index, station in enumerate(stations):
            st_id = znajdz_wartosc(station, ["identyfikator stacji", "stationid", "id"])
            lat = znajdz_wartosc(station, ["φ", "lat", "szerokość"])
            lon = znajdz_wartosc(station, ["λ", "lon", "długość"])

            station_name = str(znajdz_wartosc(station, ["nazwa stacji", "stationname", "name"]) or "").strip()
            city_obj = znajdz_wartosc(station, ["city", "miasto"])
            city_name = ""
            
            if city_obj:
                city_name = str(znajdz_wartosc(city_obj, ["name", "nazwa"]) or "").strip()
            if not city_name:
                city_name = str(znajdz_wartosc(station, ["nazwa miejscowości", "nazwa miasta"]) or "").strip()
            if not city_name and station_name:
                 city_name = station_name.split(',')[0].split('-')[0].strip()

            if st_id and lat and lon and station_name:
                print(f"[{index+1}/{total_stations}] Przetwarzam: {station_name}")
                station_data = {
                    "id": int(st_id),
                    "city": city_name,
                    "name": station_name,
                    "lat": float(str(lat).replace(",", ".")),
                    "lon": float(str(lon).replace(",", ".")),
                    "date": dzisiejsza_data,
                    "pm10": 0.0, "pm25": 0.0, "no2": 0.0, "so2": 0.0, "co": 0.0
                }

                try:
                    s_res = requests.get(f"{API_BASE}/station/sensors/{st_id}", headers=HEADERS)
                    s_res.raise_for_status()
                    sensors = wyciagnij_liste(s_res.json())

                    for sensor in sensors:
                        sens_id = znajdz_wartosc(sensor, ["identyfikator stanowiska", "sensorid", "id"])
                        
                        param_obj = sensor.get("param", {})
                        wzor = str(param_obj.get("paramFormula", "")).upper()
                        if not wzor:
                            wzor = str(sensor.get("Wskaźnik - wzór", "")).upper()
                        if not wzor:
                            wzor = str(sensor.get("Parametr") or "").upper()

                        mapped_param = None
                        if 'PM10' in wzor: mapped_param = 'pm10'
                        elif 'PM2.5' in wzor or 'PM25' in wzor: mapped_param = 'pm25'
                        elif 'NO2' in wzor: mapped_param = 'no2'
                        elif 'SO2' in wzor: mapped_param = 'so2'
                        elif 'CO' in wzor: mapped_param = 'co'

                        if mapped_param and sens_id:
                            try:
                                d_res = requests.get(f"{API_BASE}/data/getData/{sens_id}?size=10", headers=HEADERS)
                                d_res.raise_for_status()
                                readings = wyciagnij_liste(d_res.json())

                                for val_entry in readings:
                                    v = znajdz_wartosc(val_entry, ["wartość", "value", "wynik"])
                                    if v is not None:
                                        wartosc = float(v)
                                        if mapped_param == 'co':
                                            station_data[mapped_param] = round(wartosc / 1000.0, 2)
                                        else:
                                            station_data[mapped_param] = round(wartosc, 1)
                                        break
                            except Exception:
                                pass 
                    time.sleep(0.05) 
                except Exception:
                    pass

                data.append(station_data)

        if len(data) == 0:
            return "Błąd: Brak danych ze stacji."
        else:
            df = pd.DataFrame(data)
            if os.path.exists(file_path):
                df.to_csv(file_path, mode='a', header=False, index=False, encoding='utf-8-sig')
            else:
                df.to_csv(file_path, index=False, encoding='utf-8-sig')
            print("--- ZAKOŃCZONO POBIERANIE SUKCESEM ---")
            return "Ukończono!"

    except Exception as e:
        print(f"Błąd sieciowy w tle: {e}")
        return "Błąd połączenia sieciowego."

# ODCZYT BAZY DO PAMIĘCI
def wczytaj_dane_z_csv():
    file_path = 'baza_powietrza_polska3.csv'
    if not os.path.exists(file_path):
        print("INFO: Brak pliku bazy, aplikacja startuje pusta.")
        return pd.DataFrame(), []
    try:
        df_raw = pd.read_csv(file_path)
        if 'date' not in df_raw.columns:
            df_raw.columns = ['id', 'city', 'name', 'lat', 'lon', 'date', 'pm10', 'pm25', 'no2', 'so2', 'co']
            
        df_raw = df_raw.drop_duplicates(subset=['id', 'date'], keep='last')
        df_raw = df_raw.sort_values('date') 
        dates = df_raw['date'].unique().tolist()[-7:] 
        data = []
        params = ['pm10', 'pm25', 'no2', 'so2', 'co']
        
        for st_id, group in df_raw.groupby('id'):
            group = group.tail(7) 
            latest = group.iloc[-1] 
            station_data = {
                "id": latest['id'], "name": latest['name'], "city": latest['city'], 
                "lat": float(latest['lat']), "lon": float(latest['lon']), "history": {}
            }
            for pol in params:
                hist = group[pol].tolist()
                station_data["history"][pol] = hist
                station_data[pol] = float(hist[-1])
                if len(hist) >= 2:
                    diff = float(hist[-1]) - float(hist[-2])
                    threshold = float(hist[-2]) * 0.05 
                    station_data[f"{pol}_trend"] = "↗" if diff > threshold else ("↘" if diff < -threshold else "→")
                else:
                    station_data[f"{pol}_trend"] = "→" 
            data.append(station_data)
        return pd.DataFrame(data), dates
    except Exception as e:
        print(f"Błąd odczytu CSV: {e}")
        return pd.DataFrame(), []

GLOBAL_DF_INIT, _ = wczytaj_dane_z_csv()
POLAND_BORDER = "https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/poland.geojson"
DEFAULT_STATION = GLOBAL_DF_INIT.iloc[0]['id'] if not GLOBAL_DF_INIT.empty else 0

# INICJALIZACJA APLIKACJI 
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME])
server = app.server

color_mode_switch = html.Span(
    [
        dbc.Label(className="fa fa-moon", html_for="switch"),
        dbc.Switch(id="switch", value=True, className="d-inline-block ms-1", persistence=True),
        dbc.Label(className="fa fa-sun", html_for="switch"),
    ],
    style={"fontSize": "20px", "marginTop": "5px"}
)

#  LAYOUT 
app.layout = dbc.Container([
    
    html.Div([
        
        html.Div([
            html.Img(src="/assets/logo_ecog.jpg", style={'height': '70px', 'marginRight': '15px'}),
            html.H2("EcoG", style={'fontWeight': 'bold', 'margin': '0'})
        ], style={'display': 'flex', 'alignItems': 'center'}),
        
        html.Div([
            color_mode_switch,
            html.Div([
                dbc.Button([html.I(className="fa fa-download me-2"), "Pobierz dane"], id="download-btn", color="success", size="md"),
                dcc.Loading(
                    id="loading-download",
                    type="circle",
                    color="#2ECC71",
                    children=html.Div(id="download-status", style={'fontWeight': 'bold', 'color': '#2ECC71', 'marginTop': '5px', 'fontSize': '12px', 'textAlign': 'center'})
                )
            ], style={'marginLeft': '25px', 'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center'})
        ], style={'display': 'flex', 'alignItems': 'flex-start'})
        
    ], style={'padding': '15px 20px', 'borderBottom': '2px solid #005b9f', 'marginBottom': '20px', 'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'}),

    html.Div([
        html.Div([
            html.Label("Zanieczyszczenie:", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='pollutant-dropdown',
                options=[
                    {'label': 'Pyły (PM10)', 'value': 'pm10'},
                    {'label': 'Pyły (PM2.5)', 'value': 'pm25'},
                    {'label': 'Azot (NO2)', 'value': 'no2'},
                    {'label': 'Siarka (SO2)', 'value': 'so2'},
                    {'label': 'Węgiel (CO)', 'value': 'co'},
                ], value='pm10', clearable=False, style={'color': '#000'}
            ),
            html.Hr(),
            html.H4("Ranking TOP 10"),
            dash_table.DataTable(
                id='ranking-table',
                columns=[
                    {"name": "Stacja", "id": "name"},
                    {"name": "Wartość", "id": "display_val"},
                    {"name": "Trend", "id": "display_trend"},
                    {"name": "Zmiana", "id": "rank_change_str"} 
                ],
                style_cell={'textAlign': 'left', 'padding': '5px', 'fontSize': '12px', 'backgroundColor': 'transparent'},
                style_header={'fontWeight': 'bold', 'backgroundColor': 'transparent'},
                page_size=10 
            ),
            html.Div(id='dynamic-legend', style={'marginTop': '20px'})
        ], className="col-md-3"),

        html.Div([
            dcc.Tabs(id="map-tabs", value='tab-stations', children=[
                dcc.Tab(label='OSM', value='tab-stations'),
                dcc.Tab(label='Heatmap', value='tab-heatmap'),
            ]),
            dl.Map(id="map-res", center=[52.1, 19.4], zoom=6, style={'height': '45vh', 'marginBottom': '10px', 'backgroundColor': '#e8e8e8'}),
            html.Div([
                html.Div([
                    html.Label("Wybierz stację do analizy historycznej:", style={'fontWeight': 'bold'}),
                    dcc.Dropdown(
                        id='station-dropdown',
                        options=[{'label': row['name'], 'value': row['id']} for _, row in GLOBAL_DF_INIT.iterrows()] if not GLOBAL_DF_INIT.empty else [],
                        value=DEFAULT_STATION, 
                        clearable=False,
                        style={'color': '#000'}
                    )
                ], style={'width': '50%', 'marginBottom': '10px'}),
                dcc.Graph(id='history-chart', style={'height': '28vh'})
            ], style={'padding': '10px', 'border': '1px solid #ddd', 'borderRadius': '5px'})
        ], className="col-md-9")
    ], className="row")
], fluid=True, style={'padding': '20px'})

# LOGIKA APLIKACJI 

clientside_callback(
    """
    (switchOn) => {
        document.documentElement.setAttribute("data-bs-theme", switchOn ? "light" : "dark");
        return window.dash_clientside.no_update
    }
    """,
    Output("switch", "id"),
    Input("switch", "value"),
)

@app.callback(
    [Output("download-status", "children"),
     Output("station-dropdown", "options"),
     Output("station-dropdown", "value")],
    Input("download-btn", "n_clicks"),
    prevent_initial_call=True
)
def handle_download(n_clicks):
    if not n_clicks:
        return dash.no_update, dash.no_update, dash.no_update
    
    status_msg = pobierz_dzisiejsze_dane()
    df_fresh, _ = wczytaj_dane_z_csv()
    options = [{'label': row['name'], 'value': row['id']} for _, row in df_fresh.iterrows()] if not df_fresh.empty else []
    val = df_fresh.iloc[0]['id'] if not df_fresh.empty else 0
    return status_msg, options, val

@app.callback(
    [Output('map-res', 'children'),
     Output('ranking-table', 'data'),
     Output('dynamic-legend', 'children')], 
    [Input('pollutant-dropdown', 'value'),
     Input('map-tabs', 'value'),
     Input('download-status', 'children')] 
)
def update_map_elements(pollutant, tab, download_status):
    temp_df, _ = wczytaj_dane_z_csv()
    
    if temp_df.empty:
        return [dl.TileLayer()], [], html.Div()

    thresholds = {
        'pm10': [50, 110],
        'pm25': [35, 75],
        'no2': [100, 230],
        'so2': [100, 350],
        'co': [5, 30] 
    }
    t = thresholds.get(pollutant, [30, 60])

    def get_color(val):
        if val == 0.0:
            return "#95a5a6"
        return "#2ECC71" if val <= t[0] else "#F39C12" if val <= t[1] else "#E74C3C"

    temp_df['today_val'] = temp_df['history'].apply(lambda h: float(h[pollutant][-1]))
    temp_df['yest_val'] = temp_df['history'].apply(lambda h: float(h[pollutant][-2]) if len(h[pollutant]) >= 2 else float(h[pollutant][-1]))
    temp_df['rank_today'] = temp_df['today_val'].rank(ascending=False, method='min')
    temp_df['rank_yest'] = temp_df['yest_val'].rank(ascending=False, method='min')
    temp_df['rank_change'] = temp_df['rank_yest'] - temp_df['rank_today']
    
    def format_change(c):
        if c > 0: return f"↑ +{int(c)}"
        elif c < 0: return f"↓ {int(c)}"
        return "-"
        
    temp_df['rank_change_str'] = temp_df['rank_change'].apply(format_change)

    table_data = temp_df.sort_values(by='today_val', ascending=False).head(10)
    table_data['display_val'] = table_data['today_val']
    table_data['display_trend'] = table_data.apply(
        lambda row: "-" if row['today_val'] == 0.0 else row[f"{pollutant}_trend"], axis=1
    )

    safe_table_data = table_data[['name', 'display_val', 'display_trend', 'rank_change_str']]

    children = []
    if tab == 'tab-stations':
        children.append(dl.TileLayer())
    else:
        children.append(dl.GeoJSON(url=POLAND_BORDER, style={'color': '#888', 'fillOpacity': 0, 'weight': 2}))

    heat_data = [] 
    interactive_points = []

    for _, row in temp_df.iterrows():
        val = row['today_val']
        color = get_color(val)
        unit = "mg/m³" if pollutant == 'co' else "µg/m³"
        display_text = f"{pollutant.upper()}: {val} {unit}"
        unique_id = f"marker-{row['id']}-{pollutant}-{tab}"
        
        if tab == 'tab-stations':
            interactive_points.append(
                dl.CircleMarker(
                    id=unique_id, 
                    center=[row['lat'], row['lon']], 
                    radius=6,
                    color=color, fill=True, fillOpacity=0.9, weight=1,
                    children=[dl.Popup([html.B(row['name']), html.Br(), display_text])]
                )
            )
        else:
            if val > 0:
                intensity = min(val / t[1], 1.0) 
                heat_data.append([row['lat'], row['lon'], intensity])

            # Brak Tooltip i Popup dla Heatmapy
            interactive_points.append(
                dl.CircleMarker(
                    id=f"point-{unique_id}", 
                    center=[row['lat'], row['lon']], 
                    radius=3,
                    color="#333", fillColor=color, fillOpacity=1, weight=1
                )
            )

    if tab == 'tab-heatmap':
        children.append(
            dl.Heatmap(
                data=heat_data,
                radius=35, 
                blur=25,   
                gradient={"0.4": '#2ECC71', "0.7": '#F39C12', "1.0": '#E74C3C'},
                minOpacity=0.3
            )
        )

    children.append(dl.LayerGroup(interactive_points))
    
    legend_html = html.Div([
        html.P("Legenda (zgodnie z normami):", style={'fontWeight': 'bold'}),
        html.Div([html.Span("●", style={'color': '#2ECC71'}), f" Dobra (<= {t[0]})"]),
        html.Div([html.Span("●", style={'color': '#F39C12'}), f" Umiarkowana ({t[0]} - {t[1]})"]),
        html.Div([html.Span("●", style={'color': '#E74C3C'}), f" Zła (> {t[1]})"]),
        html.Div([html.Span("●", style={'color': '#95a5a6'}), " Brak danych / 0.0"]),
    ])
    return children, safe_table_data.to_dict('records'), legend_html

@app.callback(
    Output('history-chart', 'figure'),
    [Input('pollutant-dropdown', 'value'),
     Input('station-dropdown', 'value'),
     Input('switch', 'value'),
     Input('download-status', 'children')] 
)
def update_chart(pollutant, station_id, is_light_mode, download_status):
    temp_df, dates = wczytaj_dane_z_csv()
    
    if temp_df.empty:
        return px.line(title="Brak danych do wyświetlenia")

    trigger = ctx.triggered_id
    text_color = '#000' if is_light_mode else '#fff'
    grid_color = '#eee' if is_light_mode else '#555'
    line_color = '#c0392b' if is_light_mode else '#e74c3c'
    if trigger == 'switch':
        patched_figure = Patch()
        patched_figure["layout"]["font"]["color"] = text_color
        patched_figure["layout"]["xaxis"]["gridcolor"] = grid_color
        patched_figure["layout"]["yaxis"]["gridcolor"] = grid_color
        patched_figure["data"][0]["line"]["color"] = line_color
        patched_figure["data"][0]["marker"]["color"] = line_color
        return patched_figure

    if station_id not in temp_df['id'].values:
        station_id = temp_df.iloc[0]['id']

    row = temp_df[temp_df['id'] == station_id].iloc[0]
    y_data = row['history'][pollutant]
    unit = "mg/m³" if pollutant == 'co' else "µg/m³"
    fig = px.line(
        x=dates, y=y_data, 
        markers=True, 
        title=f"Wartości {pollutant.upper()} - {row['name']}",
        labels={'x': 'Data', 'y': f'Stężenie [{unit}]'}
    )
    fig.update_layout(
        margin={'l': 40, 'r': 20, 't': 40, 'b': 30},
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_color=text_color,
        xaxis=dict(showgrid=True, gridcolor=grid_color, tickformat="%Y-%m-%d"),
        yaxis=dict(showgrid=True, gridcolor=grid_color)
    )
    fig.update_traces(line_color=line_color, marker=dict(size=8))
    return fig

if __name__ == '__main__':
    app.run(debug=True)