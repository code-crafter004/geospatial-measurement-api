# Geospatial File Measurement API

A backend service built with FastAPI that accepts a geospatial file (a zipped Shapefile or a KML), extracts every feature, and returns measurements: area for polygons and length for lines. All measurements are calculated in a projected coordinate system, never in raw latitude and longitude degrees.

Version: 1.0.0

## Contents

1. [Quick start](#quick-start)
2. [Configuration](#configuration)
3. [API](#api)
4. [Architecture](#architecture)
5. [Design decisions](#design-decisions)
6. [Testing](#testing)
7. [Limitations and assumptions](#limitations-and-assumptions)
8. [Learnings](#learnings)
9. [Future scope](#future-scope)

## Quick start

### Option A: Docker (easiest)

```bash
git clone https://github.com/<your-username>/geospatial-measurement-api.git
cd geospatial-measurement-api
docker compose up --build
```

The API is now at http://localhost:8000 and the interactive docs are at http://localhost:8000/docs. The database and uploaded files live in a Docker volume, so they survive restarts. Run `docker compose down -v` to delete them.

### Option B: Local

Python 3.10 or newer is needed (developed on 3.10, Docker image uses 3.11).

```bash
git clone https://github.com/<your-username>/geospatial-measurement-api.git
cd geospatial-measurement-api
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

If `pip install` tries to build `pyproj` from source and fails, use `pip install --only-binary=:all: pyproj shapely pyogrio geopandas` first, or use Docker.

### Try it

Sample files are in `samples/`.

```bash
curl -X POST http://localhost:8000/api/files/ -F "file=@samples/survey.kml"
curl http://localhost:8000/api/files/<id>/
curl http://localhost:8000/api/files/<id>/measurements/
```

To regenerate the sample shapefile zip: `python scripts/make_sample_zip.py`.

## Configuration

All settings are environment variables (see `.env.example`).

| Variable | Default | Meaning |
|---|---|---|
| `MAX_UPLOAD_MB` | `25` | Maximum upload size |
| `DATABASE_URL` | `sqlite:///./geo.db` | SQLAlchemy database URL |
| `UPLOAD_DIR` | `uploads` | Where uploaded files are stored |
| `LOG_LEVEL` | `INFO` | Python logging level |

## API

Interactive documentation: `GET /docs` (Swagger) and `GET /openapi.json`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/files/` | Upload and process a file |
| GET | `/api/files/` | List uploaded files (`limit`, `offset`) |
| GET | `/api/files/{id}/` | File information and status |
| GET | `/api/files/{id}/measurements/` | Features with measurements |
| GET | `/health` | Service status and version |

### Upload: `POST /api/files/`

Multipart form with a field named `file`. Accepts `.kml` or `.zip` (containing a Shapefile).

```bash
curl -X POST http://localhost:8000/api/files/ -F "file=@samples/survey.kml"
```

Response `201`:

```json
{
  "id": "1d2642e3-f8c6-43de-9a88-eb5cd57ce8cd",
  "filename": "survey.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "error": null,
  "created_at": "2026-10-07T09:22:00.923209"
}
```

If the upload itself is valid but the content cannot be read (for example a zip with no `.shp`, or a Shapefile with no `.prj`), the API still returns `201`, with `"status": "FAILED"` and a readable `error`. If the request itself is bad (wrong extension, empty file, too large, not a real zip), the API returns a `4xx` error and stores nothing.

### File information: `GET /api/files/{id}/`

Returns the same shape as the upload response. Status values are `PENDING`, `PROCESSING`, `COMPLETED` and `FAILED`.

### Measurements: `GET /api/files/{id}/measurements/`

Query parameters:

| Parameter | Default | Meaning |
|---|---|---|
| `limit` | `100` | Page size (1 to 1000) |
| `offset` | `0` | Features to skip |
| `geometry_type` | none | Only return one type, for example `Polygon` |

```bash
curl "http://localhost:8000/api/files/<id>/measurements/?geometry_type=Polygon"
```

Response (shortened):

```json
{
  "id": "1d2642e3-f8c6-43de-9a88-eb5cd57ce8cd",
  "crs": "EPSG:4326",
  "feature_count": 1,
  "limit": 100,
  "offset": 0,
  "features": [
    {
      "index": 0,
      "layer": null,
      "geometry_type": "Polygon",
      "geometry": { "type": "Polygon", "coordinates": [[[77.59, 12.97, 0.0], "..."]] },
      "crs": "EPSG:4326",
      "properties": { "Name": "Plot A" },
      "measurement": {
        "supported": true,
        "type": "area",
        "value": 12016.97,
        "unit": "square_meters",
        "method": "WGS 84 / UTM zone 43N (EPSG:32643)",
        "geodesic_value": 12003.11
      }
    }
  ]
}
```

What each geometry type returns in `measurement`:

| Geometry | Result |
|---|---|
| Polygon, MultiPolygon | `type: "area"`, square meters (parts are summed) |
| LineString, MultiLineString | `type: "length"`, meters (parts are summed) |
| Point, MultiPoint | `null` (no measurement needed) |
| Anything else, or broken geometry | `{"supported": false, "reason": "..."}` |

`geodesic_value` is an independent cross check calculated on the WGS84 ellipsoid. It is only present when the source data is in geographic coordinates. A `warning` field appears when an invalid polygon had to be repaired before measuring.

If the file is not `COMPLETED`, this endpoint returns `409`.

### Errors

Every error uses one format:

```json
{ "error": { "code": "FILE_NOT_FOUND", "message": "No file with id abc" } }
```

| HTTP | Code | When |
|---|---|---|
| 400 | `EMPTY_FILE` | Uploaded file has no content |
| 400 | `INVALID_ZIP` | Not a valid zip archive |
| 404 | `FILE_NOT_FOUND` | Unknown file id (or unknown route, as `HTTP_404`) |
| 409 | `FILE_NOT_READY` | Measurements requested for a file that is not `COMPLETED` |
| 413 | `FILE_TOO_LARGE` | Over `MAX_UPLOAD_MB` |
| 415 | `UNSUPPORTED_FILE_TYPE` | Not `.kml` or `.zip` |
| 422 | `VALIDATION_ERROR` | Bad query parameters or missing `file` field, with a `details` list |
| 500 | `INTERNAL_ERROR` | Unexpected failure (full traceback goes to the logs, not the response) |

## Architecture

### Application structure

```
app/
  main.py               app factory, logging, router and error handlers
  config.py             settings from environment variables
  api/routes_files.py   HTTP endpoints only, kept thin
  core/errors.py        AppError and the consistent error responses
  db/                   SQLAlchemy engine, session and models (File, Feature)
  schemas/files.py      Pydantic response models
  services/
    ingestion.py        upload validation and saving to disk
    parsing.py          safe zip extraction, KML and Shapefile reading
    processing.py       orchestrates parse, measure and store
    crs.py              UTM zone and projected CRS selection, unit handling
    measurement.py      area and length calculation per geometry
tests/                  pytest suite (38 tests)
scripts/                helper to generate the sample shapefile zip
samples/                example KML and zipped Shapefile
```

Routes know about HTTP, services know about geospatial data, and the two do not mix.

### File processing flow

1. **Validate** (`ingestion.py`): check the extension, stream the upload to disk while enforcing the size limit, reject empty files, and check that a `.zip` is really a zip. A rejected upload is deleted from disk.
2. **Record**: create a `files` row with status `PENDING`, then set it to `PROCESSING`.
3. **Parse** (`parsing.py`):
   - KML: read every layer (each KML folder becomes a layer) with GDAL through pyogrio. CRS is always `EPSG:4326`.
   - Shapefile zip: extract safely into a temp directory, find every `.shp`, read each one, and take the CRS from the `.prj`.
4. **Measure** (`measurement.py`): compute a measurement per feature (below).
5. **Store**: save every feature (geometry as GeoJSON, properties, measurement) in the `features` table, then set the file to `COMPLETED` with its CRS and feature count. Any failure sets `FAILED` with a readable message and nothing is half saved.

### Measurement calculation flow

For each feature:

1. Read the geometry type. Points need no measurement. Unsupported types return `supported: false`.
2. Drop Z values (only X and Y matter for ground measurements).
3. For polygons, check validity. An invalid polygon (for example a bow tie) is repaired with `make_valid` and a warning is attached.
4. Pick the projection (next section) and transform the geometry with `pyproj.Transformer(always_xy=True)`.
5. Measure with Shapely in the projected CRS: `.area` for polygons, `.length` for lines.
6. For geographic input, also compute the geodesic value with `pyproj.Geod` as a cross check.
7. Any unexpected error in one feature becomes an `unsupported` result for that feature only. One bad feature never fails the whole file.

### CRS handling

| Input CRS | What happens |
|---|---|
| Geographic (such as EPSG:4326) | Choose the WGS84 UTM zone from the feature centroid, transform, measure in meters |
| Projected (such as a State Plane CRS) | Measure directly in the file's own CRS. If the CRS uses feet, convert to meters |
| Shapefile without a `.prj` | File is marked `FAILED` with a clear message |
| Unrecognised or unsupported CRS | That feature is `unsupported`, the rest still work |

UTM zone is `floor((lon + 180) / 6) + 1`, with EPSG `326xx` for the north and `327xx` for the south. Near the poles (north of 84 degrees or south of 80 degrees) UTM is not defined, so the Universal Polar Stereographic CRS is used instead.

Real result from the sample file: a 0.001 by 0.001 degree square near Bengaluru measures 12,016.97 m² in UTM and 12,003.11 m² geodesically, a difference of about 0.12%. A sample line measures 775.216 m in UTM against 774.767 m geodesic, about 0.06% apart.

## Design decisions

**FastAPI instead of Django REST Framework.** The scope is a small, API only service. FastAPI gives typed request and response models, automatic OpenAPI docs and less boilerplate. Django would be the better choice if this grew to need an admin panel, built in auth and a larger ORM driven app.

**geopandas with pyogrio instead of using fiona or ogr directly.** One reader handles both Shapefile and KML through GDAL, and pyogrio ships with prebuilt wheels, which keeps installation simple. The cost is a heavier dependency stack than a single purpose reader.

**UTM from the centroid, with a geodesic cross check.** UTM is accurate to well under 0.5% inside a zone and is easy to explain. The alternatives I considered were a single equal area projection (good for area, poor for length), Web Mercator (heavy distortion, wrong for measurement), and pure geodesic math (most accurate, but harder to apply to polygons with holes and multi parts). I kept UTM as the main answer and added geodesic as a verification value so the accuracy is visible rather than assumed.

**Missing `.prj` fails instead of assuming EPSG:4326.** Guessing a CRS can silently produce wrong numbers. A clear failure is safer than a confident wrong answer. The trade-off is that some valid but incomplete files are rejected.

**Repair invalid polygons and warn.** Rejecting the whole file because one polygon self intersects is unfriendly. `make_valid` repairs it and the response carries a `warning`, so the caller knows the number came from a repaired shape.

**Store measurements at upload time.** Reads are fast and the numbers stay consistent with the CRS logic version that created them. The cost is extra storage and a need to reprocess if the measurement logic changes. Original uploads are kept on disk so reprocessing is possible.

**Synchronous processing.** Simpler and enough for files up to the size limit. The `status` field already exists, so moving processing to a background worker later does not change the API.

**SQLite.** Zero setup for reviewers. SQLAlchemy makes switching to PostgreSQL a configuration change, and PostGIS would be the natural next step.

**One consistent error format.** Every failure, including framework validation errors and unknown routes, returns the same JSON shape, and unexpected errors never leak a stack trace.

**Safety around uploads.** Zip slip is blocked by resolving every member path and checking it stays inside the temp directory. There are also limits on upload size, member count (500) and total uncompressed size (200 MB) to blunt zip bombs. The app runs as a non root user in Docker.

## Testing

```bash
python -m pytest -q
python -m ruff check .
```

Or inside Docker: `docker compose run --rm api python -m pytest -q`.

The suite has 38 tests covering:

- Upload validation: wrong type, empty file, corrupt zip, oversize file (with cleanup), unknown id
- Parsing: KML, multi folder KML, Shapefile zip, missing `.prj`, zip without `.shp`, empty and garbage KML
- Security: zip slip rejection
- Measurements: area and length checked against an independent `pyproj.Geod` calculation, UTM zone selection, axis order, MultiPolygon, 3D coordinates, invalid polygon repair, projected CRS in meters and in feet, unsupported and null geometry
- API behaviour: pagination, geometry type filter, the consistent error format

## Limitations and assumptions

- A feature that spans more than one UTM zone is measured in the zone of its centroid, so accuracy drops for very large shapes. Features crossing the antimeridian are not handled specially.
- All Shapefiles in one zip must share one CRS.
- Z values are kept in the stored geometry but ignored for measurement.
- Processing is synchronous, so very large files block the request until done.
- Uploaded files stay on disk after processing and are not cleaned up automatically.
- Timestamps come back without a timezone suffix because SQLite does not store one. They are UTC.
- Only Shapefile and KML are supported (no KMZ, GeoJSON or GeoPackage yet).

## Learnings

- **Geometry libraries use X then Y, humans say latitude then longitude.** Swapping them puts Bengaluru in the wrong UTM zone and quietly breaks every number. `always_xy=True` plus a test that asserts the chosen zone guards against it.
- **UTM is not ground truth.** Seeing a 0.12% gap between UTM and geodesic results made the accuracy trade-off concrete, and it is why the geodesic cross check exists.
- **KML needs cleanup.** GDAL names an unnamed KML layer after the stored filename (a UUID in this app), and every placemark carries a pile of empty style fields. I hide the internal layer name and drop empty and rendering only properties.
- **KML folders are layers.** Reading only the first layer would silently skip data, so all layers are read.
- **Zip files are untrusted input.** Plain `extractall` is unsafe. Path checking and size limits are part of the parsing step.
- **Catch specific exceptions.** Lint rules pushed me to narrow `except Exception` in the parsing helpers. There is still one deliberate catch all around each feature's measurement so one bad feature cannot fail the file.
- **Tooling gotchas.** Running `pytest` outside the virtual environment picked up a different install and produced a confusing `TestClient` error, so I use `python -m pytest`. `pyproj` tried to compile from source on one Python version until I forced prebuilt wheels. Ruff's B008 rule flags FastAPI's `Depends` pattern, so it is configured to allow it. SQLite silently drops timezone information.

## Future scope

- Background processing with a task queue (FastAPI background tasks first, then Celery or RQ with Redis) so `PENDING` to `COMPLETED` becomes a real transition
- PostgreSQL with PostGIS, spatial queries and indexes
- Authentication (API key or JWT) and per user file ownership
- More formats: KMZ, GeoJSON, GeoPackage
- Handling features that cross UTM zones or the antimeridian, possibly by switching to pure geodesic calculation for those cases
- Automatic cleanup of old uploads, or object storage such as S3
- Perimeter for polygons, and a summary endpoint with totals per geometry type
- A small map preview (for example a Leaflet viewer)
- CI with GitHub Actions running tests and lint on every push

## Changelog

See [CHANGELOG.md](CHANGELOG.md).