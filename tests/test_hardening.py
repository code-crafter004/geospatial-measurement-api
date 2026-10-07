from pathlib import Path

from app.config import settings

DATA = Path(__file__).parent / "data"


def upload_kml(client):
    return client.post(
        "/api/files/", files={"file": ("survey.kml", (DATA / "survey.kml").read_bytes())}
    )


def test_missing_file_field_uses_error_format(client):
    r = client.post("/api/files/")
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"][0]["field"].endswith("file")


def test_unknown_route_uses_error_format(client):
    r = client.get("/api/nope/")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "HTTP_404"


def test_oversize_upload_rejected_and_cleaned_up(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 0)
    r = upload_kml(client)
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "FILE_TOO_LARGE"
    upload_dir = Path(settings.upload_dir)
    assert not upload_dir.exists() or not list(upload_dir.iterdir())


def test_kml_properties_are_cleaned(client):
    file_id = upload_kml(client).json()["id"]
    feats = client.get(f"/api/files/{file_id}/measurements/").json()["features"]
    for f in feats:
        assert f["layer"] is None
        assert "tessellate" not in f["properties"]
        assert None not in f["properties"].values()
        assert f["properties"]["Name"]


def test_measurements_pagination_and_filter(client):
    file_id = upload_kml(client).json()["id"]

    page = client.get(f"/api/files/{file_id}/measurements/?limit=1&offset=1").json()
    assert page["feature_count"] == 3
    assert len(page["features"]) == 1
    assert page["features"][0]["index"] == 1

    only = client.get(f"/api/files/{file_id}/measurements/?geometry_type=Polygon").json()
    assert only["feature_count"] == 1
    assert only["features"][0]["geometry_type"] == "Polygon"


def test_list_files_paginates(client):
    for _ in range(3):
        upload_kml(client)
    assert len(client.get("/api/files/").json()) == 3
    assert len(client.get("/api/files/?limit=2").json()) == 2
    assert len(client.get("/api/files/?limit=2&offset=2").json()) == 1


def test_invalid_pagination_rejected(client):
    r = client.get("/api/files/?limit=0")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
