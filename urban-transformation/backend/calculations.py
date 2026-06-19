"""Kentsel dönüşüm hesaplama motoru.

Bu modül, gerçek imar/kadastro mevzuatının basitleştirilmiş bir
yaklaşımıdır (TAKS/KAKS, kat sayısı, bağımsız bölüm ve maliyet/kâr).
Sonuçlar tahmini olup ruhsat/imar başvurusu için resmi belge değildir.
"""
import math
from pydantic import BaseModel, Field


class CalculationInput(BaseModel):
    parcel_area_m2: float = Field(gt=0, description="Birleştirilmiş parsel alanı (m²)")
    existing_footprint_area_m2: float = Field(ge=0, description="Mevcut bina(lar) ayak izi toplamı (m²)")
    existing_floor_count: int = Field(ge=0, description="Mevcut bina kat sayısı")
    existing_unit_count: int = Field(ge=0, description="Mevcut bağımsız bölüm sayısı")
    owner_count: int = Field(gt=0, description="Hak sahibi sayısı")
    target_taks: float = Field(gt=0, lt=1, description="Hedef taban alanı kat sayısı (0-1)")
    target_kaks: float = Field(gt=0, description="Hedef emsal (KAKS)")
    avg_unit_size_m2: float = Field(gt=0, description="Hedef ortalama bağımsız bölüm büyüklüğü (m²)")
    floor_height_m: float = Field(default=3.0, gt=0, description="Kat yüksekliği (m)")
    construction_cost_per_m2: float = Field(gt=0, description="m² başına inşaat maliyeti (TL)")
    sale_price_per_m2: float = Field(gt=0, description="m² başına satış fiyatı (TL)")


class CalculationResult(BaseModel):
    existing_taks: float
    existing_kaks: float
    new_footprint_area_m2: float
    total_construction_area_m2: float
    new_floor_count: int
    building_height_m: float
    total_unit_count_estimate: int
    units_to_owners: int
    units_to_contractor: int
    area_per_owner_m2: float
    contractor_sellable_area_m2: float
    estimated_cost_tl: float
    estimated_revenue_tl: float
    estimated_profit_tl: float
    notes: list[str]


def calculate(inp: CalculationInput) -> CalculationResult:
    notes: list[str] = []

    existing_taks = (
        inp.existing_footprint_area_m2 / inp.parcel_area_m2 if inp.parcel_area_m2 else 0
    )
    existing_total_construction = inp.existing_floor_count * inp.existing_footprint_area_m2
    existing_kaks = existing_total_construction / inp.parcel_area_m2 if inp.parcel_area_m2 else 0

    new_footprint_area_m2 = inp.parcel_area_m2 * inp.target_taks
    total_construction_area_m2 = inp.parcel_area_m2 * inp.target_kaks

    new_floor_count = max(1, math.ceil(total_construction_area_m2 / new_footprint_area_m2))
    building_height_m = new_floor_count * inp.floor_height_m

    total_unit_count_estimate = max(
        inp.owner_count, math.floor(total_construction_area_m2 / inp.avg_unit_size_m2)
    )
    units_to_owners = min(inp.owner_count, total_unit_count_estimate)
    units_to_contractor = total_unit_count_estimate - units_to_owners
    if units_to_contractor == 0 and total_unit_count_estimate < inp.owner_count:
        notes.append(
            "Hesaplanan toplam bağımsız bölüm sayısı hak sahibi sayısından az: "
            "hedef KAKS/emsal değerini artırmanız gerekebilir."
        )

    area_per_owner_m2 = total_construction_area_m2 * units_to_owners / total_unit_count_estimate / inp.owner_count \
        if inp.owner_count and total_unit_count_estimate else 0.0
    contractor_sellable_area_m2 = units_to_contractor * inp.avg_unit_size_m2

    estimated_cost_tl = total_construction_area_m2 * inp.construction_cost_per_m2
    estimated_revenue_tl = contractor_sellable_area_m2 * inp.sale_price_per_m2
    estimated_profit_tl = estimated_revenue_tl - estimated_cost_tl

    if estimated_profit_tl < 0:
        notes.append(
            "Tahmini kâr negatif: müteahhite kalan satılabilir alan, inşaat "
            "maliyetini karşılamıyor. Emsal, daire büyüklüğü veya maliyet "
            "varsayımlarını gözden geçirin."
        )
    notes.append(
        "Bu hesaplama basitleştirilmiş bir yaklaşımdır; KDV, harç, ruhsat "
        "giderleri, kat karşılığı sözleşme şartları ve güncel imar planı "
        "kısıtları dahil değildir."
    )

    return CalculationResult(
        existing_taks=round(existing_taks, 4),
        existing_kaks=round(existing_kaks, 4),
        new_footprint_area_m2=round(new_footprint_area_m2, 2),
        total_construction_area_m2=round(total_construction_area_m2, 2),
        new_floor_count=new_floor_count,
        building_height_m=round(building_height_m, 2),
        total_unit_count_estimate=total_unit_count_estimate,
        units_to_owners=units_to_owners,
        units_to_contractor=units_to_contractor,
        area_per_owner_m2=round(area_per_owner_m2, 2),
        contractor_sellable_area_m2=round(contractor_sellable_area_m2, 2),
        estimated_cost_tl=round(estimated_cost_tl, 2),
        estimated_revenue_tl=round(estimated_revenue_tl, 2),
        estimated_profit_tl=round(estimated_profit_tl, 2),
        notes=notes,
    )
