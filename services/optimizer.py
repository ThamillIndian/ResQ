from typing import List, Dict, Tuple

from ortools.linear_solver import pywraplp
from utils.distance_matrix import haversine

from models import Zone, Depot, Asset, Assignment, Plan, KPIs
import logging

logger = logging.getLogger(__name__)


def _is_access_allowed(asset_type: str, zone_access: str) -> bool:
    if asset_type == "truck":
        return zone_access in ("road_open", "both")
    if asset_type == "boat":
        return zone_access in ("boat_only", "both")
    return False


def _asset_speed_kmph(asset_type: str) -> float:
    if asset_type == "truck":
        return 35.0
    if asset_type == "boat":
        return 20.0
    return 25.0


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return float(sorted_vals[mid])
    return float((sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0)


def optimize_plan(
    zones: List[Zone],
    depots: List[Depot],
    assets: List[Asset],
    distance_matrix: Dict[str, Dict[str, float]],
) -> Plan:
    """
    Mixed Integer Program using OR-Tools:
    - Each asset may serve at most one zone.
    - Loads are non-negative and limited by asset capacity, depot stock, and zone demand.
    - Infeasible pairs (by access) are disallowed.
    Objective (linearized proxy): maximize total delivered demand with small penalty on distance.
    """
    solver = pywraplp.Solver.CreateSolver("CBC")
    if solver is None:
        # Fallback: return empty plan if solver not available
        return Plan(assignments=[], kpis=KPIs(coverage_percent=0.0, fairness_percent=0.0, median_eta=0), rationales=[])

    # Index helpers
    zone_by_id: Dict[str, Zone] = {z.zone_id: z for z in zones}
    zone_ids: List[str] = [z.zone_id for z in zones]
    depot_by_id: Dict[str, Depot] = {d.depot_id: d for d in depots}
    # Allow lookup by either depot_id or depot name (case-insensitive)
    depot_by_any: Dict[str, Depot] = {}
    for d in depots:
        # Index by id and by normalized name (strip + lower)
        depot_by_any[d.depot_id] = d
        depot_by_any[d.depot_id.strip()] = d
        depot_by_any[d.name.lower()] = d
        depot_by_any[d.name.strip().lower()] = d
    asset_ids: List[str] = [a.asset_id for a in assets]

    def resolve_depot(start_depot_value: str) -> Depot | None:
        if start_depot_value is None:
            return None
        raw = start_depot_value
        norm = raw.strip()
        lower = raw.lower()
        lower_norm = norm.lower()
        return (
            depot_by_any.get(raw)
            or depot_by_any.get(norm)
            or depot_by_any.get(lower)
            or depot_by_any.get(lower_norm)
        )

    # Decision variables
    # y[a,z] in {0,1} whether asset a is assigned to zone z
    y: Dict[Tuple[str, str], pywraplp.Variable] = {}
    # Delivered loads per resource type
    lf: Dict[Tuple[str, str], pywraplp.Variable] = {}
    lw: Dict[Tuple[str, str], pywraplp.Variable] = {}
    lm: Dict[Tuple[str, str], pywraplp.Variable] = {}

    BIG_M = 10**6

    for a in assets:
        for z in zones:
            allowed = _is_access_allowed(a.type, z.access)
            # If not allowed, force y=0 and loads=0 by upper bounds 0
            y[(a.asset_id, z.zone_id)] = solver.BoolVar(f"y_{a.asset_id}_{z.zone_id}") if allowed else solver.IntVar(0, 0, f"y_{a.asset_id}_{z.zone_id}")
            ub = BIG_M if allowed else 0.0
            lf[(a.asset_id, z.zone_id)] = solver.NumVar(0.0, ub, f"lf_{a.asset_id}_{z.zone_id}")
            lw[(a.asset_id, z.zone_id)] = solver.NumVar(0.0, ub, f"lw_{a.asset_id}_{z.zone_id}")
            lm[(a.asset_id, z.zone_id)] = solver.NumVar(0.0, ub, f"lm_{a.asset_id}_{z.zone_id}")

    # Each asset serves at most one zone
    for a in assets:
        solver.Add(solver.Sum([y[(a.asset_id, z)] for z in zone_ids]) <= 1)

    # Link loads to assignment (loads can only flow if assigned)
    for a in assets:
        for z in zone_ids:
            solver.Add(lf[(a.asset_id, z)] <= a.cap_food * y[(a.asset_id, z)])
            solver.Add(lw[(a.asset_id, z)] <= a.cap_water * y[(a.asset_id, z)])
            solver.Add(lm[(a.asset_id, z)] <= a.cap_med * y[(a.asset_id, z)])

    # Zone demand limits
    for z in zones:
        solver.Add(solver.Sum([lf[(a.asset_id, z.zone_id)] for a in assets]) <= z.demand_food)
        solver.Add(solver.Sum([lw[(a.asset_id, z.zone_id)] for a in assets]) <= z.demand_water)
        solver.Add(solver.Sum([lm[(a.asset_id, z.zone_id)] for a in assets]) <= z.demand_med)

    # Depot stock limits (assets start at a.start_depot)
    for d in depots:
        assets_from_d = [
            a for a in assets
            if a.start_depot == d.depot_id or a.start_depot.lower() == d.name.lower()
        ]
        solver.Add(solver.Sum([lf[(a.asset_id, z)] for a in assets_from_d for z in zone_ids]) <= d.stock_food)
        solver.Add(solver.Sum([lw[(a.asset_id, z)] for a in assets_from_d for z in zone_ids]) <= d.stock_water)
        solver.Add(solver.Sum([lm[(a.asset_id, z)] for a in assets_from_d for z in zone_ids]) <= d.stock_med)

    # Objective: maximize delivered units minus small distance penalty to encourage proximity
    distance_penalty_terms = []
    delivered_terms = []
    for a in assets:
        # Resolve depot by id or name
        depot = resolve_depot(a.start_depot)  # may be None if unknown
        depot_key = depot.depot_id if depot else None
        for z in zones:
            delivered_terms.extend([lf[(a.asset_id, z.zone_id)], lw[(a.asset_id, z.zone_id)], lm[(a.asset_id, z.zone_id)]])
            dist_km = 0.0
            if depot_key is not None:
                dist_km = float(distance_matrix.get(depot_key, {}).get(z.zone_id, 0.0) or 0.0)
            # Fallback: compute directly if missing/zero
            if (dist_km == 0.0) and depot is not None:
                dist_km = haversine(depot.lat, depot.lon, z.lat, z.lon)
            # Small penalty scaled so it never dominates delivery
            distance_penalty_terms.append(0.001 * dist_km * y[(a.asset_id, z.zone_id)])

    objective = solver.Sum(delivered_terms) - solver.Sum(distance_penalty_terms)
    solver.Maximize(objective)

    status = solver.Solve()
    if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        return Plan(assignments=[], kpis=KPIs(coverage_percent=0.0, fairness_percent=0.0, median_eta=0), rationales=[])

    # Build assignments
    assignments: List[Assignment] = []
    eta_values: List[float] = []

    # Pre-compute total demands for KPIs
    total_food = sum(z.demand_food for z in zones)
    total_water = sum(z.demand_water for z in zones)
    total_med = sum(z.demand_med for z in zones)

    served_food = 0.0
    served_water = 0.0
    served_med = 0.0

    for a in assets:
        for z in zones:
            if y[(a.asset_id, z.zone_id)].solution_value() >= 0.5:
                load_food = int(round(lf[(a.asset_id, z.zone_id)].solution_value()))
                load_water = int(round(lw[(a.asset_id, z.zone_id)].solution_value()))
                load_med = int(round(lm[(a.asset_id, z.zone_id)].solution_value()))

                # ETA from depot to zone by asset speed (resolve by id or name)
                depot = resolve_depot(a.start_depot)
                # For ETA, compute distance directly to avoid any matrix key issues
                dist_km = 0.0
                if depot is not None:
                    dist_km = haversine(depot.lat, depot.lon, z.lat, z.lon)
                speed = _asset_speed_kmph(a.type)
                eta_min = int(round((dist_km / max(speed, 1e-6)) * 60.0))
                if y[(a.asset_id, z.zone_id)].solution_value() >= 0.5 and eta_min == 0 and dist_km > 0.0:
                    # Ensure at least 1 minute if distance is non-zero
                    eta_min = 1

                assignments.append(
                    Assignment(
                        asset_id=a.asset_id,
                        zone_id=z.zone_id,
                        load_food=load_food,
                        load_water=load_water,
                        load_med=load_med,
                        eta_minutes=eta_min,
                    )
                )
                eta_values.append(eta_min)
                served_food += load_food
                served_water += load_water
                served_med += load_med
                try:
                    depot_name = depot.name if depot is not None else None
                    logger.info(
                        "ETA_DEBUG asset=%s depot=%s zone=%s dist_km=%.3f speed_kmph=%.1f eta_min=%d",
                        a.asset_id,
                        depot_name,
                        z.zone_id,
                        dist_km,
                        speed,
                        eta_min,
                    )
                except Exception:
                    pass

    # KPIs
    total_demand = float(total_food + total_water + total_med)
    total_served = float(served_food + served_water + served_med)
    coverage = 0.0 if total_demand <= 0 else (total_served / total_demand) * 100.0

    # Simple fairness proxy: 100 - coefficient of variation of unmet demand across zones (clamped)
    unmet_per_zone: List[float] = []
    for z in zones:
        delivered_f = sum(
            lf[(a.asset_id, z.zone_id)].solution_value() if y[(a.asset_id, z.zone_id)].solution_value() >= 0.5 else 0.0
            for a in assets
        )
        delivered_w = sum(
            lw[(a.asset_id, z.zone_id)].solution_value() if y[(a.asset_id, z.zone_id)].solution_value() >= 0.5 else 0.0
            for a in assets
        )
        delivered_m = sum(
            lm[(a.asset_id, z.zone_id)].solution_value() if y[(a.asset_id, z.zone_id)].solution_value() >= 0.5 else 0.0
            for a in assets
        )
        unmet = max(z.demand_food - delivered_f, 0.0) + max(z.demand_water - delivered_w, 0.0) + max(z.demand_med - delivered_m, 0.0)
        unmet_per_zone.append(unmet)

    fairness = 100.0
    if unmet_per_zone and sum(unmet_per_zone) > 0:
        import math as _math

        mean_unmet = sum(unmet_per_zone) / len(unmet_per_zone)
        var_unmet = sum((u - mean_unmet) ** 2 for u in unmet_per_zone) / len(unmet_per_zone)
        std_unmet = _math.sqrt(var_unmet)
        cv = 0.0 if mean_unmet == 0 else std_unmet / mean_unmet
        fairness = max(0.0, 100.0 - min(100.0, cv * 100.0))

    median_eta = int(round(_median(eta_values)))

    kpis = KPIs(coverage_percent=float(round(coverage, 2)), fairness_percent=float(round(fairness, 2)), median_eta=median_eta)

    return Plan(assignments=assignments, kpis=kpis, rationales=[])


