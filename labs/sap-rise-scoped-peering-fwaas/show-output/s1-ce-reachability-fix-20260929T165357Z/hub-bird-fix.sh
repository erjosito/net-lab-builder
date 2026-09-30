set -eu
cp /etc/bird/bird.conf /etc/bird/bird.conf.bak-ce-reachability-20260929
python3 - <<'"'"'PY'"'"'
from pathlib import Path
path = Path("/etc/bird/bird.conf")
old = "protocol kernel { ipv4 { import all; export none; }; learn; scan time 15; }\n"
new = "protocol kernel { ipv4 { import all; export where proto = \"static_bgp\"; }; learn; scan time 15; }\n"
text = path.read_text()
if old not in text:
    raise SystemExit("expected kernel export-none line not found exactly; stop and escalate to Trinity")
path.write_text(text.replace(old, new, 1))
PY
birdc configure
grep -n "protocol kernel" /etc/bird/bird.conf
birdc show route 10.60.0.0/16 all
ip route get 10.60.1.4
