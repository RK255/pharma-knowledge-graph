#!/usr/bin/env python3
"""
Fix RxNorm relation direction in the converter.
The RXNREL.RRF file stores relationships with RELA describing RXCUI2 -> RXCUI1,
not RXCUI1 -> RXCUI2 as we were assuming.
"""

import re

file_path = 'scripts/production/pipeline/02_rxnorm/01_rxnorm_to_grc20.py'

with open(file_path, 'r') as f:
    content = f.read()

# Find and fix the source/target assignment
# Current (WRONG):
#     source_rxcui = fields[0]
#     target_rxcui = fields[4]
# Fixed:
#     source_rxcui = fields[4]  # RXCUI2 - RELA describes relationship FROM RXCUI2
#     target_rxcui = fields[0]  # RXCUI1 - TO RXCUI1

old_pattern = r'''(source_rxcui = fields$$)0($$
\s+target_rxcui = fields$$)4($$)'''

new_pattern = r'''\g<1>4\g<2>0\g<3>'''

# Check current state
if 'source_rxcui = fields[0]' in content and 'target_rxcui = fields[4]' in content:
    print("Found current (wrong) direction. Fixing...")
    content = re.sub(old_pattern, new_pattern, content)
    
    # Add comment explaining the fix
    content = content.replace(
        'source_rxcui = fields[4]',
        'source_rxcui = fields[4]  # RXCUI2 - RELA describes RXCUI2 -> RXCUI1'
    )
    content = content.replace(
        'target_rxcui = fields[0]',
        'target_rxcui = fields[0]  # RXCUI1 (see RxNorm docs)'
    )
    
    with open(file_path, 'w') as f:
        f.write(content)
    print("✅ Fixed relation direction in 01_rxnorm_to_grc20.py")
else:
    print("⚠️ Pattern not found or already fixed")
    # Show what we have
    for i, line in enumerate(content.split('\n')):
        if 'source_rxcui' in line or 'target_rxcui' in line:
            print(f"Line {i+1}: {line}")
