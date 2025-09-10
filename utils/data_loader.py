import json
from typing import List

from disaster_relief_backend.models import Zone, Depot, Asset


def load_zones(path: str) -> List[Zone]:
    with open(path) as f:
        data = json.load(f)
    return [Zone(**zone) for zone in data["zones"]]


def load_depots(path: str) -> List[Depot]:
    with open(path) as f:
        data = json.load(f)
    return [Depot(**depot) for depot in data["depots"]]


def load_assets(path: str) -> List[Asset]:
    with open(path) as f:
        data = json.load(f)
    return [Asset(**asset) for asset in data["assets"]]

