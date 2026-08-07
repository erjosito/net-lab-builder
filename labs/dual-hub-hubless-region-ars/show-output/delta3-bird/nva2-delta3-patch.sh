#!/bin/bash
set -e

# Step 1: Backup current config
cp /etc/bird/bird.conf /etc/bird/bird.conf.pre-delta3
echo "=== PRE-DELTA3 BACKUP ==="
cat /etc/bird/bird.conf

# Step 2: Replace the export_to_poland_ars filter
# Current:
#   filter export_to_poland_ars {
#     accept;
#   }
# Target:
#   filter export_to_poland_ars {
#     if net = 0.0.0.0/0 then {
#       bgp_path.prepend(65002);
#       bgp_path.prepend(65002);
#     }
#     accept;
#   }

python3 -c "
import re, sys

with open('/etc/bird/bird.conf', 'r') as f:
    content = f.read()

old_filter = '''filter export_to_poland_ars {
        accept;
      }'''

new_filter = '''filter export_to_poland_ars {
        if net = 0.0.0.0/0 then {
          bgp_path.prepend(65002);
          bgp_path.prepend(65002);
        }
        accept;
      }'''

if old_filter in content:
    content = content.replace(old_filter, new_filter)
    with open('/etc/bird/bird.conf', 'w') as f:
        f.write(content)
    print('PATCH_APPLIED: filter replaced successfully')
else:
    # Try alternate whitespace (operational fixes may have changed indentation)
    old_filter2 = 'filter export_to_poland_ars {\n  accept;\n}'
    new_filter2 = 'filter export_to_poland_ars {\n  if net = 0.0.0.0/0 then {\n    bgp_path.prepend(65002);\n    bgp_path.prepend(65002);\n  }\n  accept;\n}'
    if old_filter2 in content:
        content = content.replace(old_filter2, new_filter2)
        with open('/etc/bird/bird.conf', 'w') as f:
            f.write(content)
        print('PATCH_APPLIED: filter replaced (alt indent)')
    else:
        print('PATCH_FAILED: filter not found in expected form')
        import sys; sys.exit(1)
"

echo "=== POST-PATCH CONFIG ==="
cat /etc/bird/bird.conf

# Step 3: Validate BIRD syntax BEFORE reload
echo "=== SYNTAX CHECK ==="
birdc configure check 2>&1
SYNTAX_RC=$?
echo "Syntax check exit: $SYNTAX_RC"

if [ $SYNTAX_RC -ne 0 ]; then
    echo "SYNTAX_ERROR: Rolling back to pre-delta3 config"
    cp /etc/bird/bird.conf.pre-delta3 /etc/bird/bird.conf
    echo "ROLLBACK_DONE"
    exit 1
fi

echo "SYNTAX_OK"