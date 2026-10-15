#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import datetime,hashlib,json,pathlib,re,subprocess,time
data = {'site': 'us', 'links': [{'peer': 'eu', 'interface': 'wgeuus', 'local': '172.31.0.2', 'remote': '172.31.0.1', 'port': 51821}, {'peer': 'jp', 'interface': 'wgusjp', 'local': '172.31.0.13', 'remote': '172.31.0.14', 'port': 51824}, {'peer': 'cn', 'interface': 'wguscn', 'local': '172.31.0.17', 'remote': '172.31.0.18', 'port': 51825}], 'ips': {'eu': '10.210.0.4', 'us': '10.220.0.4', 'jp': '10.130.0.4', 'cn': '10.140.0.4'}}
def run(args):
 p=subprocess.run(args,text=True,capture_output=True,timeout=15)
 if p.returncode: raise RuntimeError(args[0]+": "+p.stderr)
 return p.stdout
p=pathlib.Path('/etc/bird/bird.conf');s=p.stat()
identity=dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),stat=dict(uid=s.st_uid,gid=s.st_gid,mode=s.st_mode&0o777,mtimeNs=s.st_mtime_ns))
protocols={}
for line in run(['birdc','show','protocols']).splitlines():
 fields=line.split()
 if fields and re.match(r'^(mesh_|azure_)',fields[0]):
  protocols[fields[0]]=dict(state=fields[3],since=fields[4],info=fields[5] if len(fields)>5 else '')
exports={}
if data['site'] in ('eu','us','jp'):
 for peer in ('azure_0','azure_1'):
  text=run(['birdc','show','route','export',peer,'all'])
  routes={};prefix=None
  for line in text.splitlines():
   match=re.match(r'(10\.\d+\.0\.0/24)\s',line)
   if match: prefix=match.group(1);routes[prefix]=[]
   if prefix and 'BGP.as_path:' in line:
    routes[prefix]=[int(x) for x in line.split('BGP.as_path:',1)[1].split()]
  exports[peer]=routes
rules=run(['ip','rule','show'])
table=run(['ip','route','show','table','100'])
wg={}
for link in data['links']:
 iface=link['interface']
 endpoints=run(['wg','show',iface,'endpoints']).split()
 handshakes=run(['wg','show',iface,'latest-handshakes']).split()
 target=data['ips'][link['peer']]
 wg[iface]=dict(peerPublicId=endpoints[0],endpoint=endpoints[1],
  listenPort=int(run(['wg','show',iface,'listen-port']).strip()),
  fwmark=run(['wg','show',iface,'fwmark']).strip(),
  latestHandshake=int(handshakes[1]),
  markedRoute=run(['ip','route','get',target,'mark','0x200']).strip(),
  expectedPeer=target,expectedPort=link['port'])
ike=None;children=None
if data['site']=='jp':
 sas=run(['swanctl','--list-sas'])
 ike=len(re.findall(r'^\S.*\bESTABLISHED\b',sas,re.M))
 children=len(re.findall(r'^\s+\S.*\bINSTALLED\b',sas,re.M))
result=dict(site=data['site'],now=int(time.time()),utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 bird=identity,protocols=protocols,exports=exports,rules=rules,table100=table,wg=wg,
 natTranslationPresent='TH_WG_' in run(['iptables-save','-t','nat']),
 ordinaryCnRoute=run(['ip','route','get','10.140.0.4']).strip(),
 ikeEstablished=ike,childInstalled=children)
print('RESTORED_MESH_VERIFICATION_COMPLETE '+json.dumps(result,separators=(',',':')))
PY
