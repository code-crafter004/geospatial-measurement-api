import json
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pyogrio

MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_ZIP_MEMBERS = 500


class ParseError(Exception):
    """Raised when a file cannot be turned into features."""


@dataclass
class ParsedFeature:
    index: int
    layer: str | None
    geometry_type: str | None
    geometry: dict | None
    properties: dict


@dataclass
class ParsedFile:
    crs: str
    features: list[ParsedFeature]


def _crs_label(crs) -> str:
    epsg = crs.to_epsg()
    if epsg:
        return f"EPSG:{epsg}"
    authority = crs.to_authority()
    if authority:
        return f"{authority[0]}:{authority[1]}"
    return f"custom:{crs.name}"[:50]


def _frame_to_features(gdf, layer: str | None, start: int) -> list[ParsedFeature]:
    geom_types = list(gdf.geometry.geom_type)
    collection = json.loads(gdf.to_json())
    features = []
    for offset, (feat, gtype) in enumerate(zip(collection["features"], geom_types)):
        features.append(
            ParsedFeature(
                index=start + offset,
                layer=layer,
                geometry_type=gtype if isinstance(gtype, str) else None,
                geometry=feat.get("geometry"),
                properties=feat.get("properties") or {},
            )
        )
    return features


def safe_extract(zip_path: Path, dest: Path) -> None:
    """Extract a zip after checking for zip slip and zip bombs."""
    dest = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_MEMBERS:
            raise ParseError("Zip contains too many files")
        if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
            raise ParseError("Zip is too large once extracted")
        for info in infos:
            target = (dest / info.filename).resolve()
            if not target.is_relative_to(dest):
                raise ParseError("Zip contains an unsafe file path")
        zf.extractall(dest)


def parse_kml(path: Path) -> ParsedFile:
    try:
        layers = pyogrio.list_layers(path)
    except Exception as exc:
        raise ParseError(f"Could not read KML: {str(exc)[:300]}") from exc

    features: list[ParsedFeature] = []
    for layer_name, _ in layers:
        try:
            gdf = gpd.read_file(path, layer=layer_name, engine="pyogrio")
        except Exception as exc:
            raise ParseError(
                f"Could not read KML layer '{layer_name}': {str(exc)[:300]}"
            ) from exc
        if gdf.empty:
            continue
        features.extend(_frame_to_features(gdf, layer_name, len(features)))

    # KML is always WGS84 lon/lat by specification.
    return ParsedFile(crs="EPSG:4326", features=features)


def parse_shapefile_zip(path: Path) -> ParsedFile:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        safe_extract(path, tmp_path)

        shps = sorted(
            p
            for p in tmp_path.rglob("*.shp")
            if "__MACOSX" not in p.parts and not p.name.startswith("._")
        )
        if not shps:
            raise ParseError("Zip does not contain a .shp file")

        features: list[ParsedFeature] = []
        crs_label: str | None = None
        for shp in shps:
            try:
                gdf = gpd.read_file(shp, engine="pyogrio")
            except Exception as exc:
                raise ParseError(
                    f"Could not read {shp.name}: {str(exc)[:300]}"
                ) from exc

            if gdf.crs is None:
                raise ParseError(f"{shp.name} has no CRS (missing .prj file)")

            label = _crs_label(gdf.crs)
            if crs_label and label != crs_label:
                raise ParseError("Shapefiles with different CRS in one zip are not supported")
            crs_label = label

            if gdf.empty:
                continue
            features.extend(_frame_to_features(gdf, shp.stem, len(features)))

    return ParsedFile(crs=crs_label or "EPSG:4326", features=features)


def parse_file(path: Path, file_type: str) -> ParsedFile:
    if file_type == "kml":
        parsed = parse_kml(path)
    elif file_type == "shapefile_zip":
        parsed = parse_shapefile_zip(path)
    else:
        raise ParseError(f"Unsupported file type: {file_type}")

    if not parsed.features:
        raise ParseError("No features found in file")
    return parsed
