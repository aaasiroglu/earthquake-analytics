"""İBB/MAKS kaynaklı GML ve Shapefile (.shp) verisinin içe aktarılması.

MAKS (Mekânsal Adres Kayıt Sistemi) ve İBB açık veri/kadastro
katmanlarının alan adları kurumdan kuruma ve yıldan yıla değişebildiği
için, gerçek sütun adlarını bilmeden de çalışabilecek bir
"alias eşleştirme" (alias mapping) yaklaşımı kullanılır: her hedef alan
için olası kaynak sütun adlarının bir listesi tutulur, gelen veri
büyük/küçük harf ve alt çizgi farkından bağımsız olarak bu listeyle
eşleştirilir. Gerçek MAKS şeması netleşince ALIASES sözlüğüne yeni
adlar eklemek yeterlidir; eşleştirme mantığı değişmez.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import requests
from pyproj import Transformer
from shapely.geometry import Polygon
from shapely.ops import transform as shapely_transform

try:
    import geopandas as gpd

    GEOPANDAS_AVAILABLE = True
except ImportError:  # pragma: no cover - sandbox'ta GDAL/geopandas olmayabilir
    GEOPANDAS_AVAILABLE = False

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
MAX_EXTRACTED_ARCHIVE_BYTES = 100 * 1024 * 1024
# İstanbul için uygun UTM dilimi (metrik alan hesabı için).
_WGS84_TO_UTM35N = Transformer.from_crs("EPSG:4326", "EPSG:32635", always_xy=True)


# Hedef (normalize) alan adı -> olası kaynak sütun adları (MAKS/İBB/TKGM tipik adlandırmaları)
# TUCBS_BI v2.0 (1 Ocak 2025 şeması) yeni alanları da dahildir; gerçek öznitelik adları
# netleşince buraya eklenmesi yeterlidir — eşleştirme mantığı değişmez.
ALIASES: dict[str, list[str]] = {
    "parcel_id": ["ada_parsel", "ada_no_parsel_no", "adaparselno", "parsel_id", "parselno", "object_id"],
    "parcel_area_m2": ["parsel_alan", "alan", "alan_m2", "shape_area", "area", "parsel_alani"],
    "floor_count": ["kat_sayisi", "katsayisi", "floor_count", "kat_adedi", "ns_kat", "building:levels"],
    "unit_count": [
        "bagimsiz_bolum_sayisi", "bb_sayisi", "bagimsizbolumsayisi",
        "unit_count", "daire_sayisi", "building:flats",
    ],
    "population": ["nufus", "population", "nufus_sayisi", "yasayan_nufus"],
    "building_id": ["bina_id", "bina_no", "building_id", "yapi_no"],
    "district": ["ilce", "ilce_adi", "district", "addr:district"],
    "neighborhood": ["mahalle", "mahalle_adi", "neighborhood", "addr:suburb", "addr:neighbourhood"],
    "risk_score": ["risk_skoru", "risk_score", "deprem_risk_skoru", "risk_puani", "riskskor"],
    # ── TUCBS_BI v2.0 yeni alanlar ────────────────────────────────────────────────
    "facade_direction": [
        "cephe_yonu", "cepheyonu", "facade_direction", "bi_cepheyonu", "yon", "yön",
    ],
    "floor_type": [
        "bulundugu_kat_tipi", "kattipi", "kat_tipi", "floor_type", "bi_kattipi",
    ],
    "energy_class": [
        "enerji_sinifi", "enerjisinifi", "energy_class", "enerji_performansi",
        "bi_enerjisinifi",
    ],
    "has_elevator": [
        "asansor", "asansör", "elevator", "has_elevator", "bi_asansor", "asansorvarligi",
    ],
    "seismic_hazard_level": [
        "deprem_yer_hareketi_duzeyi", "depremyerhareketduzeyi", "seismic_hazard",
        "seismichazard", "bi_depremyerhareketduzeyi", "deprem_hazard",
    ],
    "installation_status": [
        "tesisat", "tesisatdurumu", "tesisat_durumu", "installation", "bi_tesisat",
    ],
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


def _mock_risk_score(normalized: dict[str, Any], fallback_seed: str) -> float:
    """Gerçek risk verisi yokken deterministik, tekrarlanabilir bir sahte skor üretir.

    Aynı parsel/bina için her zaman aynı skoru üretir (kararlılık), ama
    farklı kayıtlar için görsel çeşitlilik sağlar. Gerçek risk skoru
    (ALIASES eşleşirse) geldiğinde bu fonksiyon hiç çağrılmaz.
    """
    seed = str(normalized.get("parcel_id") or normalized.get("building_id") or fallback_seed)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return round((int(digest[:8], 16) % 10000) / 10000 * 100, 1)


def _ensure_risk_score(normalized: dict[str, Any], fallback_seed: str) -> dict[str, Any]:
    if normalized.get("risk_score") is None:
        normalized["risk_score"] = _mock_risk_score(normalized, fallback_seed)
    return normalized


def _extract_zip_if_needed(file_path: Path) -> Path:
    """.zip içinde gönderilen shapefile setini (.shp/.dbf/.shx/.prj) açar."""
    if file_path.suffix.lower() != ".zip":
        return file_path
    extract_dir = file_path.parent / "extracted"
    extract_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(file_path) as zf:
        # Zip Slip saldırılarını önlemek için her üyenin hedef dizinde kaldığını doğrula.
        if len(zf.infolist()) > 100:
            raise ValueError("Zip dosyasında çok fazla kayıt var (en fazla 100).")
        if sum(member.file_size for member in zf.infolist()) > MAX_EXTRACTED_ARCHIVE_BYTES:
            raise ValueError("Zip açıldığında izin verilen toplam boyutu aşıyor (100 MB).")
        for member in zf.infolist():
            target = (extract_dir / member.filename).resolve()
            if not target.is_relative_to(extract_dir.resolve()):
                raise ValueError("Zip dosyası güvenli olmayan bir yol içeriyor.")
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
    if gdf.crs is None:
        raise ValueError("Veri dosyasında CRS bilgisi yok; güvenilir dönüşüm için CRS zorunludur.")
    if gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    gdf = gdf[gdf.geometry.notna() & gdf.geometry.is_valid].copy()
    return gdf


def to_normalized_geojson(gdf: "gpd.GeoDataFrame") -> dict[str, Any]:
    features = []
    raw_geojson = json.loads(gdf.to_json())
    for idx, feature in enumerate(raw_geojson["features"]):
        raw_props = feature.get("properties", {}) or {}
        normalized = _ensure_risk_score(normalize_attributes(raw_props), fallback_seed=str(idx))
        features.append(
            {
                "type": "Feature",
                "geometry": feature["geometry"],
                "properties": {**normalized, "raw": raw_props},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _osm_tag_to_int(value: Any) -> int | None:
    """OSM etiketleri her zaman string'dir (örn. "10", "3.5", "2-3" gibi
    aralıklar da olabilir); sayısal alanlar için en baştaki sayıyı int'e çevirir."""
    if value is None:
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
    if not match:
        return None
    try:
        return int(float(match.group().replace(",", ".")))
    except ValueError:
        return None


def fetch_osm_buildings(lon: float, lat: float, radius_m: int) -> dict[str, Any]:
    """Verilen noktanın çevresindeki OSM bina ayak izlerini Overpass API'den çeker.

    OSM kadastral parsel kavramı içermez; bu yüzden `parcel_id`/`population`/
    `unit_count` çoğunlukla `None` kalır (mevcut "parsel ≈ bina ayak izi"
    basitleştirmesiyle tutarlı). Alan bilgisi OSM'de yok — burada UTM'e
    projekte edilip hesaplanır.
    """
    query = (
        f'[out:json][timeout:25];way["building"](around:{radius_m},{lat},{lon});out geom;'
    )
    try:
        resp = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "KafamdaKentselDonusum/1.0 (urban transformation decision support tool)",
            },
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f"Overpass API isteği başarısız: {exc}") from exc

    features = []
    for idx, element in enumerate(payload.get("elements", [])):
        geometry = element.get("geometry")
        if not geometry or len(geometry) < 3:
            continue
        ring = [[pt["lon"], pt["lat"]] for pt in geometry]
        if ring[0] != ring[-1]:
            ring.append(ring[0])

        tags = dict(element.get("tags", {}) or {})
        normalized = normalize_attributes(tags)
        for key in ("floor_count", "unit_count", "population"):
            normalized[key] = _osm_tag_to_int(normalized.get(key))
        if not normalized.get("building_id"):
            normalized["building_id"] = f"osm/{element.get('id')}"

        polygon = Polygon(ring)
        projected = shapely_transform(_WGS84_TO_UTM35N.transform, polygon)
        normalized["parcel_area_m2"] = round(projected.area, 2)

        normalized = _ensure_risk_score(normalized, fallback_seed=str(idx))
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {**normalized, "raw": tags},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def sample_geojson() -> dict[str, Any]:
    """Gerçek MAKS dosyası gelene kadar arayüzü test etmek için örnek veri."""
    fc = {
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
    for idx, feature in enumerate(fc["features"]):
        _ensure_risk_score(feature["properties"], fallback_seed=str(idx))
    return fc
