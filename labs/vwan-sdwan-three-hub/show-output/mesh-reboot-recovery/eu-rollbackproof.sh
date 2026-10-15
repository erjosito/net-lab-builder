#!/bin/bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
import hashlib,json,subprocess
p=Path('/opt/threehub/network.sh');b=Path('/var/lib/threehub/mesh-reboot-network.sh')
digest=hashlib.sha256(p.read_bytes()).hexdigest()
assert p.read_bytes()==b.read_bytes()
assert digest=='a44f8561e92eca28285236999d9bfc18980bc9e012c420768f04fd570f39476b'
rules=subprocess.check_output(['iptables','-t','nat','-S','TH_WG_IN'],text=True,timeout=20)
assert rules.count('-j REDIRECT --to-ports ')==3
assert 'DNAT' not in rules
print('MESH_DIAGNOSTIC '+json.dumps(dict(rollbackVerified=True,networkSha256=digest,rules=rules),separators=(',',':')))
PY
