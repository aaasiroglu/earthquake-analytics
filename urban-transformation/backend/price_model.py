"""Sentetik GWR-lite fiyat modeli.

Gerçek satış verisi ve mgwr entegrasyonuna geçiş için bir yol haritası sunar:

  Aşama 1 (mevcut): Sabit ilçe bazlı SENTETİK referans fiyat tablosu.
  Aşama 2 (Faz 1 adayı, bağımlılıksız): TCMB Konut Fiyat Endeksi (KFE) çarpanıyla
    bölgesel kalibrasyon — e-Devlet/TCMB açık veri, dış API anlaşması gerektirmez.
  Aşama 3 (Faz 2): Gerçek satış verisi + mgwr/numpy ile çok değişkenli GWR.
    Tobler'ın Birinci Coğrafya Kanunu baz alınarak koordinata göre dinamik
    hiper-parametre optimizasyonu — hedef MAPE < %3.

UYARI: Bu modelin tüm fiyatları HİPOTETİK SENARYOLAR içindir.
Hukuki veya finansal karar vermede kullanılamaz.
"""
from __future__ import annotations

import math
import random
import re

# ── İstanbul ilçe bazlı sentetik referans fiyatlar (TL/m², 2025 kalibrasyonu) ──────
# Kaynak: SENTETİK / test verisi — gerçek piyasa satış kaydı DEĞİL
# Aşama 2'de TCMB KFE bölgesel çarpanıyla kalibre edilecek.
_DISTRICT_BASE_PRICES: dict[str, float] = {
    # Avrupa yakası – merkez/prestij
    "beşiktaş": 95_000,
    "sarıyer": 88_000,
    "beyoğlu": 72_000,
    "şişli": 70_000,
    "bakırköy": 65_000,
    "zeytinburnu": 50_000,
    "fatih": 55_000,
    "eyüpsultan": 45_000,
    "kağıthane": 48_000,
    "bahçelievler": 48_000,
    "bayrampaşa": 42_000,
    "güngören": 38_000,
    "bağcılar": 36_000,
    "esenler": 33_000,
    "gaziosmanpaşa": 38_000,
    "sultangazi": 32_000,
    # Avrupa yakası – çevre
    "başakşehir": 45_000,
    "küçükçekmece": 42_000,
    "avcılar": 40_000,
    "esenyurt": 30_000,
    "beylikdüzü": 38_000,
    "büyükçekmece": 40_000,
    "arnavutköy": 28_000,
    "silivri": 25_000,
    "çatalca": 22_000,
    # Anadolu yakası – merkez/prestij
    "kadıköy": 75_000,
    "ataşehir": 65_000,
    "üsküdar": 60_000,
    "beykoz": 68_000,
    "adalar": 80_000,
    "ümraniye": 50_000,
    "maltepe": 52_000,
    # Anadolu yakası – çevre
    "kartal": 45_000,
    "pendik": 40_000,
    "tuzla": 38_000,
    "sultanbeyli": 30_000,
    "sancaktepe": 32_000,
    "çekmeköy": 42_000,
}

_DEFAULT_PRICE: float = 50_000  # İlçe eşleşmezse kullanılan tahmini değer

# ── TCMB KFE kalibrasyonu (Aşama 2 yer tutucu) ─────────────────────────────────────
# Değer 1.0 = kalibre edilmemiş (Aşama 1). Gerçek TCMB bölgesel KFE verisi
# geldiğinde ilçe bazlı sözlük olarak genişletilecek.
_TCMB_KFE_MULTIPLIER: float = 1.0


def _normalize_district(name: str) -> str:
    """Türkçe karakter ve büyük/küçük harf farklılıklarını gidererek eşleştirme yapar."""
    replacements = {
        "ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c",
        "İ": "i", "Ğ": "g", "Ü": "u", "Ş": "s", "Ö": "o", "Ç": "c",
    }
    name = name.strip().lower()
    for src, dst in replacements.items():
        name = name.replace(src, dst)
    return re.sub(r"\s+", "", name)


def _build_normalized_index() -> dict[str, tuple[str, float]]:
    """Normalize edilmiş anahtar → (orijinal ilçe adı, baz fiyat) eşleşme tablosu."""
    return {_normalize_district(k): (k, v) for k, v in _DISTRICT_BASE_PRICES.items()}


_NORMALIZED_INDEX = _build_normalized_index()


def estimate_price(district: str, floor_factor: float = 1.0) -> dict:
    """İlçe ve kat faktörüne göre sentetik GWR-lite fiyat tahmini döner.

    Args:
        district: İlçe adı (büyük/küçük harf ve Türkçe karakter toleranslı).
        floor_factor: Dikey şerefiye çarpanı (1.0 = zemin/referans, >1.0 = üst katlar).

    Returns:
        price_per_m2 (TL), base_price_per_m2, district_resolved, tcmb_kfe_multiplier,
        source, disclaimer.
    """
    key_normalized = _normalize_district(district)
    match = _NORMALIZED_INDEX.get(key_normalized)

    if match:
        resolved_name, base = match
    else:
        resolved_name = None
        base = _DEFAULT_PRICE

    price = round(base * floor_factor * _TCMB_KFE_MULTIPLIER, 2)

    return {
        "district": district,
        "district_resolved": resolved_name,
        "price_per_m2": price,
        "base_price_per_m2": base,
        "floor_factor": round(floor_factor, 4),
        "tcmb_kfe_multiplier": _TCMB_KFE_MULTIPLIER,
        "source": "synthetic_v1",
        "upgrade_roadmap": (
            "Aşama 1 (mevcut): sentetik ilçe bazlı tablo. "
            "Aşama 2: TCMB KFE bölgesel çarpanı. "
            "Aşama 3: gerçek satış verisi + mgwr çok değişkenli GWR (hedef MAPE < %%3)."
        ),
        "disclaimer": (
            "Bu fiyat SENTETİK veridir — gerçek piyasa verisi değil. "
            "Hukuki veya finansal kararlarda kullanılamaz."
        ),
    }


# ── GWR-lite (Nadaraya-Watson): /price/predict ve /scan için ─────────────────────────

def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def synthetic_sales(center_lon: float, center_lat: float, n: int = 60, seed: int = 42) -> list[dict[str, float]]:
    """Merkeze yakın noktalarda daha yüksek fiyat eğilimi olan, gürültülü
    SENTETİK (sahte) satış verisi üretir — sadece demo/test amaçlı."""
    rng = random.Random(seed)
    sales = []
    for _ in range(n):
        d_lon = rng.uniform(-0.02, 0.02)
        d_lat = rng.uniform(-0.02, 0.02)
        lon, lat = center_lon + d_lon, center_lat + d_lat
        distance_km = _haversine_km(center_lon, center_lat, lon, lat)
        base_price = 80000 - distance_km * 18000
        noise = rng.uniform(-8000, 8000)
        price = max(20000.0, base_price + noise)
        sales.append({"lon": lon, "lat": lat, "price_per_m2": round(price, 2)})
    return sales


class KernelWeightedPriceModel:
    """Coğrafi mesafeye göre Gauss ağırlıklı yerel ortalama ("GWR-lite")."""

    def __init__(self, sales: list[dict[str, float]], bandwidth_km: float = 1.5):
        if not sales:
            raise ValueError("Eğitim verisi (satış noktaları) boş olamaz.")
        self._sales = sales
        self._bandwidth_km = bandwidth_km

    def predict(self, lon: float, lat: float) -> dict[str, float]:
        weights = [
            math.exp(-(_haversine_km(lon, lat, s["lon"], s["lat"]) / self._bandwidth_km) ** 2)
            for s in self._sales
        ]
        total_weight = sum(weights)
        if total_weight <= 1e-9:
            avg = sum(s["price_per_m2"] for s in self._sales) / len(self._sales)
            return {"predicted_price_per_m2": round(avg, 2), "effective_sample_size": 0.0}
        predicted = sum(w * s["price_per_m2"] for w, s in zip(weights, self._sales)) / total_weight
        effective_n = (total_weight ** 2) / sum(w ** 2 for w in weights)
        return {"predicted_price_per_m2": round(predicted, 2), "effective_sample_size": round(effective_n, 2)}
