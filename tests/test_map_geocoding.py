from odoo_streamlit.map_geocoding import _point, search_location


def test_postcode_search_resolves_centre(monkeypatch):
    called = []
    def fake_fetch(url):
        called.append(url)
        return [
            {"nom": "Rennes", "centre": {"coordinates": [-1.6778, 48.1173]}}
        ]
    monkeypatch.setattr("odoo_streamlit.map_geocoding._fetch_json", fake_fetch)
    matches = search_location("35000")
    assert "codePostal=35000" in called[0]
    assert matches == [{"label": "35000 · Rennes", "lat": 48.1173, "lon": -1.6778, "zoom": 11}]


def test_city_and_address_search(monkeypatch):
    monkeypatch.setattr(
        "odoo_streamlit.map_geocoding._fetch_json",
        lambda url: {"features": [
            {"geometry": {"coordinates": [-2.76, 47.66]},
             "properties": {"label": "Vannes", "type": "municipality"}}
        ]},
    )
    assert search_location("Vannes")[0]["zoom"] == 11


def test_invalid_coordinates_are_ignored():
    assert _point({"coordinates": [220, 48]}) is None
    assert _point({"coordinates": ["xx", 48]}) is None
