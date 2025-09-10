from pathlib import Path

from fastapi import FastAPI

from disaster_relief_backend.models import Zone, Depot, Asset, Event, Plan
from disaster_relief_backend.utils.data_loader import load_zones, load_depots, load_assets
from disaster_relief_backend.utils.distance_matrix import compute_distance_matrix
from disaster_relief_backend.services.optimizer import optimize_plan
from disaster_relief_backend.services.event_handler import apply_event
from disaster_relief_backend.services.rationals import generate_rationales


app = FastAPI()


# Resolve data paths relative to this file
BASE_DIR = Path(__file__).parent
ZONES_PATH = BASE_DIR / "database" / "zones.json"
DEPOTS_PATH = BASE_DIR / "database" / "depots.json"
ASSETS_PATH = BASE_DIR / "database" / "assets.json"


# Load data at startup
zones = load_zones(str(ZONES_PATH))
depots = load_depots(str(DEPOTS_PATH))
assets = load_assets(str(ASSETS_PATH))
distance_matrix = compute_distance_matrix(depots, zones)


@app.get("/zones")
def get_zones() -> list[Zone]:
    return zones


@app.get("/depots")
def get_depots() -> list[Depot]:
    return depots


@app.get("/assets")
def get_assets() -> list[Asset]:
    return assets


@app.post("/optimize")
def run_optimization() -> Plan:
    plan = optimize_plan(zones, depots, assets, distance_matrix)
    plan.rationales = generate_rationales(plan)
    return plan


from typing import List, Dict, Any
from fastapi import HTTPException

@app.post("/event")
def apply_event_endpoint(event: Event) -> Dict[str, Any]:
    # First apply the event and get the full plan
    updated_plan = apply_event(None, event, zones, depots, assets, distance_matrix)
    updated_plan.rationales = generate_rationales(updated_plan)
    
    # Get the target zone details
    target_zone = next((z for z in zones if z.zone_id == event.target_zone or z.name == event.target_zone), None)
    if not target_zone:
        raise HTTPException(status_code=404, detail=f"Zone {event.target_zone} not found")

    # Calculate total demand (use additional_demand if provided, otherwise use zone's current demand)
    demand_food = event.additional_demand if event.additional_demand else target_zone.demand_food
    demand_water = event.additional_demand if event.additional_demand else target_zone.demand_water
    demand_med = event.additional_demand if event.additional_demand else target_zone.demand_med

    # Determine which asset types to look for based on access type
    access_type = getattr(event, 'new_access', 'road_open')
    
    if access_type == 'boat_only':
        asset_types = ["boat"]
    elif access_type == 'road_open':
        asset_types = ["truck"]
    else:  # both or any other case
        asset_types = ["truck", "boat"]

    potential_depots = []
    
    for depot in depots:
        # Get all relevant assets for this depot based on access type
        relevant_assets = [
            asset for asset in assets 
            if asset.type in asset_types and 
               (asset.start_depot == depot.depot_id or asset.start_depot == depot.name)
        ]
        
        if not relevant_assets:
            continue
            
        # Calculate available resources in this depot
        available_food = depot.stock_food
        available_water = depot.stock_water
        available_med = depot.stock_med
        
        # Check if this depot can contribute to the demand
        if (available_food > 0 or demand_food == 0) and \
           (available_water > 0 or demand_water == 0) and \
           (available_med > 0 or demand_med == 0):
            
            # Calculate total capacity for this depot's assets
            total_capacity = {
                "food": sum(asset.cap_food for asset in relevant_assets),
                "water": sum(asset.cap_water for asset in relevant_assets),
                "medical": sum(asset.cap_med for asset in relevant_assets)
            }
            
            # Group assets by type
            assets_by_type = {}
            for asset_type in asset_types:
                type_assets = [a for a in relevant_assets if a.type == asset_type]
                if type_assets:
                    assets_by_type[asset_type] = type_assets
            
            # Prepare the contribution
            contribution = {
                "depot": {
                    "depot_id": depot.depot_id,
                    "name": depot.name,
                    "location": {"lat": depot.lat, "lon": depot.lon}
                },
                "available_resources": {
                    "food": available_food,
                    "water": available_water,
                    "medical": available_med
                },
                "total_capacity": total_capacity,
                "assets": {}
            }
            
            # Add assets grouped by type
            for asset_type, type_assets in assets_by_type.items():
                contribution["assets"][asset_type] = [
                    {
                        "asset_id": asset.asset_id,
                        "capacity": {
                            "food": asset.cap_food,
                            "water": asset.cap_water,
                            "medical": asset.cap_med
                        }
                    }
                    for asset in type_assets
                ]
                
            potential_depots.append(contribution)

    # Prepare response
    response = {
        "event_type": event.type,
        "target_zone": {
            "zone_id": target_zone.zone_id,
            "name": target_zone.name,
            "location": {"lat": target_zone.lat, "lon": target_zone.lon},
            "access_type": access_type
        },
        "demand": {
            "food": demand_food,
            "water": demand_water,
            "medical": demand_med
        },
        "potential_depots": potential_depots
    }
    
    # Add additional info if present
    if hasattr(event, 'new_access') and event.new_access:
        response["access_type"] = event.new_access
    
    return response


