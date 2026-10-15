#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import subprocess,json,socket,struct
def attrs(data):
 out={}
 while len(data)>=4:
  n,t=struct.unpack_from('HH',data)
  if n<4: break
  out[t&0x3fff]=data[4:n]
  data=data[(n+3)&~3:]
 return out
def tuple4(data):
 a=attrs(data); ip=attrs(a.get(1,b'')); p=attrs(a.get(2,b''))
 return [socket.inet_ntoa(ip.get(1,bytes(4))),int.from_bytes(p.get(2,b''),'big'),socket.inet_ntoa(ip.get(2,bytes(4))),int.from_bytes(p.get(3,b''),'big')]
s=socket.socket(socket.AF_NETLINK,socket.SOCK_RAW,12);s.settimeout(3);s.bind((0,0))
s.send(struct.pack('IHHII',20,0x101,0x301,1,0)+struct.pack('BBH',socket.AF_INET,0,0))
flows=[];done=False
while not done:
 b=s.recv(65536)
 while len(b)>=16:
  n,t,_,_,_=struct.unpack_from('IHHII',b)
  if t in (2,3): done=True;break
  a=attrs(b[20:n]);orig=tuple4(a.get(1,b''));reply=tuple4(a.get(2,b''))
  if any(51820<=p<=51826 for p in (orig[1],orig[3],reply[1],reply[3])):
   flows.append(dict(orig=orig,reply=reply,status=int.from_bytes(a.get(3,b''),'big')))
  b=b[(n+3)&~3:]
def run(*args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=15);return (p.stdout+p.stderr).strip()
d={'flows':flows,'rpFilter':run('sh','-c','grep . /proc/sys/net/ipv4/conf/*/rp_filter'),'allNat':run('iptables','-t','nat','-S'),'raw':run('iptables','-t','raw','-S')}
print('MESH_DIAGNOSTIC '+json.dumps(d,separators=(',',':')))
PY
