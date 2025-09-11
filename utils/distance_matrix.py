import math
from typing import Dict

from models import Zone, Depot


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compute_distance_matrix(depots: list[Depot], zones: list[Zone]) -> Dict[str, Dict[str, float]]:
    """
    Returns a nested dict keyed by IDs: matrix[depot_id][zone_id] = distance_km
    Using IDs avoids name-mismatch issues.
    """
    matrix: Dict[str, Dict[str, float]] = {}
    for depot in depots:
        matrix[depot.depot_id] = {}
        for zone in zones:
            matrix[depot.depot_id][zone.zone_id] = haversine(depot.lat, depot.lon, zone.lat, zone.lon)
    return matrix


