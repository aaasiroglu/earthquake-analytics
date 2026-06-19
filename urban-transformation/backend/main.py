import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/health")
def health():
    return {"status": "ok", "geopandas_available": GEOPANDAS_AVAILABLE}
