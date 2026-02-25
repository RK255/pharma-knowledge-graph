#!/usr/bin/env python3
"""Quick status check for extraction progress."""
import json
from pathlib import Path
from datetime import datetime

manifest_path = Path('/mnt/fast_raid/server_projects/Geo/graph_workshop/data/interactions/extraction_manifest.json')

if manifest_path.exists():
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
    
    stats = manifest.get('stats', {})
    processed = len(manifest.get('processed_set_ids', {}))
    
    total_files = 53786
    estimated_with_interactions = int(total_files * 0.6)
    progress_pct = (processed / estimated_with_interactions) * 100 if estimated_with_interactions > 0 else 0
    
    # Estimate time remaining
    created = datetime.fromisoformat(manifest.get('created_at', datetime.now().isoformat()))
    updated = datetime.fromisoformat(manifest.get('updated_at', datetime.now().isoformat()))
    elapsed = (updated - created).total_seconds()
    
    if processed > 0 and elapsed > 0:
        rate = processed / (elapsed / 60)  # files per minute
        remaining_files = estimated_with_interactions - processed
        eta_minutes = remaining_files / rate if rate > 0 else 0
        
        print("=" * 50)
        print("  DRUG INTERACTION EXTRACTION STATUS")
        print("=" * 50)
        print(f"  Files processed: {processed:,} / ~{estimated_with_interactions:,} ({progress_pct:.1f}%)")
        print(f"  Interactions extracted: {stats.get('total_interactions', 0):,}")
        print(f"  Rate: {rate:.1f} files/min")
        print(f"  ETA: {eta_minutes/60:.1f} hours remaining")
        print("=" * 50)
        
        # Last 5 drugs
        recent = list(manifest.get('processed_set_ids', {}).items())[-5:]
        print(f"\nLast 5 processed:")
        for set_id, info in recent:
            print(f"  • {info['drug_name'][:35]:35} → {info['interactions_count']} interactions")
    else:
        print("Extraction just started...")
else:
    print("Manifest not found - extraction not started")
