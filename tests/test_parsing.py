import io
import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

DATA = Path(__file__).parent / "data"


def make_shapefile_zip(tmp_path: Path, with_prj: bool = True) -> bytes:
    gdf = gpd.GeoDataFrame(
        {"name": ["Plot A"]},
        geometry=[Polygon([(77.590, 12.970), (77.591, 12.970), (77.591, 12.971), (77.590, 12.971)])],
        crs="EPSG:4326",
    )
    folder = tmp_path / "shp"
    folder.mkdir()
    gdf.to_file(folder / "plots.shp", engine="pyogrio")
    if not with_prj:
        (folder / "plots.prj").unlink()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in folder.iterdir():
            z.write(f, f.name)
    return buf.getvalue()


def upload(client, name, content):
    return client.post("/api/files/", files={"file": (name, content)})


def test_kml_features(client):
    r = upload(client, "survey.kml", (DATA / "survey.kml").read_bytes())
    file_id = r.json()["id"]
    m = client.get(f"/api/files/{file_id}/measurements/")
    assert m.status_code == 200
    feats = m.json()["features"]
    assert {f["geometry_type"] for f in feats} == {"Polygon", "LineString", "Point"}
    assert {f["properties"].get("Name") for f in feats} == {"Plot A", "Road 1", "Gate"}
    assert [f["index"] for f in feats] == [0, 1, 2]


def test_shapefile_zip(client, tmp_path):
    r = upload(client, "plots.zip", make_shapefile_zip(tmp_path))
    body = r.json()
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 1
    assert body["crs"] == "EPSG:4326"


def test_shapefile_missing_prj_fails(client, tmp_path):
    r = upload(client, "plots.zip", make_shapefile_zip(tmp_path, with_prj=False))
    body = r.json()
    assert body["status"] == "FAILED"
    assert "CRS" in body["error"]


def test_zip_without_shp_fails(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "hi")
    body = upload(client, "nothing.zip", buf.getvalue()).json()
    assert body["status"] == "FAILED"
    assert ".shp" in body["error"]


def test_zip_slip_rejected(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../evil.txt", "x")
    body = upload(client, "evil.zip", buf.getvalue()).json()
    assert body["status"] == "FAILED"
    assert "unsafe" in body["error"]


def test_measurements_409_when_failed(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "hi")
    file_id = upload(client, "nothing.zip", buf.getvalue()).json()["id"]
    r = client.get(f"/api/files/{file_id}/measurements/")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "FILE_NOT_READY"
