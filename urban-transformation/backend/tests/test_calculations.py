"""Hesaplama motorunun kritik iş kuralları için bağımlılıksız regresyon testleri."""
import unittest

from calculations import (
    CalculationInput,
    ScenarioInput,
    SerefiyeInput,
    calculate,
    calculate_scenarios,
    calculate_serefiye,
)


class CalculationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.input = CalculationInput(
            parcel_area_m2=1_000,
            existing_footprint_area_m2=250,
            existing_floor_count=4,
            existing_unit_count=20,
            owner_count=20,
            population=60,
            target_taks=0.30,
            target_kaks=2.10,
            avg_unit_size_m2=100,
            construction_cost_per_m2=25_000,
            sale_price_per_m2=75_000,
            license_year=2025,
            license_month=6,
        )

    def test_calculation_returns_consistent_geometry_and_allocations(self) -> None:
        result = calculate(self.input)

        self.assertEqual(result.new_footprint_area_m2, 300)
        self.assertEqual(result.total_construction_area_m2, 2100)
        self.assertEqual(result.new_floor_count, 7)
        self.assertEqual(result.total_unit_count_estimate, 21)
        self.assertEqual(result.units_to_owners + result.units_to_contractor, 21)
        self.assertEqual(result.law_6306.required_new_threshold, 11)
        self.assertEqual(result.area_per_resident_m2, 35)

    def test_scenarios_derive_kaks_from_taks_and_floor_count(self) -> None:
        rows = calculate_scenarios(
            ScenarioInput(base=self.input, floor_counts=[4, 8])
        ).rows

        self.assertEqual([row.target_kaks for row in rows], [1.2, 2.4])
        self.assertEqual([row.result.new_floor_count for row in rows], [4, 8])

    def test_serefiye_top_floor_has_configured_premium(self) -> None:
        result = calculate_serefiye(
            SerefiyeInput(
                total_floor_count=4,
                avg_unit_size_m2=100,
                sale_price_per_m2=50_000,
                top_floor_premium_pct=0.20,
            )
        )

        self.assertEqual(result.floors[0].serefiye_factor, 1.0)
        self.assertEqual(result.floors[-1].serefiye_factor, 1.2)
        self.assertEqual(result.floors[-1].tier, "en üst")


if __name__ == "__main__":
    unittest.main()
