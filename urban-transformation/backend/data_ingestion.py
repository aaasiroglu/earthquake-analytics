"""İBB/MAKS kaynaklı GML ve Shapefile (.shp) verisinin içe aktarılması.

MAKS (Mekânsal Adres Kayıt Sistemi) ve İBB açık veri/kadastro
katmanlarının alan adları kurumdan kuruma ve yıldan yıla değişebildiği
için, gerçek sütun adlarını bilmeden de çalışabilecek bir
"alias eşleştirme" (alias mapping) yaklaşımı kullanılır: her hedef alan
için olası kaynak sütun adlarının bir listesi tutulur, gelen veri
büyük/küçük harf ve alt çizgi farkından bağımsız olarak bu listeyle
eşleştirilir. Gerçek MAKS şeması netleşince ALIASES sözlüğüne yeni
adlar eklemek yeterlidir; eşleştirme mantığı değişmez.

Not: Resmi TUCBS_BI v2.0 bina veri şemasının öznitelik adları (örn.
cephe yönü, bulunduğu kat tipi, enerji sınıfı, asansör, deprem yer
hareketi düzeyi, tesisat) henüz ALIASES'e eklenmedi; gerçek MAKS/TUCBS
verisi temin edildiğinde eklenmelidir.
"""
from __future__ import annotations

import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

try:
    import geopandas as gpd

    GEOPANDAS_AVAILABLE = True
except ImportError:  # pragma: no cover - sandbox'ta GDAL/geopandas olmayabilir
    GEOPANDAS_AVAILABLE = False


# Hedef (normalize) alan adı -> olası kaynak sütun adları (MAKS/İBB/TKGM tipik adlandırmaları)
ALIASES: dict[str, list[str]] = {
    "parcel_id": ["ada_parsel", "ada_no_parsel_no", "adaparselno", "parsel_id", "parselno", "object_id"],
    "parcel_area_m2": ["parsel_alan", "alan", "alan_m2", "shape_area", "area", "parsel_alani"],
    "floor_count": ["kat_sayisi", "katsayisi", "floor_count", "kat_adedi", "ns_kat"],
    "unit_count": [
        "bagimsiz_bolum_sayisi", "bb_sayisi", "bagimsizbolumsayisi",
        "unit_count", "daire_sayisi",
    ],
    "population": ["nufus", "population", "nufus_sayisi", "yasayan_nufus"],
    "building_id": ["bina_id", "bina_no", "building_id", "yapi_no"],
    "district": ["ilce", "ilce_adi", "district"],
    "neighborhood": ["mahalle", "mahalle_adi", "neighborhood"],
}


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def normalize_attributes(properties: dict[str, Any]) -> dict[str, Any]:
    """Ham öznitelik sözlüğünü ALIASES'e göre normalize eder.

    Eşleşmeyen alanlar None olur; orijinal veri kaybolmaz, çağıran taraf
    `raw` altında orijinal öznitelikleri de saklar.
    """
    normalized_input = {_normalize_key(k): v for k, v in properties.items()}
    result: dict[str, Any] = {}
    for target_field, aliases in ALIASES.items():
        value = None
        for alias in aliases:
            alias_key = _normalize_key(alias)
            if alias_key in normalized_input and normalized_input[alias_key] not in (None, ""):
                value = normalized_input[alias_key]
                break
        result[target_field] = value
    return result


def _extract_zip_if_needed(file_path: Path) -> Path:
    """.zip içinde gönderilen shapefile setini (.shp/.dbf/.shx/.prj) açar."""
    if file_path.suffix.lower() != ".zip":
        return file_path
    extract_dir = Path(tempfile.mkdtemp())
    with zipfile.ZipFile(file_path) as zf:
        zf.extractall(extract_dir)
    shp_files = list(extract_dir.glob("**/*.shp"))
    if not shp_files:
        raise ValueError("Zip içinde .shp dosyası bulunamadı.")
    return shp_files[0]


def load_vector_file(file_path: str | Path) -> "gpd.GeoDataFrame":
    if not GEOPANDAS_AVAILABLE:
        raise RuntimeError(
            "geopandas/fiona kurulu değil. requirements.txt içindeki GIS "
            "bağımlılıklarını (geopandas, fiona, shapely, pyproj) kurun."
        )
    path = _extract_zip_if_needed(Path(file_path))
    gdf = gpd.read_file(path)
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    return gdf


def to_normalized_geojson(gdf: "gpd.GeoDataFrame") -> dict[str, Any]:
    features = []
    raw_geojson = json.loads(gdf.to_json())
    for feature in raw_geojson["features"]:
        raw_props = feature.get("properties", {}) or {}
        normalized = normalize_attributes(raw_props)
        features.append(
            {
                "type": "Feature",
                "geometry": feature["geometry"],
                "properties": {**normalized, "raw": raw_props},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def sample_geojson() -> dict[str, Any]:
    """Gerçek MAKS dosyası gelene kadar arayüzü test etmek için örnek veri."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "parcel_id": "1234/5",
                    "parcel_area_m2": 950.0,
                    "floor_count": 4,
                    "unit_count": 14,
                    "population": 38,
                    "building_id": "BINA-0012",
                    "district": "Kadıköy",
                    "neighborhood": "Caferağa",
                    "raw": {"kaynak": "örnek veri (gerçek MAKS değil)"},
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [29.0270, 40.9875], [29.0282, 40.9875],
                        [29.0282, 40.9883], [29.0270, 40.9883],
                        [29.0270, 40.9875],
                    ]],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "parcel_id": "1234/6",
                    "parcel_area_m2": 1100.0,
                    "floor_count": 5,
                    "unit_count": 18,
                    "population": 47,
                    "building_id": "BINA-0013",
                    "district": "Kadıköy",
                    "neighborhood": "Caferağa",
                    "raw": {"kaynak": "örnek veri (gerçek MAKS değil)"},
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [29.0283, 40.9875], [29.0296, 40.9875],
                        [29.0296, 40.9883], [29.0283, 40.9883],
                        [29.0283, 40.9875],
                    ]],
                },
            },
        ],
    }
