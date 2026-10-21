import re

from data_pipeline.dating import card_number, family, rule_checklist, rules


def test_card_number_keeps_series_apart():
    assert card_number("k 4139") == ("k", 4139)
    assert card_number("1430 Fl.") == ("fl", 1430)
    assert card_number("11547") == ("", 11547)
    assert card_number("Serie II") is None


def test_publisher_family_collapses_spellings():
    assert family("Wehrli - Photoglob, AG., Zürich") == "photoglob-wehrli"
    assert family("Wehrli & Vouga - Photoglob AG., Zürich") == "photoglob-wehrli"
    assert family("Wehrli, Gebr. - Kilchberg, Zürich") == "wehrli"
    assert family("unbekannt") is None


def test_rules_have_sources_and_publisher_regexes_compile():
    for r in rules():
        assert r["source"].startswith("http")
        if r["applies"] == "publisher":
            re.compile(r["match"])
    assert all(r["category"] != "publisher" for r in rule_checklist())
