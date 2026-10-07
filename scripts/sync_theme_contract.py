"""Generate the host's type-only contract and theme v2 runtime files without bundling SDK tooling."""
from pathlib import Path
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('host',type=Path)
args=parser.parse_args()
source=Path(__file__).resolve().parents[1]/'frontend/theme-contract.ts'
target=args.host/'frontend/src/generated/theme-contract.ts'
target.parent.mkdir(parents=True,exist_ok=True)
target.write_bytes(source.read_bytes())

pack_source=source.with_name('theme-pack-contract.ts')
pack_target=target.with_name('theme-pack-contract.ts')
pack_target.write_bytes(pack_source.read_bytes())

# Theme API v2: the pure resolver, the registry it reads and the generated CSS and Tailwind preset.
for name in ('theme-resolve.ts','theme-registry.json','theme-defaults.css','tailwind-preset.mjs'):
    (target.parent/name).write_bytes((source.parent/name).read_bytes())
