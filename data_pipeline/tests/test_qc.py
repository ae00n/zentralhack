import json


def _setup(data):
    from data_pipeline import paths
    (paths.GAZETTEER).mkdir(parents=True, exist_ok=True)
    (paths.GAZETTEER / "gemeinden.json").write_text(json.dumps([
        {"name": "Schwyz", "aliases": []}, {"name": "Ingenbohl", "aliases": []}, {"name": "Küssnacht (SZ)", "aliases": []}]))
    recs = [{"id": f"challenge:SG.CIV.17.{i}", "raw": {"priority": "1" if i < 10 else ""}} for i in (3, 5, 8, 12)]
    (paths.RECORDS / "challenge.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))


def test_import_csv_german_headers_and_official_names(tiny_data, tmp_path):
    from data_pipeline import qc
    from data_pipeline.jsonl import read_jsonl
    _setup(tiny_data)
    export = tmp_path / "hand.csv"
    export.write_text("Dateiname,Ortschaft,Gemeinde,Gebäude,Strasse,Notiz\n"
                      'SG.CIV.17.5.jpg,Brunnen,ingenbohl,"Seeklinik Brunnen; Hotel Eden",,\n'
                      "challenge:SG.CIV.17.3,,Schwyz,,Grundstrasse,nicht sicher\n"
                      "SG.CIV.17.8,Näfels,Glarus Nord,-,,\n"
                      "SG.CIV.17.12,Arth,Arth,,,\n", encoding="utf-8")
    n, problems = qc.import_export(export)
    rows = list(read_jsonl(qc.QC_FILE))
    assert n == 4 and [r["id"] for r in rows] == [f"challenge:SG.CIV.17.{i}" for i in (3, 5, 8, 12)]
    r3, r5, r8, _ = rows
    assert r5["municipality"] == "Ingenbohl" and r5["buildings"] == ["Seeklinik Brunnen", "Hotel Eden"]
    assert r3["locality"] is None and r3["buildings"] is None and r3["note"] == "nicht sicher"
    assert r8["buildings"] is None and r8["municipality"] == "Glarus Nord" and "municipality" in r8["unverified"]
    assert any("SG.CIV.17.12: not a Prio-1" in p for p in problems)


def test_score_challenge_hits_abstentions_and_bins(tiny_data):
    from data_pipeline.metrics import score_challenge

    def res(i, loc, mun, b, c):
        return {"photo_id": f"challenge:SG.CIV.17.{i}", "fields": {
            "locality": {"value": loc, "confidence": c}, "municipality": {"value": mun, "confidence": c},
            "buildings": {"value": b, "confidence": c}, "street": {"value": None, "confidence": 0}}}
    results = [res(1, "Seewen SZ", "Schwyz", ["Eidg. Zeughaus Seewen"], 0.9),
               res(2, "Brunnen", "Ingenbohl", [], 0.7),
               res(3, None, None, [], 0.0)]
    qc = [{"id": "challenge:SG.CIV.17.1", "locality": "Seewen", "municipality": "Schwyz", "buildings": ["Zeughaus Seewen"], "street": None},
          {"id": "challenge:SG.CIV.17.2", "locality": "Gersau", "municipality": "Gersau", "buildings": None, "street": None},
          {"id": "challenge:SG.CIV.17.3", "locality": "Arth", "municipality": "Arth", "buildings": None, "street": None}]
    s = score_challenge(results, qc)
    loc = s["fields"]["locality"]
    assert (loc["n"], loc["answered"], loc["hits"], loc["hit_rate"], loc["coverage"]) == (3, 2, 1, 0.5, 0.667)
    assert loc["by_confidence"]["0.85-1"] == {"n": 1, "hit_rate": 1.0}
    assert loc["by_confidence"]["0.6-0.85"] == {"n": 1, "hit_rate": 0.0}
    assert s["fields"]["buildings"]["hits"] == 1 and s["fields"]["street"]["n"] == 0
    from data_pipeline.metrics import _same
    assert _same("street", "Hauptplatz 3", "Hauptplatz") and not _same("street", "Bahnhofstrasse 3", "Hauptplatz")
    assert {(m["id"][-1], m["field"]) for m in s["misses"]} == {("2", "locality"), ("2", "municipality")}
