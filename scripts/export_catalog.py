"""Export validated metadata for catalog.json; publishing is an operator step."""
import json
import sys
from dataclasses import asdict
from fastlanelabs_sdk.registry import load

apps = {key: {k: v for k, v in asdict(entry).items() if k != 'id'} for key, entry in load().items()}
with open(sys.argv[1], 'w') as out:
    json.dump({'api_version': 1, 'apps': apps}, out, indent=2)
