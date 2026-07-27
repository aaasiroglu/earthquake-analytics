"""Konut yatırımcısı için mekânsal fırsat skorlama modeli.

Bu modül, gerçek belediye/MAKS/iskan ve satış kayıtları bağlanana kadar arayüz,
API sözleşmesi ve karar destek akışını göstermek için şeffaf sentetik veriler
üretir. Skorlar kesin yatırım, deprem güvenliği veya dönüşüm taahhüdü değildir.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


DATA_SOURCE = "synthetic_demo_v1"
DISCLAIMER = (
    "Bu ekran demo/sentetik veriye dayanır. Bina bazında dönüşüm olasılığı, deprem "
    "güvenliği veya satış fiyatı taahhüdü vermez; resmî imar, risk tespiti, tapu, "
    "iskan ve lisanslı değerleme kayıtlarıyla doğrulanmalıdır."
)


@dataclass(frozen=True)
class NeighborhoodSeed:
    name: str
    district: str
    center: tuple[float, float]
    base_price_per_m2: int
    transformation_potential: int
    unsaturated_supply: int
    liquidity: int
    planned_access: int
    building_stock_age: int


_NEIGHBORHOODS: tuple[NeighborhoodSeed, ...] = (
    NeighborhoodSeed("Fikirtepe", "Kadıköy", (29.0840, 40.9830), 92_000, 78, 42, 88, 91, 68),
    NeighborhoodSeed("Osmanağa", "Kadıköy", (29.0265, 40.9897), 118_000, 51, 22, 94, 96, 42),
    NeighborhoodSeed("Cevizli", "Kartal", (29.2000, 40.9050), 58_000, 73, 71, 76, 84, 64),
    NeighborhoodSeed("Yalı", "Maltepe", (29.1230, 40.9230), 67_000, 65, 55, 79, 87, 58),
    NeighborhoodSeed("Küçükbakkalköy", "Ataşehir", (29.1210, 40.9870), 78_000, 69, 63, 85, 89, 61),
    NeighborhoodSeed("Merkez", "Avcılar", (28.7250, 40.9790), 44_000, 81, 77, 68, 72, 73),
)


class InvestorProfile(BaseModel):
    budget_tl: float = Field(gt=0, description="Toplam satın alma bütçesi (TL)")
    intent: Literal["investment", "living"] = "investment"
    risk_appetite: int = Field(default=3, ge=1, le=5, description="1 temkinli, 5 yüksek risk iştahı")
    min_transformation_potential: int = Field(default=50, ge=0, le=100)
    min_unit_m2: float = Field(default=70, gt=0, le=500)


class NeighborhoodOpportunity(BaseModel):
    neighborhood: str
    district: str
    lon: float
    lat: float
    price_per_m2: float
    affordable_unit_m2: float
    affordable: bool
    transformation_potential: int
    unsaturated_supply_score: int
    liquidity_score: int
    investment_score: int
    rationale: list[str]


class RecommendationResponse(BaseModel):
    profile: InvestorProfile
    neighborhoods: list[NeighborhoodOpportunity]
    methodology: str
    data_source: str
    disclaimer: str


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def _investment_score(seed: NeighborhoodSeed, profile: InvestorProfile) -> int:
    affordability = min(100, profile.budget_tl / (seed.base_price_per_m2 * profile.min_unit_m2) * 100)
    risk_weight = (profile.risk_appetite - 1) / 4
    transformation_weight = 0.38 + 0.14 * risk_weight
    supply_weight = 0.28 + 0.12 * risk_weight
    liquidity_weight = 0.20 - 0.08 * risk_weight
    access_weight = 1 - transformation_weight - supply_weight - liquidity_weight
    living_adjustment = 8 if profile.intent == "living" else 0
    return _clamp(
        affordability * 0.20
        + seed.transformation_potential * transformation_weight
        + seed.unsaturated_supply * supply_weight
        + seed.liquidity * liquidity_weight
        + seed.planned_access * access_weight
        + living_adjustment
    )


def _rationale(seed: NeighborhoodSeed, affordable_m2: float) -> list[str]:
    messages = [
        f"Tahmini erişilebilir büyüklük: {affordable_m2:.0f} m².",
        f"Doygunlaşmamış yeni konut arzı göstergesi: {seed.unsaturated_supply}/100.",
    ]
    if seed.transformation_potential >= 70:
        messages.append("Bina stoku ve dönüşüm göstergesi göreli olarak yüksek.")
    if seed.liquidity >= 80:
        messages.append("Likidite göstergesi güçlü; alım-satım karşılaştırması için daha fazla emsal bulunabilir.")
    return messages


def recommend_neighborhoods(profile: InvestorProfile) -> RecommendationResponse:
    opportunities: list[NeighborhoodOpportunity] = []
    for seed in _NEIGHBORHOODS:
        affordable_m2 = profile.budget_tl / seed.base_price_per_m2
        if seed.transformation_potential < profile.min_transformation_potential:
            continue
        opportunities.append(
            NeighborhoodOpportunity(
                neighborhood=seed.name,
                district=seed.district,
                lon=seed.center[0],
                lat=seed.center[1],
                price_per_m2=seed.base_price_per_m2,
                affordable_unit_m2=round(affordable_m2, 1),
                affordable=affordable_m2 >= profile.min_unit_m2,
                transformation_potential=seed.transformation_potential,
                unsaturated_supply_score=seed.unsaturated_supply,
                liquidity_score=seed.liquidity,
                investment_score=_investment_score(seed, profile),
                rationale=_rationale(seed, affordable_m2),
            )
        )
    opportunities.sort(key=lambda item: item.investment_score, reverse=True)
    return RecommendationResponse(
        profile=profile,
        neighborhoods=opportunities,
        methodology=(
            "Fırsat skoru; bütçeye göre erişilebilir büyüklük (%20), dönüşüm göstergesi, "
            "doygunlaşmamış arz, likidite ve erişim göstergelerinin şeffaf ağırlıklı toplamıdır. "
            "Risk iştahı yükseldikçe dönüşüm ve arz ağırlığı artar."
        ),
        data_source=DATA_SOURCE,
        disclaimer=DISCLAIMER,
    )


def opportunity_geojson(profile: InvestorProfile) -> dict:
    """Haritada 3B gösterim için mahalle merkezlerinde sentetik bina kütleleri üretir."""
    rows = recommend_neighborhoods(profile).neighborhoods
    row_by_name = {row.neighborhood: row for row in rows}
    features: list[dict] = []
    for neighborhood_index, seed in enumerate(_NEIGHBORHOODS):
        result = row_by_name.get(seed.name)
        if not result:
            continue
        lon, lat = seed.center
        for building_index in range(12):
            column = building_index % 4
            row = building_index // 4
            delta_lon = (column - 1.5) * 0.00042
            delta_lat = (row - 1) * 0.00036
            half_lon, half_lat = 0.00015, 0.00012
            building_age = max(12, seed.building_stock_age + ((building_index * 7) % 19) - 9)
            potential = _clamp(seed.transformation_potential + ((building_index * 11) % 17) - 8)
            estimated_m2 = round(seed.base_price_per_m2 * (0.91 + (building_index % 5) * 0.035), -2)
            unit_m2 = 75 + (building_index % 4) * 10
            total_price = int(estimated_m2 * unit_m2)
            score = _clamp(result.investment_score + ((building_index * 5) % 13) - 6)
            height = 15 + (building_index % 7) * 3
            polygon = [
                [lon + delta_lon - half_lon, lat + delta_lat - half_lat],
                [lon + delta_lon + half_lon, lat + delta_lat - half_lat],
                [lon + delta_lon + half_lon, lat + delta_lat + half_lat],
                [lon + delta_lon - half_lon, lat + delta_lat + half_lat],
                [lon + delta_lon - half_lon, lat + delta_lat - half_lat],
            ]
            features.append({
                "type": "Feature",
                "id": f"{neighborhood_index}-{building_index}",
                "properties": {
                    "neighborhood": seed.name,
                    "district": seed.district,
                    "opportunity_score": score,
                    "transformation_potential": potential,
                    "unsaturated_supply_score": seed.unsaturated_supply,
                    "building_age_estimate": building_age,
                    "estimated_price_per_m2_tl": estimated_m2,
                    "estimated_unit_m2": unit_m2,
                    "estimated_total_price_tl": total_price,
                    "affordable": total_price <= profile.budget_tl,
                    "height": height,
                    "data_source": DATA_SOURCE,
                },
                "geometry": {"type": "Polygon", "coordinates": [polygon]},
            })
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {"data_source": DATA_SOURCE, "disclaimer": DISCLAIMER},
    }
