"""Şehir ölçekli Kârlılık Endeksi tarama motoru.

Tek parsel hesaplama motorunu (`calculations.calculate`) her parsel için
tekrar çalıştırıp sonuçları Kârlılık Endeksi'ne göre sıralar. Bu,
Evveko/Kolayimar gibi mevcut Türk rakiplerin sunduğu "tek parsel sorgusu /
reaktif eşleştirme" modelinden farklı olarak; müteahhidin başvuru
beklemeden tüm bölgeyi otomatik taradığı, **proaktif** bir fırsat
radarıdır (bkz. docs/VISION.md §3 "Müteahhit İçin En Kârlı Bölge
Optimizasyon Algoritması").

Kârlılık Endeksi burada `tahmini_kâr / tahmini_süre` olarak
basitleştirilmiştir; tahmini süre sabit bir varsayımdır (gerçek değer
ruhsat/inşaat takvimine bağlıdır). Bu modülün ürettiği sayılar SADECE
parseller arası SIRALAMA için kullanılmalıdır, finansal bir taahhüt
değildir — `price_model.py`'daki sentetik veri uyarısı burada da geçerlidir.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from calculations import CalculationInput, CalculationResult, calculate
from price_model import KernelWeightedPriceModel


def _centroid(geometry: dict[str, Any]) -> tuple[float, float]:
    if geometry["type"] == "Polygon":
        ring = geometry["coordinates"][0]
    elif geometry["type"] == "MultiPolygon":
        ring = geometry["coordinates"][0][0]
    else:
        raise ValueError(f"Desteklenmeyen geometri tipi: {geometry['type']!r}")
    lons = [c[0] for c in ring]
    lats = [c[1] for c in ring]
    return sum(lons) / len(lons), sum(lats) / len(lats)


class ScanParcel(BaseModel):
    parcel_id: str
    geometry: dict[str, Any]
    parcel_area_m2: float = Field(gt=0)
    existing_footprint_area_m2: float = Field(ge=0)
    existing_floor_count: int = Field(ge=0)
    existing_unit_count: int = Field(ge=0)
    owner_count: int = Field(gt=0)


class ScanParams(BaseModel):
    target_taks: float = Field(gt=0, lt=1)
    target_kaks: float = Field(gt=0)
    avg_unit_size_m2: float = Field(gt=0)
    floor_height_m: float = Field(default=3.0, gt=0)
    construction_cost_per_m2: float = Field(gt=0)
    estimated_duration_years: float = Field(default=2.0, gt=0)
    price_bandwidth_km: float = Field(default=1.5, gt=0)


class ScanResult(BaseModel):
    parcel_id: str
    profitability_index: float
    predicted_sale_price_per_m2: float
    price_effective_sample_size: float
    calculation: CalculationResult


def scan_parcels(
    parcels: list[ScanParcel],
    params: ScanParams,
    sales: list[dict[str, float]],
) -> list[ScanResult]:
    """Verilen parsel listesini Kârlılık Endeksi'ne göre büyükten küçüğe sıralar."""
    price_model = KernelWeightedPriceModel(sales, bandwidth_km=params.price_bandwidth_km)

    results: list[ScanResult] = []
    for parcel in parcels:
        lon, lat = _centroid(parcel.geometry)
        price = price_model.predict(lon, lat)

        calc_input = CalculationInput(
            parcel_area_m2=parcel.parcel_area_m2,
            existing_footprint_area_m2=parcel.existing_footprint_area_m2,
            existing_floor_count=parcel.existing_floor_count,
            existing_unit_count=parcel.existing_unit_count,
            owner_count=parcel.owner_count,
            target_taks=params.target_taks,
            target_kaks=params.target_kaks,
            avg_unit_size_m2=params.avg_unit_size_m2,
            floor_height_m=params.floor_height_m,
            construction_cost_per_m2=params.construction_cost_per_m2,
            sale_price_per_m2=price["predicted_price_per_m2"],
        )
        calc = calculate(calc_input)
        profitability_index = calc.estimated_profit_tl / params.estimated_duration_years

        results.append(
            ScanResult(
                parcel_id=parcel.parcel_id,
                profitability_index=round(profitability_index, 2),
                predicted_sale_price_per_m2=price["predicted_price_per_m2"],
                price_effective_sample_size=price["effective_sample_size"],
                calculation=calc,
            )
        )

    results.sort(key=lambda r: r.profitability_index, reverse=True)
    return results
