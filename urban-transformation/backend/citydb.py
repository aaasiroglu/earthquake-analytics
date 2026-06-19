"""3DCityDB (v4 PostGIS şeması) entegrasyonu.

Pilot bölge CityGML verisi `citydb-tool`/Importer-Exporter ile
3DCityDB'ye, parsel SHP'si de `ogr2ogr` ile ayrı bir PostGIS tabloya
yüklendikten sonra; bina ayak izi, yükseklik, kat sayısı ve parsel
bilgisini doğrudan veritabanından çekmek için kullanılır.

ÖNEMLİ — doğrulanmamış kod: Bu sorgular 3DCityDB v4 şemasının
dokümante edilen yapısına göre yazılmıştır (`building`, `thematic_surface`,
`surface_geometry`, `objectclass`, `cityobject` tabloları). Bu ajan
sandbox'ında çalışan bir 3DCityDB örneği ve internet erişimi
bulunmadığı için sorgular gerçek/canlı veriyle test edilememiştir.
Pilot CityGML import edildikten sonra:
  - GroundSurface bulunamayan binalar için sorgu satır döndürmez
    (örn. sadece LoD1 solid varsa). Gerekirse `lod1_multi_surface`/
    `lod1_solid`'den türetilmiş bir alternatif sorgu eklenmelidir.
  - 3DCityDB v5 (citydb-tool ile oluşturulan yeni nesil şema)
    kullanılıyorsa şema tamamen farklıdır, bu sorgular çalışmaz.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from data_ingestion import normalize_attributes

CITYDB_CONFIGURED = bool(os.environ.get("CITYDB_HOST"))

_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = (
        f"postgresql+psycopg2://{os.environ['CITYDB_USER']}:{os.environ['CITYDB_PASSWORD']}"
        f"@{os.environ.get('CITYDB_HOST', 'localhost')}:{os.environ.get('CITYDB_PORT', '5432')}"
        f"/{os.environ.get('CITYDB_NAME', 'citydb')}"
    )
    return create_engine(url)


def _parcels_table() -> str:
    table = os.environ.get("PARCELS_TABLE", "parcels.parcel")
    if not _TABLE_NAME_RE.match(table):
        raise ValueError(f"Geçersiz PARCELS_TABLE adı: {table!r}")
    return table


# Bina ayak izini GroundSurface (LoD2) üzerinden türetir; yükseklik
# `measured_height`, yoksa kat sayısından (3 m/kat) tahmin edilir.
_BUILDING_FOOTPRINT_SQL = text(
    """
    SELECT
      b.id AS building_id,
      b.measured_height,
      b.storeys_above_ground,
      ST_AsGeoJSON(ST_Force2D(ST_Multi(ST_Union(sg.geometry)))) AS footprint_geojson
    FROM building b
    JOIN cityobject co ON co.id = b.id
    JOIN thematic_surface ts ON ts.building_id = b.id
    JOIN objectclass oc ON oc.id = ts.objectclass_id AND oc.classname = 'GroundSurface'
    JOIN surface_geometry sg ON sg.root_id = ts.lod2_multi_surface_id
    WHERE co.envelope && ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326)
    GROUP BY b.id, b.measured_height, b.storeys_above_ground
    """
)

# Bir parsel/alan poligonu ile kesişen binaların ayak izi alanı ve kat
# sayısını toplar (mevcut TAKS/KAKS hesaplaması için "mevcut durum" verisi).
_BUILDING_CONTEXT_SQL = text(
    """
    SELECT
      b.id AS building_id,
      b.measured_height,
      b.storeys_above_ground,
      ST_Area(ST_Force2D(ST_Union(sg.geometry))::geography) AS footprint_area_m2
    FROM building b
    JOIN cityobject co ON co.id = b.id
    JOIN thematic_surface ts ON ts.building_id = b.id
    JOIN objectclass oc ON oc.id = ts.objectclass_id AND oc.classname = 'GroundSurface'
    JOIN surface_geometry sg ON sg.root_id = ts.lod2_multi_surface_id
    WHERE ST_Intersects(co.envelope, ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326))
    GROUP BY b.id, b.measured_height, b.storeys_above_ground
    """
)


def buildings_in_bbox(minx: float, miny: float, maxx: float, maxy: float) -> dict[str, Any]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            _BUILDING_FOOTPRINT_SQL, {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy}
        ).mappings().all()

    features = []
    for row in rows:
        if not row["footprint_geojson"]:
            continue
        height = row["measured_height"] or (row["storeys_above_ground"] or 1) * 3.0
        features.append(
            {
                "type": "Feature",
                "geometry": json.loads(row["footprint_geojson"]),
                "properties": {
                    "building_id": row["building_id"],
                    "measured_height": row["measured_height"],
                    "storeys_above_ground": row["storeys_above_ground"],
                    "height": height,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def building_context_for_geometry(geometry: dict[str, Any]) -> dict[str, Any]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(_BUILDING_CONTEXT_SQL, {"geom": json.dumps(geometry)}).mappings().all()

    total_footprint = sum(r["footprint_area_m2"] or 0 for r in rows)
    max_floors = max((r["storeys_above_ground"] or 0 for r in rows), default=0)
    return {
        "building_count": len(rows),
        "existing_footprint_area_m2": round(total_footprint, 2),
        "existing_floor_count": max_floors,
        "buildings": [
            {
                "building_id": r["building_id"],
                "measured_height": r["measured_height"],
                "storeys_above_ground": r["storeys_above_ground"],
                "footprint_area_m2": round(r["footprint_area_m2"] or 0, 2),
            }
            for r in rows
        ],
    }


def parcels_in_bbox(minx: float, miny: float, maxx: float, maxy: float) -> dict[str, Any]:
    engine = get_engine()
    table = _parcels_table()
    query = text(
        f"""
        SELECT to_jsonb(t.*) - 'geom' AS properties, ST_AsGeoJSON(t.geom) AS geometry_geojson
        FROM {table} t
        WHERE t.geom && ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326)
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(query, {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy}).mappings().all()

    features = []
    for row in rows:
        raw_props = row["properties"] or {}
        normalized = normalize_attributes(raw_props)
        features.append(
            {
                "type": "Feature",
                "geometry": json.loads(row["geometry_geojson"]),
                "properties": {**normalized, "raw": raw_props},
            }
        )
    return {"type": "FeatureCollection", "features": features}
