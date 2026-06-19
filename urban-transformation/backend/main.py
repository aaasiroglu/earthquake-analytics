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


@app.get("/health")
def health():
    return {
        "status": "ok",
        "geopandas_available": GEOPANDAS_AVAILABLE,
        "citydb_configured": citydb.CITYDB_CONFIGURED,
    }
