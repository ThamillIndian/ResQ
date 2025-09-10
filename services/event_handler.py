from typing import List, Dict

from disaster_relief_backend.models import Event, Plan, Zone, Depot, Asset
from disaster_relief_backend.services.optimizer import optimize_plan
from disaster_relief_backend.utils.distance_matrix import compute_distance_matrix


def apply_event(
    plan: Plan | None,
    event: Event,
    zones: List[Zone],
    depots: List[Depot],
    assets: List[Asset],
    distance_matrix: Dict[str, Dict[str, float]],
) -> Plan:
    """
    - Update zone demand or access based on event
    - Re-run optimize_plan with updated data
    - Return updated Plan
    """
    # Update the relevant zone state
    for zone in zones:
        if zone.zone_id == event.target_zone or zone.name == event.target_zone:
            if event.type == "road_block":
                # If caller did not provide new_access, default to boat_only
                zone.access = event.new_access or "boat_only"
            elif event.type == "road_clear":
                # Default to restoring road access; caller can override via new_access
                zone.access = event.new_access or "road_open"
            elif event.type == "sos_spike" and event.additional_demand:
                zone.demand_food += event.additional_demand
                zone.demand_water += event.additional_demand
                zone.demand_med += event.additional_demand

    # Recompute distances in case access rules later affect speed calculations
    updated_distance_matrix = compute_distance_matrix(depots, zones)
    return optimize_plan(zones, depots, assets, updated_distance_matrix)


