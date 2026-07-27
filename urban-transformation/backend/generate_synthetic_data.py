"""İstanbul'da 3 binalık sentetik bir 'ada' (grid) üretir; .gml ve .shp (zip)
olarak `urban-transformation/sample_data/` altına yazar.

Amaç: gerçek MAKS/İBB verisi gelene kadar, /data/import akışını ve
ALIASES eşleştirmesini gerçek bir vektör dosyasıyla (örnek veri ile değil)
test edebilmek. Sütun adları kasıtlı olarak normalize edilmiş hedef adlar
DEĞİL, gerçek MAKS/İBB tarzı ham adlardır (ada_parsel, alan_m2, kat_sayisi,
...) — böylece ALIASES'teki fuzzy eşleştirme gerçekten egzersiz edilir.
`risk_skoru` sütunu kasıtlı olarak YOK: backend'deki mock risk skoru
fallback'inin devreye girdiğini test eder.

Gerçek MAKS dosyası elinize geçtiğinde, bu script'i çalıştırmaya gerek
kalmaz; `/data/import`'a doğrudan gerçek dosyayı yükleyin.
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

OUT_DIR = Path(__file__).resolve().parent.parent / "sample_data"

# Kadıköy/Caferağa civarı (mevcut sample_geojson ile aynı bölge).
BASE_LON, BASE_LAT = 29.0270, 40.9875
BUILDING_W, BUILDING_H = 0.00015, 0.00012  # ~13m x 13m
GAP = 0.00030  # bina aralığı (~26m)

BUILDINGS = [
    {
        "ada_parsel": "2345/1",
        "alan_m2": 420.0,
        "kat_sayisi": 3,
        "bb_sayisi": 9,
        "nufus": 22,
        "bina_no": "BINA-SENT-01",
        "ilce_adi": "Kadıköy",
        "mahalle": "Caferağa",
    },
    {
        "ada_parsel": "2345/2",
        "alan_m2": 510.0,
        "kat_sayisi": 5,
        "bb_sayisi": 15,
        "nufus": 34,
        "bina_no": "BINA-SENT-02",
        "ilce_adi": "Kadıköy",
        "mahalle": "Caferağa",
    },
    {
        "ada_parsel": "2345/3",
        "alan_m2": 380.0,
        "kat_sayisi": 7,
        "bb_sayisi": 21,
        "nufus": 41,
        "bina_no": "BINA-SENT-03",
        "ilce_adi": "Kadıköy",
        "mahalle": "Caferağa",
    },
]


def build_geodataframe() -> gpd.GeoDataFrame:
    geometries = []
    for i in range(len(BUILDINGS)):
        x0 = BASE_LON + i * GAP
        y0 = BASE_LAT
        geometries.append(box(x0, y0, x0 + BUILDING_W, y0 + BUILDING_H))
    gdf = gpd.GeoDataFrame(BUILDINGS, geometry=geometries, crs="EPSG:4326")
    return gdf


def write_gml(gdf: gpd.GeoDataFrame, path: Path) -> None:
    gdf.to_file(path, driver="GML")


def write_shapefile_zip(gdf: gpd.GeoDataFrame, zip_path: Path) -> None:
    tmp_dir = zip_path.parent / "_shp_tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    shp_path = tmp_dir / "synthetic_buildings.shp"
    gdf.to_file(shp_path, driver="ESRI Shapefile")
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in tmp_dir.glob("synthetic_buildings.*"):
            zf.write(f, arcname=f.name)
    shutil.rmtree(tmp_dir)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gdf = build_geodataframe()
    write_gml(gdf, OUT_DIR / "synthetic_buildings.gml")
    write_shapefile_zip(gdf, OUT_DIR / "synthetic_buildings_shp.zip")
    print(f"Yazıldı: {OUT_DIR / 'synthetic_buildings.gml'}")
    print(f"Yazıldı: {OUT_DIR / 'synthetic_buildings_shp.zip'}")


if __name__ == "__main__":
    main()
