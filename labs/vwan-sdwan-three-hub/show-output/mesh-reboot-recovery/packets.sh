#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import subprocess,json
def run(*args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=22)
 return (p.stdout+p.stderr).strip()
d={}
d['capture']=run('timeout','12','tcpdump','-p','-nn','-i','eth0','-c','24','udp and portrange 51820-51826')
d['natCounters']=run('iptables','-t','nat','-L','TH_WG_IN','-nvx')+'\n'+run('iptables','-t','nat','-L','TH_WG_OUT','-nvx')
d['conntrack']=run('sh','-c', "if command -v conntrack >/dev/null; then conntrack -L -p udp 2>/dev/null | grep -E 'port=5182[0-6]' | head -16; else echo conntrack-unavailable; fi")
d['routeMarked']=run('ip','route','get','10.210.0.4','mark','0x200')
d['routeUnmarked']=run('ip','route','get','10.210.0.4')
d['unit']=run('systemctl','cat','threehub-network.service')
print('MESH_DIAGNOSTIC '+json.dumps(d,separators=(',',':')))
PY
