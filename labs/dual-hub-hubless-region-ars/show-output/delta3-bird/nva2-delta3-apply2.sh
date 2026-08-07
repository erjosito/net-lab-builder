#!/bin/bash
echo BACKUP
cp /etc/bird/bird.conf /etc/bird/bird.conf.pre-delta3
echo PATCH
python3 -c '
import re
c=open("/etc/bird/bird.conf").read()
old="filter export_to_poland_ars {\n  accept;\n}"
new="filter export_to_poland_ars {\n  if net = 0.0.0.0/0 then {\n    bgp_path.prepend(65002);\n    bgp_path.prepend(65002);\n  }\n  accept;\n}"
if old in c:
    open("/etc/bird/bird.conf","w").write(c.replace(old,new)); print("PATCH_OK")
else:
    print("NOT_FOUND_TRYING_ALT")
    old2=re.compile(r"filter export_to_poland_ars \{[^}]*\}",re.DOTALL)
    m=old2.search(c)
    if m: print("FOUND_EXISTING: "+repr(m.group()))
    import sys; sys.exit(1)
'
PATCH_RC=$?
echo PATCH_EXIT=$PATCH_RC
if [ $PATCH_RC -ne 0 ]; then cp /etc/bird/bird.conf.pre-delta3 /etc/bird/bird.conf; echo ROLLBACK; exit 1; fi
echo VERIFY
grep -A 8 "filter export_to_poland_ars" /etc/bird/bird.conf
echo SYNTAX
birdc configure check 2>&1
SYNTAX_RC=$?
echo SYNTAX_EXIT=$SYNTAX_RC
if [ $SYNTAX_RC -ne 0 ]; then cp /etc/bird/bird.conf.pre-delta3 /etc/bird/bird.conf; echo ROLLBACK; exit 1; fi
echo RECONFIGURE
birdc configure 2>&1
sleep 20
echo SESSIONS
birdc show protocols
echo ROUTES
birdc show route count
echo DONE