#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import subprocess,json
def run(*args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=20);return (p.stdout+p.stderr).strip()
d={}
d['links']=run('ip','-d','-br','link')
d['addresses']=run('ip','-o','-4','addr')
d['capture']=run('timeout','8','tcpdump','-p','-nn','-i','any','-c','12','udp and portrange 51820-51826')
d['backend']=run('iptables','--version')
d['nft']=run('nft','list','table','ip','nat')
print('MESH_DIAGNOSTIC '+json.dumps(d,separators=(',',':')))
PY
