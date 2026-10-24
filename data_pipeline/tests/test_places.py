import json


def _feat(street, num, lat, lon):
    return {"geometry": {"coordinates": [lon, lat]},
            "properties": {"stn_label": street, "adr_number": num, "zip_label": "6430 Schwyz", "com_name": "Schwyz",
                           "bdg_egid": 1, "bdg_category": "residential"}}


def test_address_lookup_nearest_first_and_radius(tiny_data, monkeypatch):
    from data_pipeline import places

    def fake(lat, lon, layer, radius_m=0, extra=""):
        if layer == places.ORT_LAYER:
            return [{"properties": {"langtext": "Schwyz", "plz": 6430}}]
        if layer == places.GEM_LAYER:
            return [{"properties": {"gemname": "Schwyz", "gde_nr": 1372, "kanton": "SZ", "objektart_lookup": "kantonsgebiet"}},
                    {"properties": {"gemname": "Schwyz", "gde_nr": 1372, "kanton": "SZ", "objektart_lookup": "gemeindegebiet"}}]
        return [_feat("Grundstrasse", "30", 47.0186, 8.6572), _feat("Grundstrasse", "32", 47.018364, 8.657237),
                _feat("Weit weg", "1", 47.03, 8.66)]
    monkeypatch.setattr(places, "_identify", fake)
    r = places.address_lookup(47.018364, 8.657237, radius_m=100)
    assert (r["ortschaft"], r["municipality"], r["in_canton"]) == ("Schwyz", "Schwyz", True)
    assert [a["address"] for a in r["addresses"]] == ["Grundstrasse 32", "Grundstrasse 30"]


def test_named_buildings_by_point_name_and_kind(tiny_data, monkeypatch):
    from data_pipeline import places
    rows = [
        {"name": "Alterszentrum Acherhof", "kind": "Alters-/Pflegeheim", "lat": 47.0184, "lon": 8.6572, "alt_names": []},
        {"name": "Pfarrkirche St. Martin", "kind": "Kirche/Kapelle", "lat": 47.0207, "lon": 8.6541, "alt_names": []},
        {"name": "Hotel Waldstätterhof", "kind": "Hotel", "lat": 46.997, "lon": 8.605, "alt_names": ["Waldstaetterhof"]},
    ]
    f = places.GAZETTEER / "buildings.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rows))
    places._buildings.cache_clear()
    near = places.named_buildings(47.0184, 8.6572, radius_m=500)
    assert [b["name"] for b in near] == ["Alterszentrum Acherhof", "Pfarrkirche St. Martin"]
    assert near[0]["distance_m"] == 0
    assert [b["name"] for b in places.named_buildings(name="acherhof")] == ["Alterszentrum Acherhof"]
    assert [b["name"] for b in places.named_buildings(name="Waldstatterhof")] == ["Hotel Waldstätterhof"]
    assert [b["name"] for b in places.named_buildings(47.0184, 8.6572, 500, kinds=["Kirche/Kapelle"])] == ["Pfarrkirche St. Martin"]


def test_generic_gwr_names_rank_after_proper_names(tiny_data):
    from data_pipeline import places
    for n in ["Einfamilienhaus", "Garage B", "MFH; 883", "Gewerbegebäude Luzernerstrasse 22", "Oek.-Gebäude",
              "Wohn- und Geschäftshaus", "Mehrfamilienhaus mit Gewerbe", "Weidstall / Gebäude-Nr. 27", "1073"]:
        assert places.is_generic(n), n
    for n in ["Hotel Waldstätterhof", "Alte Metzg", "Klosterkirche 84", "Weidstall Ochsenweidli", "Pfarrhaus"]:
        assert not places.is_generic(n), n
    assert places.GBD_NR.sub("", "Gbd.-Nr. 995 Gartenhaus") == "Gartenhaus"
    rows = [
        {"name": "Einfamilienhaus", "kind": "Gebäude", "lat": 47.0184, "lon": 8.6572, "alt_names": [], "generic": True},
        {"name": "Hotel Schwert", "kind": "Hotel", "lat": 47.0190, "lon": 8.6572, "alt_names": [], "generic": False},
        {"name": "Kapelle Ried", "kind": "Kirche/Kapelle", "lat": 47.0200, "lon": 8.6572, "alt_names": []},
    ]
    f = places.GAZETTEER / "buildings.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rows))
    places._buildings.cache_clear()
    assert [b["name"] for b in places.named_buildings(47.0184, 8.6572, 500)] == [
        "Hotel Schwert", "Kapelle Ried", "Einfamilienhaus"]


def test_challenge_records_resolve_but_are_never_similar_hits(tiny_data):
    from data_pipeline import api
    rec = {"id": "challenge:SG.CIV.17.3", "source": "challenge", "split": "challenge", "date": {}, "places": []}
    (api.RECORDS / "challenge.jsonl").write_text(json.dumps(rec) + "\n")
    api.reload()
    assert api.get_record("challenge:SG.CIV.17.3")["split"] == "challenge"
    assert all(r["source"] == "staatsarchiv" for r in api.archive_lookup())


def test_sessions_group_by_camera_and_gap():
    from data_pipeline.scrapers import challenge

    def r(i, model, dt):
        return {"id": f"challenge:{i}", "raw": {"exif": {"model": model, "datetime": dt}}}
    recs = [r(1, "D1X", "2005:02:24 10:00:00"), r(2, "D1X", "2005:02:24 10:20:00"),
            r(3, "D1X", "2005:02:24 11:30:00"), r(4, "E8800", "2005:02:24 10:05:00"), r(5, "D1X", None)]
    challenge._sessions(recs)
    s = {x["id"]: x["raw"]["session"] for x in recs}
    assert s["challenge:1"] == ["challenge:2"] and s["challenge:3"] == [] and s["challenge:4"] == [] and s["challenge:5"] == []
