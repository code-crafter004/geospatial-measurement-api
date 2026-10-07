import logging

import shapely
from pyproj import CRS, Geod, Transformer
from pyproj.exceptions import CRSError
from shapely.errors import ShapelyError
from shapely.geometry import MultiPolygon, shape
from shapely.ops import transform
from shapely.validation import explain_validity, make_valid

from app.services.crs import choose_projected_crs, metres_per_unit

logger = logging.getLogger(__name__)

GEOD = Geod(ellps="WGS84")
POLYGONAL = {"Polygon", "MultiPolygon"}
LINEAR = {"LineString", "MultiLineString"}
POINTLIKE = {"Point", "MultiPoint"}


def _unsupported(reason: str) -> dict:
    return {"supported": False, "reason": reason}


def _lonlat(coords) -> tuple[list[float], list[float]]:
    xs, ys = coords.xy
    return list(xs), list(ys)


def _polygons(geom) -> list:
    out = []
    for part in shapely.get_parts(geom):
        if part.geom_type == "Polygon":
            out.append(part)
        elif part.geom_type in ("MultiPolygon", "GeometryCollection"):
            out.extend(_polygons(part))
    return out


def _geodesic_area(geom) -> float:
    total = 0.0
    for poly in _polygons(geom):
        outer = abs(GEOD.polygon_area_perimeter(*_lonlat(poly.exterior))[0])
        holes = sum(abs(GEOD.polygon_area_perimeter(*_lonlat(r))[0]) for r in poly.interiors)
        total += outer - holes
    return total


def _geodesic_length(geom) -> float:
    return sum(GEOD.line_length(*_lonlat(line)) for line in shapely.get_parts(geom))


def _measure(geometry: dict | None, crs_label: str) -> dict | None:
    if not geometry:
        return _unsupported("Feature has no geometry")
    try:
        geom = shape(geometry)
    except (ValueError, TypeError, KeyError, AttributeError, ShapelyError):
        return _unsupported("Geometry could not be parsed")
    if geom.is_empty:
        return _unsupported("Geometry is empty")

    gtype = geom.geom_type
    if gtype in POINTLIKE:
        return None
    if gtype not in POLYGONAL | LINEAR:
        return _unsupported(f"Unsupported geometry type for measurement: {gtype}")

    try:
        crs = CRS.from_user_input(crs_label)
    except CRSError:
        return _unsupported(f"Unrecognised CRS: {crs_label}")

    geom = shapely.force_2d(geom)

    warning = None
    if gtype in POLYGONAL and not geom.is_valid:
        warning = f"Invalid polygon repaired before measuring: {explain_validity(geom)}"
        polys = _polygons(make_valid(geom))
        if not polys:
            return _unsupported("Invalid polygon could not be repaired")
        geom = polys[0] if len(polys) == 1 else MultiPolygon(polys)

    geographic = crs.is_geographic
    if geographic:
        centroid = geom.centroid
        target = choose_projected_crs(centroid.x, centroid.y)
        transformer = Transformer.from_crs(crs, target, always_xy=True)
        projected = transform(transformer.transform, geom)
        factor = 1.0
        method = f"{target.name} ({target.to_string()})"
    elif crs.is_projected:
        projected = geom
        factor = metres_per_unit(crs)
        method = f"native projected CRS ({crs.to_string()})"
    else:
        return _unsupported(f"CRS type not supported for measurement: {crs_label}")

    if gtype in POLYGONAL:
        kind, unit = "area", "square_meters"
        value = projected.area * factor**2
        geodesic = _geodesic_area(geom) if geographic else None
    else:
        kind, unit = "length", "meters"
        value = projected.length * factor
        geodesic = _geodesic_length(geom) if geographic else None

    result = {
        "supported": True,
        "type": kind,
        "value": round(value, 3),
        "unit": unit,
        "method": method,
    }
    if geodesic is not None:
        result["geodesic_value"] = round(geodesic, 3)
    if warning:
        result["warning"] = warning
    return result


def measure_geometry(geometry: dict | None, crs_label: str) -> dict | None:
    """Never raises: any failure becomes an 'unsupported' result for that feature."""
    try:
        return _measure(geometry, crs_label)
    except Exception as exc:
        logger.exception("Measurement failed")
        return _unsupported(f"Measurement failed: {str(exc)[:200]}")
