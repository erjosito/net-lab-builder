#!/bin/bash
echo "=== PHASE 1: BACKUP ==="
cp /etc/bird/bird.conf /etc/bird/bird.conf.pre-delta3
echo "Backup created: /etc/bird/bird.conf.pre-delta3"

echo ""
echo "=== PHASE 2: CURRENT export_to_poland_ars FILTER ==="
grep -A 5 "filter export_to_poland_ars" /etc/bird/bird.conf

echo ""
echo "=== PHASE 3: APPLY DELTA3 PATCH ==="
python3 << 'PYEOF'
import re

with open('/etc/bird/bird.conf', 'r') as f:
    content = f.read()

# Target: replace export_to_poland_ars filter body (accept-only) with prepend + accept
# Handle both 2-space and 4-space (or any) indentation via regex
old_pattern = r'(filter export_to_poland_ars \{)\s*\n(\s*)accept;\s*\n(\s*\})'
new_content = r'''\1
\2if net = 0.0.0.0/0 then {
\2  bgp_path.prepend(65002);
\2  bgp_path.prepend(65002);
\2}
\2accept;
\3'''

result, count = re.subn(old_pattern, new_content, content)
if count == 1:
    with open('/etc/bird/bird.conf', 'w') as f:
        f.write(result)
    print('PATCH_OK: export_to_poland_ars filter updated (count=1)')
else:
    print(f'PATCH_FAIL: found {count} matches for filter pattern. No change made.')
    import sys; sys.exit(1)
PYEOF
PATCH_RC=$?

echo ""
echo "=== PHASE 4: VERIFY PATCH ==="
grep -A 10 "filter export_to_poland_ars" /etc/bird/bird.conf

if [ $PATCH_RC -ne 0 ]; then
    echo "PATCH_FAILED — rolling back"
    cp /etc/bird/bird.conf.pre-delta3 /etc/bird/bird.conf
    echo "ROLLBACK_DONE"
    exit 1
fi

echo ""
echo "=== PHASE 5: SYNTAX CHECK ==="
birdc configure check 2>&1
SYNTAX_RC=$?
echo "Syntax check exit: $SYNTAX_RC"

if [ $SYNTAX_RC -ne 0 ]; then
    echo "SYNTAX_ERROR — rolling back"
    cp /etc/bird/bird.conf.pre-delta3 /etc/bird/bird.conf
    echo "ROLLBACK_DONE"
    exit 1
fi

echo ""
echo "=== PHASE 6: APPLY VIA birdc configure ==="
birdc configure 2>&1
RELOAD_RC=$?
echo "birdc configure exit: $RELOAD_RC"

echo ""
echo "=== PHASE 7: VERIFY SESSIONS (15s after reload) ==="
sleep 15
birdc show protocols

echo ""
echo "=== PHASE 8: VERIFY ROUTE COUNT ==="
birdc show route count

echo ""
echo "=== STATUS: COMPLETE ==="