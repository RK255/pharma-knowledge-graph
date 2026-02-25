#!/usr/bin/env python3
"""
Pharmaceutical Knowledge Graph - Master Pipeline Runner
========================================================
Orchestrates all data ingestion and enrichment steps.

Usage:
    python run_pipeline.py --step 01  # Run specific step
    python run_pipeline.py --all      # Run all steps
    python run_pipeline.py --status   # Show pipeline status
"""

import os
import sys
import subprocess
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent

PIPELINE_STEPS = {
    "01": {"name": "Dailymed Parser", "script": "01_dailymed/dailymed_parser_v21.py"},
    "02": {"name": "RxNorm Loader", "script": "02_rxnorm/load_rxnorm.py"},
    "03": {"name": "NDC Bridge", "script": "03_ndc_bridge/ndc_bridge.py"},
    "04": {"name": "PubChem Enrichment", "script": "04_pubchem/enrich_pubchem.py"},
    "05": {"name": "Data Enrichment", "script": "05_enrichment/enrich.py"},
    "06": {"name": "Graph Loaders", "script": "06_loaders/load_to_neo4j.py"},
    "07": {"name": "API Backend", "script": "07_api/main_v3_hybrid_v2.py"},
    "08": {"name": "Clinical Weights", "script": "08_clinical_weights/init_weights.py"},
    "09": {"name": "Drug Interactions", "script": "09_drug_interactions/extract_interactions.py"},
    "10": {"name": "Pharmacological Classes", "script": "10_pharmacological_classes/build_pharma_classes.py"},
}

def show_status():
    """Show pipeline status."""
    print("=" * 60)
    print("PIPELINE STATUS")
    print("=" * 60)
    for step, info in PIPELINE_STEPS.items():
        script_path = PIPELINE_DIR / info["script"]
        status = "✅ EXISTS" if script_path.exists() else "❌ MISSING"
        print(f"  {step}: {info['name']:<30} {status}")
    print("=" * 60)

def run_step(step):
    """Run a specific pipeline step."""
    if step not in PIPELINE_STEPS:
        print(f"❌ Unknown step: {step}")
        return False
    
    info = PIPELINE_STEPS[step]
    script_path = PIPELINE_DIR / info["script"]
    
    if not script_path.exists():
        print(f"❌ Script not found: {script_path}")
        return False
    
    print(f"\n{'='*60}")
    print(f"STEP {step}: {info['name']}")
    print(f"{'='*60}")
    
    result = subprocess.run([sys.executable, str(script_path)], cwd=str(PIPELINE_DIR))
    return result.returncode == 0

def run_all():
    """Run all pipeline steps."""
    for step in PIPELINE_STEPS:
        if not run_step(step):
            print(f"\n❌ Pipeline stopped at step {step}")
            return False
    print("\n✅ All pipeline steps completed!")
    return True

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pharma Knowledge Graph Pipeline")
    parser.add_argument("--step", help="Run specific step (01-10)")
    parser.add_argument("--all", action="store_true", help="Run all steps")
    parser.add_argument("--status", action="store_true", help="Show pipeline status")
    
    args = parser.parse_args()
    
    if args.status:
        show_status()
    elif args.all:
        run_all()
    elif args.step:
        run_step(args.step)
    else:
        parser.print_help()
