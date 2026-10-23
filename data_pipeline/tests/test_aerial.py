from PIL import Image


def test_aerial_image_stitches_centred_square(tmp_path, monkeypatch):
    from data_pipeline import aerial
    calls = []

    def fake_tile(layer, time, z, x, y):
        calls.append((layer, time, z))
        return Image.new("RGB", (256, 256), (0, 128, 0))

    monkeypatch.setattr(aerial, "_tile", fake_tile)
    monkeypatch.setattr(aerial, "OUT", tmp_path)
    out = aerial.aerial_image(47.0185, 8.6568, radius_m=80, year=2005)
    assert {c[:2] for c in calls} == {(aerial.SERIES, "2005")} and calls[0][2] == 19
    assert abs(out["width"] - 160 / out["meters_per_pixel"]) <= 2 and out["width"] == out["height"]
    img = Image.open(tmp_path / out["path"].split("/")[-1])
    r, g, _ = img.getpixel((out["width"] // 2, out["height"] // 2))
    assert r > 150 and g < 100  # red cross on the point (JPEG softens it)
    aerial.aerial_image(47.0185, 8.6568, radius_m=80)
    assert calls[-1][:2] == (aerial.CURRENT, "current")
