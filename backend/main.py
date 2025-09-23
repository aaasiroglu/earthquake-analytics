from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
import pandas as pd
from datetime import datetime, timedelta

app = FastAPI()

# CORS (frontend'e erişim için)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def fetch_usgs(starttime, endtime, minmag=0):
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format": "geojson",
        "starttime": starttime,
        "endtime": endtime,
        "minmagnitude": minmag
    }
    r = requests.get(url, params=params)
    features = r.json().get("features", [])
    data = []
    for f in features:
        coords = f['geometry']['coordinates']
        data.append({
            "lat": coords[1],
            "lon": coords[0],
            "depth": coords[2],
            "mag": f['properties']['mag'],
            "place": f['properties']['place'],
            "time": pd.to_datetime(f['properties']['time'], unit='ms'),
            "source": "USGS"
        })
    return data

def fetch_afad():
    url = "https://deprem.afad.gov.tr/apiv2/event/filter"
    params = {
        "start": 0,
        "end": 100,
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        events = r.json().get('data', [])
    except Exception:
        events = []
    data = []
    for f in events:
        try:
            data.append({
                "lat": f['latitude'],
                "lon": f['longitude'],
                "depth": f['depth'],
                "mag": f['magnitude'],
                "place": f['location'],
                "time": pd.to_datetime(f['date']),
                "source": "AFAD"
            })
        except Exception:
            continue
    return data

@app.get("/earthquakes")
def get_earthquakes(
    source: str = "all",
    start: str = None,
    end: str = None,
    minmag: float = 0
):
    now = datetime.utcnow()
    if not start:
        start = (now - timedelta(days=30)).strftime('%Y-%m-%d')
    if not end:
        end = now.strftime('%Y-%m-%d')
    result = []
    if source in ["all", "usgs"]:
        result += fetch_usgs(start, end, minmag)
    if source in ["all", "afad"]:
        result += fetch_afad()
    return result
