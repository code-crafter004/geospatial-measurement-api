import io
import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from app.services.measurement import measure_geometry

MULTI_FOLDER_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>Plots</name>
      <Placemark><name>Plot A</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
        77.590,12.970,0 77.591,12.970,0 77.591,12.971,0 77.590,12.971,0 77.590,12.970,0
      </coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
    </Folder>
    <Folder>
      <name>Roads</name>
      <Placemark><name>Road 1</name><LineString><coordinates>
        77.590,12.970,0 77.595,12.975,0
      </coordinates></LineString></Placemark>
    </Folder>
  </Document>
</kml>
"""

EMPTY_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document></Document></kml>
"""


def upload(client, name, content):
    return client.post("/api/files/", files={"file": (name, content)})


def test_multi_folder_kml_reads_all_layers(client):
    body = upload(client, "multi.kml", MULTI_FOLDER_KML.encode()).json()
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 2

    feats = client.get(f"/api/files/{body['id']}/measurements/").json()["features"]
    assert {f["layer"] for f in feats} == {"Plots", "Roads"}
    assert [f["index"] for f in feats] == [0, 1]


def test_empty_kml_fails_gracefully(client):
    body = upload(client, "empty.kml", EMPTY_KML.encode()).json()
    assert body["status"] == "FAILED"
    assert body["error"]


def test_garbage_kml_fails_gracefully(client):
    body = upload(client, "junk.kml", b"this is not xml at all").json()
    assert body["status"] == "FAILED"
    assert body["error"]


def test_3d_coordinates_ignored_for_measurement():
    flat = [[77.590, 12.970], [77.591, 12.970], [77.591, 12.971], [77.590, 12.971], [77.590, 12.970]]
    tall = [[x, y, 900.0] for x, y in flat]
    a = measure_geometry({"type": "Polygon", "coordinates": [flat]}, "EPSG:4326")
    b = measure_geometry({"type": "Polygon", "coordinates": [tall]}, "EPSG:4326")
    assert a["value"] == pytest.approx(b["value"])


def test_projected_shapefile_in_feet_end_to_end(client, tmp_path: Path):
    # 100 ft x 100 ft square in a US State Plane CRS that uses feet.
    gdf = gpd.GeoDataFrame(
        {"name": ["Lot"]},
        geometry=[Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])],
        crs="EPSG:2272",
    )
    folder = tmp_path / "ft"
    folder.mkdir()
    gdf.to_file(folder / "lot.shp", engine="pyogrio")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in folder.iterdir():
            z.write(f, f.name)

    body = upload(client, "lot.zip", buf.getvalue()).json()
    assert body["status"] == "COMPLETED", body["error"]

    feats = client.get(f"/api/files/{body['id']}/measurements/").json()["features"]
    m = feats[0]["measurement"]
    assert m["supported"] is True, m
    assert m["value"] == pytest.approx(929.03, rel=1e-3)
    assert "geodesic_value" not in m
