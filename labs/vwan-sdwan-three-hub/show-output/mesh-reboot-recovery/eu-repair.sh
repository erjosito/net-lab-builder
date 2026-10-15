#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import subprocess,json,hashlib,os,time,shlex
from pathlib import Path
def run(*args):
 return subprocess.check_output(args,text=True,timeout=20).strip()
def bird_identity():
 p=Path('/etc/bird/bird.conf');s=p.stat()
 return dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),stat=dict(uid=s.st_uid,gid=s.st_gid,mode=s.st_mode&0o777,mtimeNs=s.st_mtime_ns))
expected={'sha256': '20fbaef367e78dd78b3e7d55e791d5c69dbae0a00fbd3c50ee0c2a740bdb4120', 'stat': {'uid': 113, 'gid': 122, 'mode': 384, 'mtimeNs': 1792000607648606479}}
assert bird_identity()==expected,'BIRD original mismatch before repair'
path=Path('/opt/threehub/network.sh')
source=path.read_bytes();info=path.stat()
oldrules=[shlex.split(line) for line in run('iptables','-t','nat','-S','TH_WG_IN').splitlines() if line.startswith('-A ')]
assert len(oldrules)==3 and all('REDIRECT' in line for line in oldrules),'unexpected live WG rules'
assert source.count(b'-j REDIRECT --to-ports ')==3,'unexpected persisted WG rules'
updated=source.replace(b'-j REDIRECT --to-ports ',b'-j DNAT --to-destination 10.210.0.4:')
backup=Path('/var/lib/threehub/mesh-reboot-network.sh')
assert not backup.exists(),'backup already exists'
backup.write_bytes(source);os.chmod(backup,0o600)
before=run('wg','show','all','latest-handshakes')
def install(data):
 path.write_bytes(data);os.chown(path,info.st_uid,info.st_gid);os.chmod(path,info.st_mode&0o777)
try:
 install(updated)
 for command in [['iptables', '-t', 'nat', '-R', 'TH_WG_IN', '1', '-i', 'eth0', '-p', 'udp', '-s', '10.220.0.4/32', '-d', '10.210.0.4/32', '--dport', '51820', '-j', 'DNAT', '--to-destination', '10.210.0.4:51821'], ['iptables', '-t', 'nat', '-R', 'TH_WG_IN', '2', '-i', 'eth0', '-p', 'udp', '-s', '10.130.0.4/32', '-d', '10.210.0.4/32', '--dport', '51820', '-j', 'DNAT', '--to-destination', '10.210.0.4:51822'], ['iptables', '-t', 'nat', '-R', 'TH_WG_IN', '3', '-i', 'eth0', '-p', 'udp', '-s', '10.140.0.4/32', '-d', '10.210.0.4/32', '--dport', '51820', '-j', 'DNAT', '--to-destination', '10.210.0.4:51823']]: run(*command)
 deadline=time.monotonic()+85
 while True:
  latest=run('wg','show','all','latest-handshakes')
  if len(latest.splitlines())==3 and all(int(line.split()[-1])>0 for line in latest.splitlines()): break
  if time.monotonic()>=deadline: raise RuntimeError('WireGuard acceptance deadline')
  time.sleep(5)
 assert bird_identity()==expected,'BIRD original mismatch after repair'
except Exception:
 install(source)
 os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns))
 for index,rule in enumerate(oldrules,1):
  run('iptables','-t','nat','-R','TH_WG_IN',str(index),*rule[2:])
 print('MESH_REPAIR '+json.dumps(dict(site='eu',state='rolled-back')))
 raise
print('MESH_REPAIR '+json.dumps(dict(site='eu',state='applied',before=before,after=latest,sourceBeforeSha256=hashlib.sha256(source).hexdigest(),sourceAfterSha256=hashlib.sha256(updated).hexdigest(),bird=bird_identity()),separators=(',',':')))
PY
