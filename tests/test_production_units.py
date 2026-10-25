"""Exercise scope selection against overlap, coverage and time/basis traps."""
import json
from pathlib import Path
import unittest

import duckdb
import production_units as p


def asset(name, value="10", parent=None, period="2024年平均", **extra):
    return {"country": "测试国", "name": name, "name_cn": name,
            "asset_level_label": "单一油气田", "asset_level": "field",
            "value": value, "unit": "千桶/日", "metric_type": "actual_output",
            "commodity": "crude_oil", "data_date": period,
            "source_url": "https://example.org/source", "ownership_basis": "全资产毛口径",
            "parent_asset": parent, "constituent_assets": [], **extra}


class ProductionUnitsTest(unittest.TestCase):
    def select(self, assets, **kwargs):
        return p.select_units(p.build_observations(assets), **kwargs)

    def test_complete_same_period_splits_parent(self):
        assets = [asset("Sarsang", "30", constituent_assets=["a", "b"]),
                  asset("a", "10", "Sarsang"), asset("b", "20", "Sarsang")]
        chosen, rows = self.select(assets, period="2024")
        self.assertEqual({o["name"] for o in chosen}, {"a", "b"})
        self.assertEqual(p.total_units(chosen, "2024")[0], 3)
        self.assertIn("已拆", rows[0]["status"])

    def test_missing_or_different_period_child_keeps_parent(self):
        for child in [asset("b", None, "Sarsang"), asset("b", "20", "Sarsang", "2023年平均")]:
            chosen, _ = self.select([asset("Sarsang", "30", constituent_assets=["a", "b"]),
                                     asset("a", "10", "Sarsang"), child])
            self.assertEqual([o["name"] for o in chosen], ["Sarsang"])

    def test_unknown_completeness_never_splits(self):
        chosen, _ = self.select([asset("group", "30", constituent_assets=["a", "b"]),
                                asset("a", "10", "group"), asset("b", "20", "group")])
        self.assertEqual([o["name"] for o in chosen], ["group"])

    def test_capacity_parent_does_not_hide_actual_child(self):
        chosen, _ = self.select([asset("group", "30", metric_type="target_capacity"),
                                asset("a", "10", "group")])
        self.assertEqual([o["name"] for o in chosen], ["a"])

    def test_equity_never_blocks_or_joins_gross(self):
        chosen, rows = self.select([asset("Sarsang", "30", constituent_assets=["a"]),
                                   asset("a", "10", "Sarsang", ownership_basis="Forza Petroleum 65%工作权益口径")])
        self.assertEqual([o["name"] for o in chosen], ["Sarsang"])
        self.assertIn("仅作明细", rows[1]["status"])

    def test_zero_is_real_value_and_missing_is_not_zero(self):
        chosen, _ = self.select([asset("zero", 0), asset("missing", None)], period="2024")
        total, summed = p.total_units(chosen, "2024")
        self.assertEqual(total, 0)
        self.assertEqual(len(summed), 1)

    def test_peak_sales_capacity_excluded(self):
        for metric in ["historical_peak", "sales_volume", "production_acceptance_test", "capacity", "target_capacity"]:
            chosen, _ = self.select([asset("a", metric_type=metric)])
            self.assertFalse(chosen)

    def test_bounds_ranges_not_summed(self):
        for value in [">70", "70–80", "约10", "<20"]:
            chosen, _ = self.select([asset("a", value)], period="2024")
            self.assertEqual(len(chosen), 1)
            self.assertIsNone(p.total_units(chosen, "2024")[0])

    def test_different_dates_no_latest_total(self):
        chosen, _ = self.select([asset("a"), asset("b", period="2023年平均")])
        self.assertIsNone(p.total_units(chosen, None)[0])
        chosen, _ = self.select([asset("a"), asset("b", period="2023年平均")], period="2024")
        self.assertEqual([o["name"] for o in chosen], ["a"])

    def test_publication_date_not_observation_period(self):
        for text in ["2010年估计；IEEJ 2012-09报告", "观测期未注明；2024-04-15报道",
                     "2025年权益日量（公告未定义是否全年均值）", "2026年1月高需求时段产量水平（非月均）"]:
            self.assertIsNone(p.observation_period(text)[0])
        self.assertEqual(p.observation_period("2026年第二季度平均")[0], "2026-Q2")
        self.assertEqual(p.observation_period("2026上半年估算日均；181日")[0], "2026-H1")

    def test_product_and_estimate_filters(self):
        assets = [asset("oil"), asset("gas", unit="百万立方米/日", commodity="natural_gas"),
                  asset("estimate", metric_type="estimated_output")]
        chosen, _ = self.select(assets, estimates=False)
        self.assertEqual([o["name"] for o in chosen], ["oil"])
        chosen, _ = self.select(assets, product="natural_gas")
        self.assertEqual([o["name"] for o in chosen], ["gas"])

    def test_boe_is_separate_and_scaled_to_ten_thousand(self):
        chosen, _ = self.select([asset("boe", "10", unit="千桶油当量/日")], product="boe", period="2024")
        self.assertEqual(p.total_units(chosen, "2024")[0], 1)

    def test_partial_geographic_scope_not_treated_as_entire_asset(self):
        chosen, _ = self.select([asset("a", ownership_basis="仅伊朗侧项目毛口径；不含阿曼侧")], period="2024")
        self.assertEqual(chosen[0]["basis"], "具名部分范围")
        self.assertIsNone(p.total_units(chosen, "2024")[0])

    def test_gas_units_not_silently_combined(self):
        chosen, _ = self.select([asset("a", unit="百万立方米/日"),
                                asset("b", unit="百万标准立方英尺/日")],
                               product="natural_gas", period="2024")
        self.assertIsNone(p.total_units(chosen, "2024")[0])

    def test_typed_bound_not_treated_as_exact_value(self):
        chosen, _ = self.select([asset("a", value_qualifier=">")], period="2024")
        self.assertIsNone(p.total_units(chosen, "2024")[0])

    def test_raw_json_numeric_strings_render(self):
        chosen, _ = self.select([asset("a", value_numeric="10", value_qualifier="")])
        self.assertEqual(p.unit_rows(chosen)[0]["产量"], "1 万桶/日")

    def test_gas_missing_not_claimed_covered_by_oil(self):
        chosen, rows = self.select([asset("oil"), asset("gas", None, "oil", commodity="natural_gas")])
        self.assertEqual(rows[1]["status"], "缺产量")

    def test_shared_country_identity_is_one_unit(self):
        observations = p.build_observations([asset("shared", countries=["测试国", "邻国"])])
        filtered = [o for o in observations if {"测试国", "邻国"} & set(o["countries"])]
        chosen, _ = p.select_units(filtered)
        self.assertEqual(len(chosen), 1)
        self.assertEqual(p.unit_rows(chosen)[0]["共享国家"], "测试国、邻国")

    def test_actual_preferred_to_estimate_then_newest_actual(self):
        base = asset("a", "10", period="2023年平均", additional_measurements=[
            asset("a", "20", period="2024年平均", metric_type="estimated_output"),
            asset("a", "9", period="2022年平均")])
        chosen, _ = self.select([base], prefer_actual=True)
        self.assertEqual(chosen[0]["measurement"]["value"], "10")
        self.assertEqual(p.compact_rows(chosen)[0]["备注"], "真实产量")

    def test_same_period_estimate_does_not_disqualify_actual(self):
        chosen, _ = self.select([asset("a", "10", additional_measurements=[
            asset("a", "20", metric_type="estimated_output")])], prefer_actual=True)
        self.assertEqual(chosen[0]["measurement"]["value"], "10")

    def test_estimated_children_do_not_replace_actual_parent(self):
        chosen, _ = self.select([asset("Sarsang", "30", constituent_assets=["a", "b"]),
                                asset("a", "10", "Sarsang", metric_type="estimated_output"),
                                asset("b", "20", "Sarsang", metric_type="estimated_output")], prefer_actual=True)
        self.assertEqual([o["name"] for o in chosen], ["Sarsang"])

    def test_compact_time_uses_observation_not_publication_year(self):
        self.assertEqual(p.measurement_year({'data_date': '2010年估计；IEEJ 2012-09报告'}), '2010')
        self.assertIsNone(p.measurement_year({'data_date': '观测期未注明；2024-04-15报道'}))
        self.assertIsNone(p.measurement_year({'data_date': '2014-02 JICA最终报告；底层观察期未明'}))

    def test_compact_daily_units_ranges_and_zero(self):
        self.assertEqual(p.daily_display(asset('a', '70–80')), '7–8万桶/天')
        self.assertEqual(p.daily_display(asset('a', '>70')), '>7万桶/天')
        self.assertEqual(p.daily_display(asset('a', 0)), '0万桶/天')
        self.assertEqual(p.daily_display(asset('a', '10000', unit='桶/日')), '1万桶/天')
        self.assertEqual(p.daily_display(asset('a', '10', unit='千桶油当量/日')), '1万桶油当量/天')

    def test_annual_conversion_is_labeled_estimate_in_compact_view(self):
        chosen, _ = self.select([asset('a', metric_type='derived_daily_average')], prefer_actual=True)
        self.assertEqual(p.compact_rows(chosen)[0]['备注'], '估算产量')

    def test_duplicate_reference_is_one_scope(self):
        ref = {"id": "syria-ward-ahmer-akash-ratka-2015", "scope": "four fields",
               "members": ["Al-Ward", "Ahmer", "Akash", "Ratka"],
               **{k: v for k, v in asset("unused").items() if k in
                  ["value", "unit", "metric_type", "data_date", "source_url", "ownership_basis"]}}
        assets = [asset(n, None, aggregate_references=[ref]) for n in ref["members"]]
        chosen, _ = self.select(assets)
        self.assertEqual(len(chosen), 1)

    def test_partial_overlap_excludes_both(self):
        observations = p.build_observations([asset("a"), asset("b")])
        observations[0]["coverage"] = frozenset({("x", "1"), ("x", "2")})
        observations[1]["coverage"] = frozenset({("x", "2"), ("x", "3")})
        chosen, rows = p.select_units(observations)
        self.assertFalse(chosen)
        self.assertTrue(all("待核" in o["status"] for o in rows))

    def test_conflicting_same_period_kept_out(self):
        chosen, rows = self.select([asset("a", additional_measurements=[
            {**asset("a"), "value": "20"}])])
        self.assertFalse(chosen)
        self.assertTrue(all("来源冲突" in o["status"] for o in rows))


class PublishedCatalogAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "runtime/monitoring.duckdb"
        with duckdb.connect(str(path), read_only=True) as conn:
            cls.assets = [json.loads(row[0]) for row in conn.execute("SELECT payload FROM catalogs WHERE kind='assets'").fetchall()]
        cls.observations = p.build_observations(cls.assets)

    def test_every_filter_combination_has_disjoint_selected_scopes(self):
        periods = {o["period"] for o in self.observations}
        for product in p.PRODUCTS:
            for period in periods:
                for estimates in (True, False):
                    with self.subTest(product=product, period=period, estimates=estimates):
                        chosen, rows = p.select_units(self.observations, period=period, product=product, estimates=estimates)
                        self.assertFalse([o for o in rows if o["status"] == "待选择"])
                        for i, a in enumerate(chosen):
                            self.assertEqual(a["product"], product)
                            self.assertIn(a["measurement"]["metric_type"], p.PRODUCTION)
                            for b in chosen[i + 1:]:
                                self.assertFalse(a["coverage"] & b["coverage"], (a["name"], b["name"]))
                        total, summed = p.total_units(chosen, period)
                        self.assertTrue(all(o["basis"] == "全资产" for o in summed))
                        self.assertTrue(all(o["period"] == period for o in summed))

    def test_kirkuk_reference_is_not_counted_with_domes(self):
        chosen, rows = p.select_units(self.observations, period="2021")
        names = {o["name"] for o in chosen}
        self.assertIn("Baba Dome", names)
        self.assertIn("Avana Dome", names)
        ref = next(o for o in rows if o["scope_id"].endswith("kirkuk-two-domes-2021"))
        self.assertIn("已拆", ref["status"])
        self.assertNotIn(ref, chosen)

    def test_no_catalog_or_reference_omissions(self):
        ids = {o["scope_id"] for o in self.observations}
        for a in self.assets:
            self.assertIn(f'{a["country"]}/{a["name"]}', ids)
            for ref in a.get("aggregate_references", []):
                self.assertTrue(ref["id"] in ids or f'reference:{a["country"]}/{ref["id"]}' in ids)

    def test_2020_domes_survive_2024_parent(self):
        chosen, _ = p.select_units(self.observations, period="2020")
        self.assertEqual({o["name"] for o in chosen},
                         {"Idd El Shargi North Dome (ISND)", "Idd El Shargi South Dome (ISSD)"})
        self.assertEqual(str(p.total_units(chosen, "2020")[0]), "6.3504")
