from data_pipeline.metrics import score

TRUTH = [
    {"id": "a", "subset": "card_exact", "municipality": "Schwyz", "year_from": 1910, "year_to": 1910},
    {"id": "b", "subset": "card_exact", "municipality": "Arth", "year_from": 1930, "year_to": 1930},
    {"id": "c", "subset": "card_posted", "municipality": "Lauerz", "year_from": 1925, "year_to": 1925,
     "year_is_upper_bound": True},
]
PRED = [
    {"id": "a", "municipality": "Schwyz", "municipality_confidence": 0.95, "year": 1912,
     "year_low": 1905, "year_high": 1915, "place_name_printed": True},
    {"id": "b", "municipality": "Schwyz", "municipality_confidence": 0.4, "year": 1950,
     "year_low": 1940, "year_high": 1960, "place_name_printed": False},
    {"id": "c", "municipality": "Lauerz", "municipality_confidence": 0.85, "year": 1910},
]


def test_score_splits_exact_and_upper_bound_years():
    s = score(PRED, TRUTH)
    assert s["n_scored"] == 3
    m = s["all"]["municipality"]
    assert m["accuracy"] == 0.667
    assert m["accuracy_printed"] == 1.0 and m["accuracy_not_printed"] == 0.0
    assert m["conf_0.8"] == {"coverage": 0.667, "accuracy": 1.0}
    y = s["all"]["year"]
    assert y["n"] == 2 and y["within_5"] == 0.5 and y["range_coverage"] == 0.5
    assert y["upper_bound_n"] == 1 and y["at_or_before_bound"] == 1.0
    assert set(s) >= {"card_exact", "card_posted"}
