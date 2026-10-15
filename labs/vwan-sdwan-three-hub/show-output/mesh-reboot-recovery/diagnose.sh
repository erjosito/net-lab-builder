#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import subprocess,json,hashlib
from pathlib import Path
def run(*args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=20)
 return p.stdout.strip() or p.stderr.strip()
data={}
for field in ('listen-port','fwmark','endpoints','latest-handshakes','transfer'):
 data[field]=run('wg','show','all',field)
data['rules']=run('ip','-4','rule','show')
data['table100']=run('ip','-4','route','show','table','100')
data['nat']= '\n'.join(line for line in run('iptables-save','-t','nat').splitlines() if 'TH_WG' in line)
data['services']=run('systemctl','show','threehub-network.service','-p','ActiveState','-p','SubState','-p','Result','-p','ExecMainStatus','-p','ActiveEnterTimestamp')
data['default']=run('ip','-4','route','show','default')
data['boot']=run('uptime','-s')
print('MESH_DIAGNOSTIC '+json.dumps(data,separators=(',',':')))
PY
