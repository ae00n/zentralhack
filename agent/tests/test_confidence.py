"""The confidence method (CHALLENGE_BRIEF section 4) and what counts as a source or a counter-source."""

from agent import confidence as c

TOOLS = {"similar_images", "named_buildings", "address_lookup", "terrain_check"}


def ev(kind, ref=None, supports=True):
    return {"kind": kind, "summary": "x", "ref_id": ref, "supports": supports}


def field(*evidence, value="Schwyz"):
    return {"value": value, "evidence": list(evidence)}


def test_scale_and_agreement_bonus():
    core = [ev("address_register"), ev("named_building"), ev("visual_cue")]
    f = {"locality": field(*core), "municipality": field(*core),
         "buildings": field(ev("named_building"), value=["Alterszentrum Acherhof"]),
         "landscape_features": field(ev("visual_cue"), value=["Grosser Mythen"]),
         "street": field(ev("address_register"), value="Grundstrasse 32")}
    out = c.apply(f, TOOLS)
    assert f["municipality"]["confidence"] == 0.85 and out["overall"] == 0.9 and out["needs_review"] is False


def test_a_competing_candidate_does_not_cap():
    # "the Hafen Felsenegg in Gersau would also fit" is an alternative, not a counter-source
    f = field(ev("address_register"), ev("named_building"), ev("visual_cue"), ev("named_building", supports=False))
    assert c.score_field(f, TOOLS)[0] == 0.85


def test_real_counter_sources_cap():
    for against in (ev("address_register", supports=False), ev("text_on_card", supports=False),
                    ev("terrain", supports=False), ev("similar_image", "stasz:9", supports=False)):
        f = field(ev("address_register"), ev("named_building"), ev("visual_cue"), against)
        assert c.score_field(f, TOOLS, verified={"stasz:9"})[0] == 0.6, against["kind"]


def test_unverified_look_alikes_count_neither_way():
    f = field(ev("address_register"), ev("similar_image", "stasz:1"), ev("similar_image", "stasz:2", supports=False))
    assert c.score_field(f, TOOLS, verified=set())[0] == 0.5          # only the register counts, no cap
    assert c.score_field(f, TOOLS, verified={"stasz:1"})[0] == 0.7     # a verified hit is a second source
    assert c.score_field(f, TOOLS, verified={"stasz:1", "stasz:2"})[0] == 0.6  # verified elsewhere: capped


def test_a_verified_crop_counts_by_its_card():
    f = field(ev("address_register"), ev("similar_image", "stasz:5#2"))
    assert c.score_field(f, TOOLS, verified={"stasz:5"})[0] == 0.7


def test_explanation_names_a_real_counter_source_only():
    f = {"locality": field(ev("address_register"), ev("named_building", supports=False)),
         "municipality": field(ev("address_register"), ev("address_register", supports=False))}
    text = c.apply(f, TOOLS)["explanation"]
    assert "Gemeinde durch eine Quelle gestützt (Gebäudeadressverzeichnis) (mit Gegenquelle)" in text
    assert text.count("Gegenquelle") == 1
