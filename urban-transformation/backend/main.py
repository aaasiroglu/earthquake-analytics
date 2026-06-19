import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import citydb
from calculations import CalculationInput, CalculationResult, calculate
from data_ingestion import (
    GEOPANDAS_AVAILABLE,
    load_vector_file,
    sample_geojson,
    to_normalized_geojson,
)
from price_model import KernelWeightedPriceModel, synthetic_sales
from scan import ScanParams, ScanParcel, ScanResult, scan_parcels

app = FastAPI(title="Kentsel Dönüşüm Karar Destek API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/calculate", response_model=CalculationResult)
def calculate_endpoint(payload: CalculationInput) -> CalculationResult:
    return calculate(payload)


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
        tmp_path = Path(tmp_dir) / (file.filename or f"upload{suffix}")
        with tmp_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        try:
            gdf = load_vector_file(tmp_path)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Dosya okunamadı: {exc}") from exc
        return to_normalized_geojson(gdf)


@app.get("/data/sample")
def sample_data():
    """Gerçek MAKS dosyası gelene kadar arayüzü test etmek için örnek veri."""
    return sample_geojson()


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
    """Verilen bbox içindeki parsel tablosunu (ogr2ogr ile yüklenmiş SHP) döner."""
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
    """Verilen parsel/alan geometrisiyle kesişen binalardan mevcut ayak izi
    alanı ve kat sayısını (TAKS/KAKS hesaplaması için "mevcut durum" girdisi
    olarak) hesaplar."""
    _require_citydb()
    try:
        return citydb.building_context_for_geometry(geometry.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"3DCityDB sorgu hatası: {exc}") from exc


@app.get("/price/sample-sales")
def price_sample_sales(lon: float, lat: float, n: int = 60, seed: int = 42):
    """Demo amaçlı SENTETİK satış noktaları üretir. Gerçek bir değerleme/
    rapor için KULLANILAMAZ — sadece /price/predict ve /scan'i test etmek
    içindir. Gerçek bölgesel satış verisi temin edilince bu uç nokta
    devre dışı bırakılmalı, sales doğrudan veritabanından/dosyadan
    okunmalıdır."""
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
    """Tek bir nokta için GWR-lite (Gauss çekirdek ağırlıklı yerel ortalama)
    ile bölgesel m² satış fiyatı tahmini döner."""
    model = KernelWeightedPriceModel(payload.sales, bandwidth_km=payload.bandwidth_km)
    return model.predict(payload.lon, payload.lat)


class ScanRequest(BaseModel):
    parcels: list[ScanParcel]
    params: ScanParams
    sales: list[dict[str, float]]


@app.post("/scan", response_model=list[ScanResult])
def scan_endpoint(payload: ScanRequest) -> list[ScanResult]:
    """Şehir ölçekli, proaktif Kârlılık Endeksi taraması: verilen parsel
    listesini, her biri için tahmini bölgesel satış fiyatı + TAKS/KAKS
    hesabı uygulayarak kârlılığa göre sıralar ("Yatırıma Hazır Adalar")."""
    if not payload.parcels:
        raise HTTPException(status_code=400, detail="parcels listesi boş olamaz.")
    try:
        return scan_parcels(payload.parcels, payload.params, payload.sales)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/health")
def health():
    return {
        "status": "ok",
        "geopandas_available": GEOPANDAS_AVAILABLE,
        "citydb_configured": citydb.CITYDB_CONFIGURED,
    }
