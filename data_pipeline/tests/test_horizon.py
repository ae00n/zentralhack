import math


def test_horizon_sees_a_synthetic_mountain(tmp_path, monkeypatch):
    import importlib
    from data_pipeline import places
    hz = importlib.import_module("data_pipeline.horizon")  # the package exports the function under the same name
    peak = (47.0, 8.6 + 3000 / (111320 * math.cos(math.radians(47.0))))  # 3 km due east

    def fake_height(lat, lon, z=12):
        dx = (lon - peak[1]) * 111320 * math.cos(math.radians(47.0))
        dy = (lat - peak[0]) * 111320
        return 400 + 1000 * math.exp(-(dx * dx + dy * dy) / (2 * 300 ** 2))

    monkeypatch.setattr(hz, "height", fake_height)
    monkeypatch.setattr(hz, "OUT", tmp_path)
    monkeypatch.setattr(places, "_buildings", lambda: [{"name": "Testberg", "kind": "Berg", "lat": peak[0],
                                                        "lon": peak[1], "tags": {"ele": "1400"}}])
    out = hz.horizon(47.0, 8.6, heading_deg=90, fov_deg=40)
    top = max(out["elevation_deg"])
    assert abs(top - math.degrees(math.atan2(1000 - 1.7, 3000))) < 1.5  # about 18 degrees
    assert out["peaks"][0]["name"] == "Testberg" and out["peaks"][0]["visible"]
    assert abs(out["peaks"][0]["offset_deg"]) < 0.5
    assert (tmp_path / out["path"].split("/")[-1]).exists()
