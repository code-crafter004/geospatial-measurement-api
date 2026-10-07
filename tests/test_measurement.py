from pathlib import Path

import pytest
from pyproj import Geod

from app.services.crs import utm_epsg
from app.services.measurement import measure_geometry

DATA = Path(__file__).parent / "data"
GEOD = Geod(ellps="WGS84")

SQUARE = [[77.590, 12.970], [77.591, 12.970], [77.591, 12.971], [77.590, 12.971], [77.590, 12.970]]


def test_utm_zone_selection():
    assert utm_epsg(77.59, 12.97) == 32643  # Bengaluru, north
    assert utm_epsg(-0.1, 51.5) == 32630  # London
    assert utm_epsg(151.2, -33.8) == 32756  # Sydney, south
    assert utm_epsg(179.9, 0) == 32660  # last zone


def test_polygon_area_matches_geodesic():
    m = measure_geometry({"type": "Polygon", "coordinates": [SQUARE]}, "EPSG:4326")
    lons = [p[0] for p in SQUARE]
    lats = [p[1] for p in SQUARE]
    expected = abs(GEOD.polygon_area_perimeter(lons, lats)[0])
    assert m["supported"] and m["type"] == "area" and m["unit"] == "square_meters"
    # UTM grid area differs from true ground area by the scale factor (<0.5% inside a zone).
    assert m["value"] == pytest.approx(expected, rel=0.005)
    assert m["geodesic_value"] == pytest.approx(expected, rel=1e-4)
    assert 11_800 < m["value"] < 12_300  # not degrees squared


def test_axis_order_picks_correct_zone():
    # If lon/lat were swapped, this would land in a completely different zone.
    m = measure_geometry({"type": "Polygon", "coordinates": [SQUARE]}, "EPSG:4326")
    assert "EPSG:32643" in m["method"]


def test_linestring_length_matches_geodesic():
    coords = [[77.590, 12.970], [77.595, 12.975]]
    m = measure_geometry({"type": "LineString", "coordinates": coords}, "EPSG:4326")
    expected = GEOD.inv(77.590, 12.970, 77.595, 12.975)[2]
    assert m["type"] == "length" and m["unit"] == "meters"
    assert m["value"] == pytest.approx(expected, rel=0.005)


def test_point_has_no_measurement():
    assert measure_geometry({"type": "Point", "coordinates": [77.59, 12.97]}, "EPSG:4326") is None


def test_unsupported_geometry_is_graceful():
    geom = {"type": "GeometryCollection", "geometries": [{"type": "Point", "coordinates": [77.59, 12.97]}]}
    m = measure_geometry(geom, "EPSG:4326")
    assert m["supported"] is False
    assert "Unsupported" in m["reason"]


def test_missing_and_empty_geometry():
    assert measure_geometry(None, "EPSG:4326")["supported"] is False
    assert measure_geometry({"type": "Polygon", "coordinates": []}, "EPSG:4326")["supported"] is False


def test_multipolygon_sums_parts():
    shifted = [[x + 0.01, y] for x, y in SQUARE]
    one = measure_geometry({"type": "Polygon", "coordinates": [SQUARE]}, "EPSG:4326")["value"]
    multi = measure_geometry(
        {"type": "MultiPolygon", "coordinates": [[SQUARE], [shifted]]}, "EPSG:4326"
    )["value"]
    assert multi == pytest.approx(2 * one, rel=0.001)


def test_projected_crs_measured_directly():
    sq = [[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]
    m = measure_geometry({"type": "Polygon", "coordinates": [sq]}, "EPSG:32643")
    assert m["value"] == pytest.approx(10_000)
    assert "geodesic_value" not in m


def test_projected_crs_in_feet_converted_to_metres():
    sq = [[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]
    m = measure_geometry({"type": "Polygon", "coordinates": [sq]}, "EPSG:2272")
    assert m["value"] == pytest.approx(929.03, rel=1e-4)


def test_invalid_polygon_repaired_with_warning():
    bowtie = [[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]
    m = measure_geometry({"type": "Polygon", "coordinates": [bowtie]}, "EPSG:4326")
    assert m["supported"] is True and m["value"] > 0
    assert "repaired" in m["warning"]


def test_unknown_crs_label_is_graceful():
    m = measure_geometry({"type": "Point", "coordinates": [1, 1]}, "custom:weird")
    assert m is None  # points need no CRS
    m = measure_geometry({"type": "LineString", "coordinates": [[0, 0], [1, 1]]}, "custom:weird")
    assert m["supported"] is False


def test_api_returns_measurements(client):
    r = client.post("/api/files/", files={"file": ("survey.kml", (DATA / "survey.kml").read_bytes())})
    file_id = r.json()["id"]
    feats = client.get(f"/api/files/{file_id}/measurements/").json()["features"]
    by_type = {f["geometry_type"]: f for f in feats}
    assert 11_800 < by_type["Polygon"]["measurement"]["value"] < 12_300
    assert by_type["LineString"]["measurement"]["type"] == "length"
    assert by_type["Point"]["measurement"] is None
