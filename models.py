from pydantic import BaseModel
from typing import List, Optional


class Zone(BaseModel):
    zone_id: str
    name: str
    lat: float
    lon: float
    population: int
    access: str  # "road_open", "boat_only", "both"
    severity: float  # 0-1
    demand_food: int
    demand_water: int
    demand_med: int


class Depot(BaseModel):
    depot_id: str
    name: str
    lat: float
    lon: float
    stock_food: int
    stock_water: int
    stock_med: int


class Asset(BaseModel):
    asset_id: str
    type: str  # "truck" or "boat"
    start_depot: str
    cap_food: int
    cap_water: int
    cap_med: int


class Event(BaseModel):
    type: str  # "road_block" or "sos_spike"
    target_zone: str
    food_demand: Optional[int] = None
    water_demand: Optional[int] = None
    medical_demand: Optional[int] = None
    new_access: Optional[str] = None


class Assignment(BaseModel):
    asset_id: str
    zone_id: str
    load_food: int
    load_water: int
    load_med: int
    eta_minutes: int


class KPIs(BaseModel):
    coverage_percent: float
    fairness_percent: float
    median_eta: int


class Plan(BaseModel):
    assignments: List[Assignment]
    kpis: KPIs
    rationales: List[str]


