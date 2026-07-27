"""Yatırım keşfi demo sözleşmesi için regresyon testleri."""
import unittest

from investment_model import InvestorProfile, opportunity_geojson, recommend_neighborhoods


class InvestmentModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = InvestorProfile(
            budget_tl=6_000_000,
            intent="investment",
            risk_appetite=3,
            min_transformation_potential=55,
            min_unit_m2=80,
        )

    def test_recommendations_are_sorted_and_transparent(self) -> None:
        response = recommend_neighborhoods(self.profile)

        self.assertEqual(response.data_source, "synthetic_demo_v1")
        self.assertTrue(response.disclaimer)
        self.assertTrue(response.neighborhoods)
        scores = [row.investment_score for row in response.neighborhoods]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(row.transformation_potential >= 55 for row in response.neighborhoods))

    def test_geojson_contains_renderable_building_properties(self) -> None:
        geojson = opportunity_geojson(self.profile)

        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertTrue(geojson["features"])
        feature = geojson["features"][0]
        self.assertEqual(feature["geometry"]["type"], "Polygon")
        self.assertIn("height", feature["properties"])
        self.assertIn("opportunity_score", feature["properties"])
        self.assertIn("affordable", feature["properties"])


if __name__ == "__main__":
    unittest.main()
