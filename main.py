from pathlib import Path

from fastapi import FastAPI

from models import Zone, Depot, Asset, Event, Plan
from utils.data_loader import load_zones, load_depots, load_assets
from utils.distance_matrix import compute_distance_matrix
from services.optimizer import optimize_plan
from services.event_handler import apply_event
from services.rationals import generate_rationales


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

@app.post("/planning")
def planning_endpoint(event: Event) -> Dict[str, Any]:
    """
    Planning endpoint that processes an event and returns optimized depot recommendations
    with best assets selected and ranked by distance.
    """
    # First get the event response
    event_response = apply_event_endpoint(event)
    
    # Get target zone for distance calculations
    target_zone = next((z for z in zones if z.zone_id == event.target_zone or z.name == event.target_zone), None)
    if not target_zone:
        raise HTTPException(status_code=404, detail=f"Zone {event.target_zone} not found")
    
    # Extract demand from event response, only including explicitly provided demands
    demand = {}
    if event.food_demand is not None:
        demand["food"] = event.food_demand
    if event.water_demand is not None:
        demand["water"] = event.water_demand
    if event.medical_demand is not None:
        demand["medical"] = event.medical_demand
        
    if not demand:
        raise HTTPException(status_code=400, detail="At least one demand (food, water, or medical) must be specified")
    
    # Process each potential depot
    ranked_depots = []
    
    for depot_info in event_response["potential_depots"]:
        depot = depot_info["depot"]
        available_resources = depot_info["available_resources"]
        assets_by_type = depot_info["assets"]
        
        # Calculate distance to target zone
        distance_km = distance_matrix[depot["depot_id"]][target_zone.zone_id]
        
        # Find best assets for this depot
        best_assets = []
        # Initialize remaining_demand with only the requested demands
        remaining_demand = {k: v for k, v in demand.items()}
        
        # Get all assets from this depot
        all_assets = []
        for asset_type, assets in assets_by_type.items():
            all_assets.extend(assets)
        
        # Sort assets by total capacity for the requested demands
        def get_asset_score(asset):
            score = 0
            for d_type in demand:
                score += asset["capacity"].get(d_type, 0)
            return score
            
        all_assets.sort(key=get_asset_score, reverse=True)
        
        # Select assets until demand is met or no more suitable assets
        for asset in all_assets:
            asset_capacity = asset["capacity"]
            
            # Check if this asset can contribute to remaining demand
            can_contribute = False
            asset_contribution = {d_type: 0 for d_type in demand}
            
            # Calculate how much this asset can contribute
            for d_type in demand:
                if remaining_demand.get(d_type, 0) > 0 and asset_capacity.get(d_type, 0) > 0:
                    contribution = min(remaining_demand[d_type], asset_capacity[d_type])
                    asset_contribution[d_type] = contribution
                    remaining_demand[d_type] -= contribution
                    can_contribute = True
            
            if can_contribute:
                # Calculate ETA based on distance and asset type
                asset_type = next((asset_type for asset_type, assets in assets_by_type.items() if asset in assets), "unknown")
                
                # Different speeds for different asset types (km/h)
                if asset_type == "truck":
                    speed_kmh = 40  # Average truck speed in city conditions
                elif asset_type == "boat":
                    speed_kmh = 25  # Average boat speed
                else:
                    speed_kmh = 30  # Default speed
                
                # Calculate ETA in minutes
                eta_minutes = round((distance_km / speed_kmh) * 60)
                
                best_assets.append({
                    "asset_id": asset["asset_id"],
                    "type": asset_type,
                    "capacity": asset_capacity,
                    "contribution": asset_contribution,
                    "eta_minutes": eta_minutes
                })
            
            # If all requested demands are met, stop adding assets
            if all(remaining_demand.get(key, 0) <= 0 for key in demand):
                break
        
        # Calculate coverage percentage based only on requested demands
        total_demand = sum(demand.get(d_type, 0) for d_type in demand)
        total_contribution = 0
        for asset in best_assets:
            for d_type in demand:
                total_contribution += asset["contribution"].get(d_type, 0)
        coverage_percent = (total_contribution / total_demand * 100) if total_demand > 0 else 0
        
        # Find fastest ETA among best assets
        fastest_eta = min((asset["eta_minutes"] for asset in best_assets), default=None)
        
        # Add depot to ranked list
        ranked_depots.append({
            "depot": depot,
            "distance_km": round(distance_km, 2),
            "available_resources": available_resources,
            "best_assets": best_assets,
            "coverage_percent": round(coverage_percent, 1),
            "can_fulfill_demand": coverage_percent >= 100,
            "fastest_eta_minutes": fastest_eta
        })
    
    # Sort depots by distance (closest first)
    ranked_depots.sort(key=lambda x: x["distance_km"])
    
    # Prepare response
    response = {
        "event_type": event.type,
        "target_zone": event_response["target_zone"],
        "demand": {k: v for k, v in demand.items() if v is not None},
        "access_type": event_response.get("access_type", "road_open"),
        "ranked_depots": ranked_depots,
        "summary": {
            "total_depots": len(ranked_depots),
            "depots_can_fulfill": len([d for d in ranked_depots if d["can_fulfill_demand"]]),
            "closest_depot": ranked_depots[0]["depot"]["name"] if ranked_depots else None,
            "closest_distance_km": ranked_depots[0]["distance_km"] if ranked_depots else None,
            "fastest_eta_minutes": min((d["fastest_eta_minutes"] for d in ranked_depots if d["fastest_eta_minutes"] is not None), default=None)
        }
    }
    
    return response

@app.post("/event")
def apply_event_endpoint(event: Event) -> Dict[str, Any]:
    # First apply the event and get the full plan
    updated_plan = apply_event(None, event, zones, depots, assets, distance_matrix)
    updated_plan.rationales = generate_rationales(updated_plan)
    
    # Get the target zone details
    target_zone = next((z for z in zones if z.zone_id == event.target_zone or z.name == event.target_zone), None)
    if not target_zone:
        raise HTTPException(status_code=404, detail=f"Zone {event.target_zone} not found")

    # Calculate total demand (use specific demands if provided, otherwise use zone's current demand)
    demand_food = event.food_demand if event.food_demand is not None else target_zone.demand_food
    demand_water = event.water_demand if event.water_demand is not None else target_zone.demand_water
    demand_med = event.medical_demand if event.medical_demand is not None else target_zone.demand_med
    
    # Build demand response with only specified demands
    demand_response = {}
    if event.food_demand is not None:
        demand_response["food"] = demand_food
    if event.water_demand is not None:
        demand_response["water"] = demand_water
    if event.medical_demand is not None:
        demand_response["medical"] = demand_med

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
        "demand": demand_response,
        "potential_depots": potential_depots
    }
    
    # Add additional info if present
    if hasattr(event, 'new_access') and event.new_access:
        response["access_type"] = event.new_access
    
    return response


