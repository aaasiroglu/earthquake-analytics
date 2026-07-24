"""Kentsel dönüşüm hesaplama motoru.

Bu modül, gerçek imar/kadastro mevzuatının basitleştirilmiş bir
yaklaşımıdır (TAKS/KAKS, kat sayısı, bağımsız bölüm ve maliyet/kâr).
Sonuçlar tahmini olup ruhsat/imar başvurusu için resmi belge değildir.
"""
import math
from pydantic import BaseModel, Field

# ── 6306 Sayılı Kanun Sabitleri (4 Şubat 2026 yönetmelik değişikliği) ───────────────
_LAW_6306_NEW_THRESHOLD_LABEL = "Arsa payı salt çoğunluk — %50+1 (4 Şubat 2026 sonrası)"
_LAW_6306_OLD_THRESHOLD_LABEL = "Eski eşik — 2/3 (~%66,7)"
_LAW_6306_CONTRACTOR_TERMINATION = (
    "Müteahhit ruhsattan itibaren 1 yıl içinde başlamazsa veya inşaatı "
    "6 ay durursa, kat malikleri %50+1 çoğunlukla tek taraflı fesih hakkına sahiptir."
)
_LAW_6306_NONCONSENTING = (
    "Anlaşmayan maliklerin arsa payı rayiç değerden az olmamak üzere satışa çıkarılır; "
    "satılmazsa TOKİ bu payı satın alır."
)
_LAW_6306_NOTIFICATION = (
    "Karar sonrası 15 günlük ilan/tebligat süresi uygulanır."
)

# ── Yarısı Bizden Devlet Desteği Sabitleri ──────────────────────────────────────────
_YB_GRANT_RESIDENTIAL_TL: float = 875_000.0      # konut hibesi
_YB_CREDIT_RESIDENTIAL_TL: float = 875_000.0     # konut kredisi
_YB_EXTRA_UNIT_CREDIT_TL: float = 1_750_000.0   # ek bağımsız bölüm için kredi
_YB_RELOCATION_ONETIME_TL: float = 125_000.0    # tek seferlik taşınma desteği
_YB_RELOCATION_MONTHLY_TL: float = 8_000.0      # aylık kira yardımı
_YB_RELOCATION_MONTHS: int = 18
_YB_DEADLINE = "31 Aralık 2026"
_YB_MIN_LICENSE_YEAR = 2023
_YB_MIN_LICENSE_MONTH = 4   # Nisan
_YB_MAX_UNIT_RATIO = 1.5    # yeni bağımsız bölüm ≤ mevcut × 1.5


# ── Yeni Modeller ────────────────────────────────────────────────────────────────────

class Law6306Info(BaseModel):
    """6306 Sayılı Kanun karar nisabı bilgisi."""
    owner_count: int
    required_new_threshold: int
    required_old_threshold: int
    new_threshold_label: str
    old_threshold_label: str
    contractor_termination_note: str
    nonconsenting_owner_note: str
    notification_note: str


class YarısıBizdenInfo(BaseModel):
    """Yarısı Bizden devlet desteği uygunluk ve tutar bilgisi."""
    eligible: bool
    ineligibility_reasons: list[str]
    grant_per_unit_tl: float
    credit_per_unit_tl: float
    total_per_unit_tl: float
    relocation_option_a_tl: float
    relocation_option_b_description: str
    total_for_all_owners_tl: float
    deadline: str
    repayment_note: str
    disclaimer: str


class SerefiyeInput(BaseModel):
    """Kat bazında şerefiye (dikey hedonik fiyatlama) hesabı girdisi."""
    total_floor_count: int = Field(gt=0, description="Toplam kat sayısı")
    avg_unit_size_m2: float = Field(gt=0, description="Ortalama bağımsız bölüm büyüklüğü (m²)")
    sale_price_per_m2: float = Field(gt=0, description="Zemin kat referans satış fiyatı (TL/m²)")
    top_floor_premium_pct: float = Field(
        default=0.25, ge=0, le=1,
        description="En üst katın zemine göre değer primi (0-1, varsayılan %25)",
    )


class SerefiyeFloor(BaseModel):
    floor_num: int
    serefiye_factor: float
    estimated_price_per_m2: float
    estimated_unit_value_tl: float
    tier: str  # "zemin" | "orta" | "üst" | "en üst"


class SerefiyeResult(BaseModel):
    floors: list[SerefiyeFloor]
    avg_factor: float
    methodology_note: str
    disclaimer: str


class CalculationInput(BaseModel):
    parcel_area_m2: float = Field(gt=0, description="Birleştirilmiş parsel alanı (m²)")
    existing_footprint_area_m2: float = Field(ge=0, description="Mevcut bina(lar) ayak izi toplamı (m²)")
    existing_floor_count: int = Field(ge=0, description="Mevcut bina kat sayısı")
    existing_unit_count: int = Field(ge=0, description="Mevcut bağımsız bölüm sayısı")
    owner_count: int = Field(gt=0, description="Hak sahibi sayısı")
    population: int | None = Field(default=None, ge=0, description="Etkilenen nüfus (opsiyonel, MAKS'tan)")
    target_taks: float = Field(gt=0, lt=1, description="Hedef taban alanı kat sayısı (0-1)")
    target_kaks: float = Field(gt=0, description="Hedef emsal (KAKS)")
    avg_unit_size_m2: float = Field(gt=0, description="Hedef ortalama bağımsız bölüm büyüklüğü (m²)")
    floor_height_m: float = Field(default=3.0, gt=0, description="Kat yüksekliği (m)")
    construction_cost_per_m2: float = Field(gt=0, description="m² başına inşaat maliyeti (TL)")
    sale_price_per_m2: float = Field(gt=0, description="m² başına satış fiyatı (TL)")
    # ── Opsiyonel alanlar (yeni özellikler için) ─────────────────────────────────
    district: str | None = Field(default=None, description="İlçe adı (fiyat modeli için)")
    license_year: int | None = Field(
        default=None, ge=2020, le=2030,
        description="Yeni inşaat ruhsat yılı (Yarısı Bizden uygunluk kontrolü için)",
    )
    license_month: int | None = Field(
        default=None, ge=1, le=12,
        description="Yeni inşaat ruhsat ayı, 1-12 (Yarısı Bizden için)",
    )
    is_commercial: bool = Field(
        default=False, description="İşyeri mi? (Yarısı Bizden tutarları yarıya iner)",
    )
    logistics_cost_ratio: float = Field(
        default=0.08, ge=0, lt=1,
        description="Yıkım/nakliye/lojistik maliyet oranı (inşaat maliyetine göre, varsayılan %8)",
    )
    current_market_value_per_m2: float | None = Field(
        default=None, ge=0,
        description="Mevcut yapı rayiç değeri TL/m² (Kârlılık İndeksi K için; girilmezse satış fiyatının %60'ı kullanılır)",
    )
    project_duration_years: float = Field(
        default=2.0, gt=0,
        description="Tahmini proje süresi yıl (Kârlılık İndeksi K paydası)",
    )


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
    area_per_resident_m2: float | None
    contractor_sellable_area_m2: float
    estimated_cost_tl: float
    estimated_revenue_tl: float
    estimated_profit_tl: float
    # ── Yeni alanlar ──────────────────────────────────────────────────────────────
    existing_construction_area_m2: float
    logistics_cost_tl: float
    profitability_index: float
    profitability_index_note: str
    law_6306: Law6306Info
    yarisi_bizden: YarısıBizdenInfo | None
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

    area_per_resident_m2 = round(total_construction_area_m2 / inp.population, 2) if inp.population else None
    if area_per_resident_m2 is not None:
        notes.append(
            "Kişi başına alan, toplam inşaat alanına göre hesaplanır; hak "
            "sahibi payı (area_per_owner_m2) ile karıştırılmamalıdır."
        )

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

    # ── Lojistik maliyet ve Kârlılık İndeksi (K) ─────────────────────────────────
    logistics_cost_tl = round(estimated_cost_tl * inp.logistics_cost_ratio, 2)

    existing_construction_area_m2 = round(
        inp.existing_floor_count * inp.existing_footprint_area_m2, 2
    )

    if inp.current_market_value_per_m2 is not None:
        current_val_per_m2 = inp.current_market_value_per_m2
        k_note = "Kârlılık İndeksi: girilen mevcut rayiç değer kullanıldı."
    else:
        current_val_per_m2 = inp.sale_price_per_m2 * 0.6
        k_note = (
            "Kârlılık İndeksi: mevcut yapı rayiç değeri girilmediğinden "
            f"satış fiyatının %60'ı ({current_val_per_m2:.0f} TL/m²) tahmin olarak kullanıldı."
        )

    # K = [(V_yeni × P_satış) − (V_mevcut × P_rayiç) − C_inşaat − C_lojistik] / Zaman
    k_numerator = (
        (total_construction_area_m2 * inp.sale_price_per_m2)
        - (existing_construction_area_m2 * current_val_per_m2)
        - estimated_cost_tl
        - logistics_cost_tl
    )
    profitability_index = round(k_numerator / inp.project_duration_years, 2)

    # ── 6306 Sayılı Kanun karar nisabı ────────────────────────────────────────────
    required_new = math.floor(inp.owner_count / 2) + 1   # %50+1 (salt çoğunluk)
    required_old = math.ceil(inp.owner_count * 2 / 3)    # 2/3

    law_6306 = Law6306Info(
        owner_count=inp.owner_count,
        required_new_threshold=required_new,
        required_old_threshold=required_old,
        new_threshold_label=_LAW_6306_NEW_THRESHOLD_LABEL,
        old_threshold_label=_LAW_6306_OLD_THRESHOLD_LABEL,
        contractor_termination_note=_LAW_6306_CONTRACTOR_TERMINATION,
        nonconsenting_owner_note=_LAW_6306_NONCONSENTING,
        notification_note=_LAW_6306_NOTIFICATION,
    )

    # ── Yarısı Bizden uygunluk ve tutar hesabı ────────────────────────────────────
    yarisi_bizden: YarısıBizdenInfo | None = None
    if inp.license_year is not None:
        ineligibility: list[str] = []

        # Ruhsat tarihi kontrolü: 1 Nisan 2023 veya sonrası
        lic_year = inp.license_year
        lic_month = inp.license_month or 1
        after_cutoff = (lic_year > _YB_MIN_LICENSE_YEAR) or (
            lic_year == _YB_MIN_LICENSE_YEAR and lic_month >= _YB_MIN_LICENSE_MONTH
        )
        if not after_cutoff:
            ineligibility.append(
                "Ruhsat tarihi 1 Nisan 2023 öncesi — "
                "Yarısı Bizden yalnızca 1 Nisan 2023 sonrası ruhsatlara uygulanır."
            )

        # Yeni bağımsız bölüm sayısı kontrolü (≤ mevcut × 1.5)
        if inp.existing_unit_count > 0:
            unit_ratio = total_unit_count_estimate / inp.existing_unit_count
            if unit_ratio > _YB_MAX_UNIT_RATIO:
                ineligibility.append(
                    "Yeni bağımsız bölüm sayısı (%.0f) mevcut sayının (%.0f) "
                    "1,5 katını (%.0f) aşıyor." % (
                        total_unit_count_estimate,
                        inp.existing_unit_count,
                        inp.existing_unit_count * _YB_MAX_UNIT_RATIO,
                    )
                )

        eligible = len(ineligibility) == 0

        multiplier = 0.5 if inp.is_commercial else 1.0
        grant = _YB_GRANT_RESIDENTIAL_TL * multiplier
        credit = _YB_CREDIT_RESIDENTIAL_TL * multiplier
        total_per_unit = grant + credit
        total_all = total_per_unit * inp.owner_count

        yarisi_bizden = YarısıBizdenInfo(
            eligible=eligible,
            ineligibility_reasons=ineligibility,
            grant_per_unit_tl=grant,
            credit_per_unit_tl=credit,
            total_per_unit_tl=total_per_unit,
            relocation_option_a_tl=_YB_RELOCATION_ONETIME_TL,
            relocation_option_b_description=(
                "%.0f TL/ay × %d ay = %.0f TL kira yardımı (ikisi arasından biri seçilir)" % (
                    _YB_RELOCATION_MONTHLY_TL,
                    _YB_RELOCATION_MONTHS,
                    _YB_RELOCATION_MONTHLY_TL * _YB_RELOCATION_MONTHS,
                )
            ),
            total_for_all_owners_tl=total_all,
            deadline=_YB_DEADLINE,
            repayment_note="10 yıl vade, geri ödeme ruhsat tarihinden 2 yıl sonra başlar.",
            disclaimer=(
                "Tutarlar 2026 yılı itibarıyla geçerlidir. Son sözleşme tarihi "
                + _YB_DEADLINE
                + ". Resmi başvuru için ilgili belediye/TOKİ birimi esas alınmalıdır."
            ),
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
        area_per_resident_m2=area_per_resident_m2,
        contractor_sellable_area_m2=round(contractor_sellable_area_m2, 2),
        estimated_cost_tl=round(estimated_cost_tl, 2),
        estimated_revenue_tl=round(estimated_revenue_tl, 2),
        estimated_profit_tl=round(estimated_profit_tl, 2),
        existing_construction_area_m2=existing_construction_area_m2,
        logistics_cost_tl=logistics_cost_tl,
        profitability_index=profitability_index,
        profitability_index_note=k_note,
        law_6306=law_6306,
        yarisi_bizden=yarisi_bizden,
        notes=notes,
    )


class ScenarioInput(BaseModel):
    base: CalculationInput
    floor_counts: list[int] = Field(min_length=1, description="Denenecek kat sayısı seçenekleri")


class ScenarioRow(BaseModel):
    floor_count: int
    target_taks: float
    target_kaks: float
    result: CalculationResult


class ScenarioOutput(BaseModel):
    rows: list[ScenarioRow]


def calculate_scenarios(inp: ScenarioInput) -> ScenarioOutput:
    """Aynı parsel için farklı kat sayısı seçeneklerini karşılaştırır.

    Her seçenek için hedef TAKS sabit tutulup KAKS = TAKS × kat sayısı olarak
    türetilir, böylece tek hesaplama mantığı (calculate) çatallanmadan
    yeniden kullanılır.
    """
    rows: list[ScenarioRow] = []
    for floor_count in inp.floor_counts:
        if floor_count <= 0:
            continue
        derived_kaks = inp.base.target_taks * floor_count
        scenario_input = inp.base.model_copy(update={"target_kaks": derived_kaks})
        result = calculate(scenario_input)
        rows.append(
            ScenarioRow(
                floor_count=floor_count,
                target_taks=inp.base.target_taks,
                target_kaks=round(derived_kaks, 4),
                result=result,
            )
        )
    return ScenarioOutput(rows=rows)


def calculate_serefiye(inp: SerefiyeInput) -> SerefiyeResult:
    """Kat bazında şerefiye faktörü hesabı (basitleştirilmiş dikey hedonik fiyatlama).

    Gerçek şerefiye analizi için Viewshed (görüş alanı), Sky View Factor (SVF) ve
    gürültü haritalarından türetilmiş 3D GIS katmanları gerekir. Bu fonksiyon,
    yalnızca kat yüksekliğine dayalı doğrusal bir yaklaşım uygular:
      - Zemin kat (1) → şerefiye_faktörü = 1.0 (baz)
      - En üst kat    → şerefiye_faktörü = 1.0 + top_floor_premium_pct
      - Ara katlar    → doğrusal interpolasyon

    Sonuçlar adil paylaşım (kat karşılığı daire dağılımı) müzakerelerinde yol
    gösterici olarak kullanılabilir; sözleşme değeri taşımaz.
    """
    n = inp.total_floor_count
    floors: list[SerefiyeFloor] = []

    for floor_num in range(1, n + 1):
        if n == 1:
            factor = 1.0
        else:
            factor = 1.0 + (floor_num - 1) / (n - 1) * inp.top_floor_premium_pct

        price_per_m2 = inp.sale_price_per_m2 * factor
        unit_value = price_per_m2 * inp.avg_unit_size_m2

        if floor_num == n:
            tier = "en üst"
        elif n > 3 and floor_num > n * 0.6:
            tier = "üst"
        elif floor_num <= 2:
            tier = "zemin"
        else:
            tier = "orta"

        floors.append(
            SerefiyeFloor(
                floor_num=floor_num,
                serefiye_factor=round(factor, 4),
                estimated_price_per_m2=round(price_per_m2, 2),
                estimated_unit_value_tl=round(unit_value, 2),
                tier=tier,
            )
        )

    avg_factor = sum(f.serefiye_factor for f in floors) / len(floors) if floors else 1.0

    return SerefiyeResult(
        floors=floors,
        avg_factor=round(avg_factor, 4),
        methodology_note=(
            "Kat bazında doğrusal interpolasyon (zemin=1.0, en üst=1+prim). "
            "Gerçek şerefiye hesabı için Viewshed, Sky View Factor (SVF) ve "
            "gürültü haritası gerektiren 3D GIS analizi yapılmalıdır (Bölüm 1C)."
        ),
        disclaimer=(
            "Şerefiye değerleri tahminidir; adil paylaşım sözleşmelerinde "
            "lisanslı UDES (Uluslararası Değerleme Standartları) uzman raporu esas alınır."
        ),
    )
