"""List low-cloud Sentinel-2 L2A scenes (Planetary Computer) over a bbox."""
import sys
import planetary_computer as pc
from pystac_client import Client

bbox = [float(x) for x in sys.argv[1].split(",")]
rng = sys.argv[2]
cat = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
s = cat.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=rng,
               query={"eo:cloud_cover": {"lt": 30}})
for it in sorted(s.items(), key=lambda i: i.datetime):
    print(it.id, it.properties["eo:cloud_cover"])
