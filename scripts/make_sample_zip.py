import shutil
import tempfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

out = Path(__file__).resolve().parent.parent / "samples" / "plots"
tmp = Path(tempfile.mkdtemp())

gdf = gpd.GeoDataFrame(
    {"name": ["Plot A", "Plot B"]},
    geometry=[
        Polygon([(77.590, 12.970), (77.591, 12.970), (77.591, 12.971), (77.590, 12.971)]),
        Polygon([(77.592, 12.970), (77.593, 12.970), (77.593, 12.972), (77.592, 12.972)]),
    ],
    crs="EPSG:4326",
)
gdf.to_file(tmp / "plots.shp", engine="pyogrio")
print("created:", shutil.make_archive(str(out), "zip", tmp))
