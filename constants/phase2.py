from typing import Dict, FrozenSet, Tuple

SOFTWARE_CONFIG_KEYS: FrozenSet[str] = frozenset([
    "startup_config_content",
    "startup_script",
    "start_command",
    "environment",
])

ALLOWED_VALUE_TYPES: Dict[str, Tuple[type, ...]] = {
    "startup_config_content": (str,),
    "startup_script": (str,),
    "start_command": (str,),
    "environment": (dict, str),
}

