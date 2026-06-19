"""Bölgesel m² satış fiyatı tahmini (vizyon §1.B, Kârlılık Endeksi'ndeki
P_satış girdisi).

ÖNEMLİ — basitleştirilmiş iskelet: Tam GWR (Geographically Weighted
Regression: çok değişkenli, katsayıları mekansal olarak değişen
regresyon) için `mgwr` kütüphanesi ve gerçek, çok değişkenli satış verisi
gerekir. Bu ajan sandbox'ında internet erişimi olmadığından `mgwr`/
`numpy` kurulamamış, elimizde de gerçek satış verisi bulunmamaktadır.
Bu yüzden burada, **dış bağımlılık gerektirmeyen ve gerçekten test
edilebilen** bir "GWR-lite" uygulanmıştır: coğrafi mesafeye göre Gauss
çekirdek ağırlıklı yerel ortalama (Nadaraya–Watson tipi kernel
regresyon). Bu, GWR'nin sadece sabit terimli, tek değişkenli özel bir
hâli sayılabilir.

Gerçek veri/`mgwr` temin edilince yapılması gereken: bu modülü
`mgwr.gwr.GWR` + `mgwr.sel_bw.Sel_bw` ile çok değişkenli (m², kat,
manzara/viewshed skoru, deprem riski vb. açıklayıcı değişkenli) bir
modele yükseltmek; dış API (`predict()` girdi/çıktı sözleşmesi) aynı
kalabilir.

GERÇEK SATIŞ VERİSİ YOKTUR: `synthetic_sales()` tamamen SENTETİK
(uydurma) veri üretir, sadece demo/test amaçlıdır. Üretilen tahminler
hiçbir şekilde gerçek bir değerleme/rapor/sözleşme için kullanılmamalıdır.
"""
from __future__ import annotations

import math
import random


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
