#!/bin/bash
while true; do
    clear
    echo "========================================"
    echo "  DRUG INTERACTION EXTRACTION MONITOR"
    echo "========================================"
    date
    echo ""
    
    # Check process
    if ps aux | grep -q "[e]xtract_interactions_v7"; then
        echo "✓ Process RUNNING"
    else
        echo "✗ Process STOPPED"
    fi
    echo ""
    
    # Get stats from manifest
    python3 << 'PYEOF'
import json
from pathlib import Path
from datetime import datetime
import os

manifest_path = Path('/mnt/fast_raid/server_projects/Geo/graph_workshop/data/interactions/extraction_manifest.json')
interactions_path = Path('/mnt/fast_raid/server_projects/Geo/graph_workshop/data/interactions/interactions_structured.json')

if manifest_path.exists():
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
    
    processed = len(manifest.get('processed_set_ids', {}))
    stats = manifest.get('stats', {})
    total_interactions = stats.get('total_interactions', 0)
    with_interactions = stats.get('with_interactions', 0)
    updated = manifest.get('updated_at', '')
    
    print(f"Processed drugs: {processed:,}")
    print(f"Drugs with interactions: {with_interactions:,}" if with_interactions else "")
    print(f"Total interactions: {total_interactions:,}")
    print(f"Last update: {updated}")
    
    # Progress
    estimated_total = 32000
    pct = (processed / estimated_total) * 100
    bar_len = 30
    filled = int(bar_len * pct / 100)
    bar = '█' * filled + '░' * (bar_len - filled)
    print(f"\nProgress: [{bar}] {pct:.1f}%")
    
    # File size
    if interactions_path.exists():
        size = os.path.getsize(interactions_path) / 1024 / 1024
        print(f"Output file: {size:.1f} MB")
else:
    print("Manifest not found")
PYEOF
    
    echo ""
    echo "Press Ctrl+C to stop monitoring"
    sleep 10
done
