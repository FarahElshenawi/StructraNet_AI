from typing import Dict, FrozenSet

MAX_RETRIES: int = 3

# Prompt-side conservative limits to prevent impossible designs.
DYNAMIPS_MAX_LINKS: Dict[str, int] = {
    "c7200": 3,
    "c3745": 6,
    "c3725": 6,
    "c3660": 5,
    "c3640": 4,
    "c3620": 4,
    "c2691": 6,
    "c2600": 2,
    "c1700": 2,
}

SINGLE_LINK_TYPES: FrozenSet[str] = frozenset({"vpcs", "traceng", "nat"})

