"""Candidate site definitions — ground truth for the scoring engine."""
from typing import Optional
from pydantic import BaseModel


class Site(BaseModel):
    id: str
    name: str
    short_name: str
    location: str
    lat: float
    lng: float
    state: str
    market: str
    acres: int
    land_cost_per_acre: int
    fiber_km: float
    water_km: float
    pipeline_km: float
    gas_hub: str
    lmp_node: str
    lmp: Optional[float] = None


CANDIDATE_SITES: list[Site] = [
    Site(id="TX-PB-001", name="Permian Prime",      short_name="PERM-A",
         location="Midland, TX",    lat=31.9973, lng=-102.0779,
         state="TX", market="ERCOT", acres=1240, land_cost_per_acre=950,
         fiber_km=1.8, water_km=6.2, pipeline_km=0.4, gas_hub="Waha",
         lmp_node="HB_WEST", lmp=None),
    Site(id="TX-WJ-001", name="Waha Junction",      short_name="WAHA-A",
         location="Pecos, TX",      lat=31.4224, lng=-104.2029,
         state="TX", market="ERCOT", acres=890,  land_cost_per_acre=780,
         fiber_km=4.2, water_km=12.1, pipeline_km=0.1, gas_hub="Waha",
         lmp_node="HB_WEST", lmp=None),
    Site(id="NM-DB-001", name="Delaware Basin",      short_name="DLWR-A",
         location="Carlsbad, NM",   lat=32.4207, lng=-104.2288,
         state="NM", market="ERCOT", acres=1580, land_cost_per_acre=620,
         fiber_km=6.8, water_km=4.3, pipeline_km=0.8, gas_hub="Waha",
         lmp_node="HB_WEST", lmp=None),
    Site(id="TX-WTP-001", name="West Texas Plains",  short_name="WTP-A",
         location="Andrews, TX",    lat=32.3170, lng=-102.5535,
         state="TX", market="ERCOT", acres=2100, land_cost_per_acre=720,
         fiber_km=3.1, water_km=9.4, pipeline_km=1.2, gas_hub="Waha",
         lmp_node="HB_WEST", lmp=None),
    Site(id="TX-PS-001",  name="Permian South",      short_name="PERM-S",
         location="Odessa, TX",     lat=31.8457, lng=-102.3676,
         state="TX", market="ERCOT", acres=760,  land_cost_per_acre=1100,
         fiber_km=0.8, water_km=3.2, pipeline_km=0.6, gas_hub="Waha",
         lmp_node="HB_WEST", lmp=None),
    Site(id="TX-PH-001",  name="Panhandle",           short_name="PAN-A",
         location="Amarillo, TX",   lat=35.2220, lng=-101.8313,
         state="TX", market="ERCOT", acres=1850, land_cost_per_acre=580,
         fiber_km=2.4, water_km=5.6, pipeline_km=1.8, gas_hub="Panhandle EP",
         lmp_node="HB_NORTH", lmp=None),
    Site(id="NM-RC-001",  name="Roswell Corridor",    short_name="RSW-A",
         location="Roswell, NM",    lat=33.3942, lng=-104.5230,
         state="NM", market="WECC", acres=1020, land_cost_per_acre=540,
         fiber_km=5.6, water_km=7.8, pipeline_km=2.1, gas_hub="Waha",
         lmp_node="PALOVRDE_ASR-APND", lmp=38.50),
    Site(id="AZ-PD-001",  name="Phoenix Desert",      short_name="PHX-A",
         location="Buckeye, AZ",    lat=33.3703, lng=-112.5838,
         state="AZ", market="WECC", acres=640,  land_cost_per_acre=2800,
         fiber_km=1.2, water_km=2.1, pipeline_km=3.4, gas_hub="SoCal Gas",
         lmp_node="PALOVRDE_ASR-APND", lmp=38.50),
]
