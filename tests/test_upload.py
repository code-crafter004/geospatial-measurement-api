import io
import zipfile


def make_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("plots.shp", b"x")
    return buf.getvalue()


def test_upload_kml(client):
    r = client.post("/api/files/", files={"file": ("survey.kml", b"<kml></kml>")})
    assert r.status_code == 201
    body = r.json()
    assert body["filename"] == "survey.kml"
    assert body["status"] == "PENDING"

    g = client.get(f"/api/files/{body['id']}/")
    assert g.status_code == 200
    assert g.json()["id"] == body["id"]


def test_upload_zip(client):
    r = client.post("/api/files/", files={"file": ("plots.zip", make_zip())})
    assert r.status_code == 201


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
