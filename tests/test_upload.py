import io
import zipfile
from pathlib import Path

DATA = Path(__file__).parent / "data"


def fake_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("plots.shp", b"x")
    return buf.getvalue()


def test_upload_kml(client):
    r = client.post(
        "/api/files/", files={"file": ("survey.kml", (DATA / "survey.kml").read_bytes())}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 3
    assert body["crs"] == "EPSG:4326"

    g = client.get(f"/api/files/{body['id']}/")
    assert g.status_code == 200
    assert g.json()["id"] == body["id"]


def test_upload_unreadable_zip_marks_failed(client):
    r = client.post("/api/files/", files={"file": ("plots.zip", fake_zip())})
    assert r.status_code == 201
    assert r.json()["status"] == "FAILED"
    assert r.json()["error"]


def test_reject_wrong_extension(client):
    r = client.post("/api/files/", files={"file": ("notes.txt", b"hello")})
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_reject_empty_file(client):
    r = client.post("/api/files/", files={"file": ("empty.kml", b"")})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "EMPTY_FILE"


def test_reject_corrupt_zip(client):
    r = client.post("/api/files/", files={"file": ("bad.zip", b"not a zip")})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_ZIP"


def test_unknown_id(client):
    r = client.get("/api/files/does-not-exist/")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "FILE_NOT_FOUND"
