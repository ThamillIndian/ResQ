from typing import List

from models import Plan


def generate_rationales(plan: Plan) -> List[str]:
    """
    - Send plan data to Gemini 2.0 API
    - Return list of human-readable rationales per assignment
    """
    # Placeholder: integrate Gemini 2.0 later
    return [
        f"Assignment of asset {a.asset_id} to zone {a.zone_id} based on proximity and demand"
        for a in plan.assignments
    ]


