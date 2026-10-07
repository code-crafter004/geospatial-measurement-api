from pyproj import CRS

UPS_NORTH = 32661
UPS_SOUTH = 32761


def utm_epsg(lon: float, lat: float) -> int:
    """EPSG code of the WGS84 UTM zone containing a lon/lat point."""
    lon = ((lon + 180) % 360) - 180
    zone = min(int((lon + 180) // 6) + 1, 60)
    return (32600 if lat >= 0 else 32700) + zone


def choose_projected_crs(lon: float, lat: float) -> CRS:
    """UTM for most of the globe, UPS near the poles where UTM is undefined."""
    if lat > 84:
        return CRS.from_epsg(UPS_NORTH)
    if lat < -80:
        return CRS.from_epsg(UPS_SOUTH)
    return CRS.from_epsg(utm_epsg(lon, lat))


def metres_per_unit(crs: CRS) -> float:
    """Metres per CRS axis unit (1.0 for metres, about 0.3048 for feet)."""
    return crs.axis_info[0].unit_conversion_factor or 1.0
