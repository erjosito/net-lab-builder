#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import subprocess,json
from pathlib import Path
def run(*args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=15)
 return (p.stdout+p.stderr).strip()
d={}
d['publicKeys']=run('wg','show','all','public-key')
d['peerKeys']=run('wg','show','all','peers')
d['wgAddress']=run('ip','-br','-4','addr')
d['udpSockets']=run('ss','-unlp')
d['conntrack']= '\n'.join(line for path in ('/proc/net/nf_conntrack','/proc/net/ip_conntrack') if Path(path).exists() for line in Path(path).read_text().splitlines() if 'dport=5182' in line)[:1800]
d['filter']=run('iptables','-S')
d['networkHash']=run('sha256sum','/opt/threehub/network.sh')
print('MESH_DIAGNOSTIC '+json.dumps(d,separators=(',',':')))
PY
