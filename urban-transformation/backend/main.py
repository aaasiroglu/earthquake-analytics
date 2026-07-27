import tempfile
import time
from pathlib import Path
from collections import OrderedDict
import logging
import os

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import citydb
from calculations import (
    CalculationInput,
    CalculationResult,
    ScenarioInput,
    ScenarioOutput,
    SerefiyeInput,
    SerefiyeResult,
    calculate,
    calculate_scenarios,
    calculate_serefiye,
)
from data_ingestion import (
    GEOPANDAS_AVAILABLE,
    fetch_osm_buildings,
    load_vector_file,
    sample_geojson,
    to_normalized_geojson,
)
from price_model import KernelWeightedPriceModel, estimate_price, synthetic_sales
from investment_model import (
    InvestorProfile,
    RecommendationResponse,
    opportunity_geojson,
    recommend_neighborhoods,
)
from scan import ScanParams, ScanParcel, ScanResult, scan_parcels

logger = logging.getLogger("urban_transformation.api")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

APP_VERSION = "1.1.0"
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
OSM_CACHE_TTL_SECONDS = int(os.getenv("OSM_CACHE_TTL_SECONDS", "900"))
OSM_CACHE_MAX_ITEMS = int(os.getenv("OSM_CACHE_MAX_ITEMS", "64"))
_osm_cache: OrderedDict[tuple[float, float, int], tuple[float, dict]] = OrderedDict()


def _allowed_origins() -> list[str]:
    """Virgülle ayrılmış CORS_ORIGINS tanımını güvenli bir listeye dönüştürür."""
    configured = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173,http://localhost:8080,http://127.0.0.1:8080",
    )
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    if "*" in origins and os.getenv("APP_ENV", "development").lower() != "development":
        raise RuntimeError("Üretimde CORS_ORIGINS '*' olamaz; izinli origin'leri açıkça tanımlayın.")
    return origins


app = FastAPI(
    title="Kentsel Dönüşüm Karar Destek API",
    version=APP_VERSION,
    description="Tahmini kentsel dönüşüm senaryo hesaplama ve açık coğrafi veri API'si.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Hesaplama Endpoint'leri ───────────────────────────────────────────────────────────

@app.post("/calculate", response_model=CalculationResult)
def calculate_endpoint(payload: CalculationInput) -> CalculationResult:
    return calculate(payload)


@app.post("/calculate/scenarios", response_model=ScenarioOutput)
def calculate_scenarios_endpoint(payload: ScenarioInput) -> ScenarioOutput:
    return calculate_scenarios(payload)


@app.post("/calculate/serefiye", response_model=SerefiyeResult)
def serefiye_endpoint(payload: SerefiyeInput) -> SerefiyeResult:
    """Kat bazında şerefiye (dikey hedonik fiyatlama) analizi."""
    return calculate_serefiye(payload)


# ── Fiyat Modeli Endpoint'leri ────────────────────────────────────────────────────────

@app.get("/price/estimate")
def price_estimate_endpoint(district: str, floor_factor: float = 1.0):
    """Sentetik GWR-lite ilçe bazlı m² fiyat tahmini."""
    if not (0.5 <= floor_factor <= 3.0):
        raise HTTPException(
            status_code=400, detail="floor_factor 0.5-3.0 aralığında olmalı."
        )
    return estimate_price(district=district, floor_factor=floor_factor)


@app.get("/price/sample-sales")
def price_sample_sales(lon: float, lat: float, n: int = 60, seed: int = 42):
    """Demo amaçlı SENTETİK satış noktaları üretir."""
    return {
        "warning": "SENTETİK (uydurma) veri. Gerçek değerleme için kullanılamaz.",
        "sales": synthetic_sales(lon, lat, n=n, seed=seed),
    }


class PricePredictRequest(BaseModel):
    lon: float
    lat: float
    sales: list[dict[str, float]]
    bandwidth_km: float = 1.5


@app.post("/price/predict")
def price_predict(payload: PricePredictRequest):
    """Tek bir nokta için GWR-lite (Gauss çekirdek ağırlıklı yerel ortalama) ile m² fiyat tahmini."""
    model = KernelWeightedPriceModel(payload.sales, bandwidth_km=payload.bandwidth_km)
    return model.predict(payload.lon, payload.lat)


# ── Yatırımcı Keşif Endpoint'leri ────────────────────────────────────────────────────

@app.post("/market/recommendations", response_model=RecommendationResponse)
def market_recommendations(profile: InvestorProfile) -> RecommendationResponse:
    """Bütçe ve tercihleri sentetik mahalle fırsat göstergeleriyle eşleştirir."""
    return recommend_neighborhoods(profile)


@app.post("/market/opportunities")
def market_opportunities(profile: InvestorProfile):
    """3B MapLibre katmanında gösterilecek sentetik bina fırsat GeoJSON'unu döner."""
    return opportunity_geojson(profile)


# ── Veri Endpoint'leri ────────────────────────────────────────────────────────────────

@app.post("/data/import")
async def import_vector_file(file: UploadFile):
    """MAKS/İBB kaynaklı .gml veya .shp (tam shapefile seti .zip olarak) içe aktarır."""
    if not GEOPANDAS_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail=(
                "geopandas/fiona kurulu değil. backend/requirements.txt "
                "içindeki GIS bağımlılıklarını kurun (GDAL sistem "
                "kütüphanesi gerekir)."
            ),
        )
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".gml", ".shp", ".zip"):
        raise HTTPException(
            status_code=400,
            detail="Desteklenen formatlar: .gml, .zip (içinde .shp/.dbf/.shx). "
            "Tek başına .shp dosyası companion (.dbf/.shx) dosyaları olmadan okunamaz.",
        )
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / Path(file.filename or f"upload{suffix}").name
        with tmp_path.open("wb") as f:
            uploaded_bytes = 0
            while chunk := await file.read(1024 * 1024):
                uploaded_bytes += len(chunk)
                if uploaded_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Dosya boyutu üst sınırı aşıyor ({MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
                    )
                f.write(chunk)
        try:
            gdf = load_vector_file(tmp_path)
        except Exception as exc:
            logger.info("Vector import rejected: %s", exc)
            raise HTTPException(status_code=422, detail=f"Dosya okunamadı: {exc}") from exc
        return to_normalized_geojson(gdf)


@app.get("/data/sample")
def sample_data():
    """Gerçek MAKS dosyası gelene kadar arayüzü test etmek için örnek veri."""
    return sample_geojson()


@app.get("/data/osm")
def osm_data(lon: float, lat: float, radius_m: int = 150):
    """Verilen noktanın çevresindeki bina ayak izlerini OSM'den (Overpass API) çeker."""
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise HTTPException(status_code=400, detail="Geçerli bir enlem/boylam girin.")
    if not (0 < radius_m <= 500):
        raise HTTPException(status_code=400, detail="radius_m 1-500 aralığında olmalı.")
    cache_key = (round(lon, 5), round(lat, 5), radius_m)
    now = time.monotonic()
    cached = _osm_cache.get(cache_key)
    if cached and now - cached[0] < OSM_CACHE_TTL_SECONDS:
        _osm_cache.move_to_end(cache_key)
        return cached[1]
    try:
        data = fetch_osm_buildings(lon, lat, radius_m)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _osm_cache[cache_key] = (now, data)
    _osm_cache.move_to_end(cache_key)
    while len(_osm_cache) > OSM_CACHE_MAX_ITEMS:
        _osm_cache.popitem(last=False)
    return data


# ── Şehir Ölçekli Tarama ─────────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    parcels: list[ScanParcel]
    params: ScanParams
    sales: list[dict[str, float]]


@app.post("/scan", response_model=list[ScanResult])
def scan_endpoint(payload: ScanRequest) -> list[ScanResult]:
    """Şehir ölçekli, proaktif Kârlılık Endeksi taraması."""
    if not payload.parcels:
        raise HTTPException(status_code=400, detail="parcels listesi boş olamaz.")
    try:
        return scan_parcels(payload.parcels, payload.params, payload.sales)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ── 3DCityDB Endpoint'leri ────────────────────────────────────────────────────────────

def _require_citydb():
    if not citydb.CITYDB_CONFIGURED:
        raise HTTPException(
            status_code=501,
            detail=(
                "3DCityDB bağlantısı yapılandırılmamış. CITYDB_HOST, "
                "CITYDB_USER, CITYDB_PASSWORD vb. ortam değişkenlerini "
                "ayarlayın (bkz. docker/.env.example)."
            ),
        )


@app.get("/citydb/buildings")
def citydb_buildings(minx: float, miny: float, maxx: float, maxy: float):
    """Verilen bbox içindeki 3DCityDB binalarını (gerçek ayak izi + yükseklik) döner."""
    _require_citydb()
    try:
        return citydb.buildings_in_bbox(minx, miny, maxx, maxy)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"3DCityDB sorgu hatası: {exc}") from exc


@app.get("/citydb/parcels")
def citydb_parcels(minx: float, miny: float, maxx: float, maxy: float):
    """Verilen bbox içindeki parsel tablosunu döner."""
    _require_citydb()
    try:
        return citydb.parcels_in_bbox(minx, miny, maxx, maxy)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Parsel sorgu hatası: {exc}") from exc


class GeometryPayload(BaseModel):
    type: str
    coordinates: list


@app.post("/citydb/context")
def citydb_context(geometry: GeometryPayload):
    """Verilen parsel/alan geometrisiyle kesişen binalardan mevcut durum hesaplar."""
    _require_citydb()
    try:
        return citydb.building_context_for_geometry(geometry.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"3DCityDB sorgu hatası: {exc}") from exc


# ── Sağlık Kontrolü ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": APP_VERSION,
        "geopandas_available": GEOPANDAS_AVAILABLE,
        "citydb_configured": citydb.CITYDB_CONFIGURED,
        "osm_cache_items": len(_osm_cache),
    }
