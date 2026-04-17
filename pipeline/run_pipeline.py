#!/usr/bin/env python3
"""
GRC-20 Pharmaceutical Knowledge Graph Pipeline Runner

Orchestrates the full pipeline from data sources to final GRC-20 output with provenance.
"""

import sys
import subprocess
from pathlib import Path
import json
import argparse
from datetime import datetime
import os

sys.path.insert(0, str(Path(__file__).parent / "00_schema"))
from pharma_schema import PharmaSchema

# Configuration
BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/production/pipeline")
DATA_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop/data/grc20_v2")
DAILYMED_XML_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop/data/dailymed/xml_only")
RAW_DATA_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data")
CONFIG_FILE = DATA_DIR / "pipeline_config.json"


def run_preflight_menu():
    """Run the interactive preflight configuration menu."""
    print("\n" + "=" * 70)
    print("GRC-20 PIPELINE CONFIGURATION")
    print("=" * 70)
    
    config = {}
    
    # 1. DailyMed Source Selection
    print("\n--- DAILYMED SOURCE SELECTION ---")
    print("  [1] Download and extract latest release")
    print("      - Slower. Fetches latest archive from dailymed-data.nlm.nih.gov")
    print("  [2] Use existing local data (Skip download)")
    print("      - Faster. Uses files in data/dailymed/xml_only/")
    
    choice = input("Select mode [1-2] (default: 2): ").strip()
    if not choice:
        choice = "2"
    
    dailymed_mode = 'download' if choice == '1' else 'existing'
    config['dailymed_mode'] = dailymed_mode
    print(f"Selected: {'Download and extract' if dailymed_mode == 'download' else 'Use existing local data'}")
    
    # 2. RxNorm Source Selection
    print("\n--- RXNORM SOURCE SELECTION ---")
    
    rxnorm_zips = []
    if RAW_DATA_DIR.exists():
        for file in os.listdir(RAW_DATA_DIR):
            if file.startswith("RxNorm") and file.endswith(".zip"):
                rxnorm_zips.append(file)
    
    rxnorm_zips.sort(reverse=True)
    
    if rxnorm_zips:
        print("Available RxNorm releases:")
        for i, zip_file in enumerate(rxnorm_zips, 1):
            print(f"  [{i}] {zip_file}")
        
        rx_choice = input(f"Select source [1-{len(rxnorm_zips)}] (default: 1): ").strip()
        if not rx_choice:
            rx_choice = "1"
        
        try:
            rx_idx = int(rx_choice) - 1
            if 0 <= rx_idx < len(rxnorm_zips):
                selected_rxnorm = rxnorm_zips[rx_idx]
                config['rxnorm_source'] = selected_rxnorm
                print(f"Selected: {selected_rxnorm}")
            else:
                print("Invalid selection, using default.")
                config['rxnorm_source'] = rxnorm_zips[0]
        except ValueError:
            print("Invalid input, using default.")
            config['rxnorm_source'] = rxnorm_zips[0]
    else:
        print("No RxNorm zip files found in raw_data directory.")
        print("Please download RxNorm data first.")
        sys.exit(1)
    
    # 3. Run Mode
    print("\n--- RUN MODE ---")
    print("  [1] Full Run")
    print("      - Processes all available documents.")
    print("      - Recommended for production builds.")
    print("  [2] Limited Run (Test)")
    print("      - Processes a subset of documents.")
    print("      - Useful for testing and development.")
    
    mode_choice = input("Select mode [1-2] (default: 1): ").strip()
    if not mode_choice:
        mode_choice = "1"
    
    run_mode = 'full' if mode_choice == '1' else 'limited'
    config['run_mode'] = run_mode
    print(f"Selected: {'Full Run' if run_mode == 'full' else 'Limited Run (Test)'}")
    
    if run_mode == 'limited':
        limit = input("Enter the number of documents to process (e.g., 100): ").strip()
        try:
            limit = int(limit)
            config['document_limit'] = limit
            print(f"Processing limit set to: {limit}")
        except ValueError:
            print("Invalid limit, using 10.")
            config['document_limit'] = 10
    
    # Save Config
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    
    print("\n✅ Configuration saved to pipeline_config.json")
    print("You can now run the pipeline.")


# Pipeline steps - UPDATED PATHS
STEPS = [
    {
        "num": 1,
        "name": "DailyMed",
        "script": "01_dailymed/dailymed_pipeline.py",
        "args": ["--skip-download", f"--xml-dir={DAILYMED_XML_DIR}", "--no-validate"]
    },
    {
        "num": 2,
        "name": "RxNorm to GRC-20",
        "script": "02_rxnorm/01_rxnorm_to_grc20.py",
        "args": []
    },
    {
        "num": 3,
        "name": "NDC Extraction",
        "script": "03_ndc/01_extract_ndcs.py",
        "args": []
    },
    {
        "num": 4,
        "name": "NDC Bridge to GRC-20",
        "script": "03_ndc/02_ndc_bridge_to_grc20.py",
        "args": []
    },
    {
        "num": 5,
        "name": "PubChem CID Matching",
        "script": "04_pubchem/01_enrich_by_cid.py",
        "args": []
    },
    {
        "num": 6,
        "name": "PubChem Properties",
        "script": "04_pubchem/02_fetch_properties.py",
        "args": ["--properties", "smiles", "inchikey", "iupac_name", "molecular_weight", "pmid"]
    },
    {
        "num": 7,
        "name": "Merge & Enrich",
        "script": "05_merge/01_merge_enrich.py",
        "args": []
    },
    {
        "num": 8,
        "name": "Link PI to RxNorm",
        "script": "05_merge/02_link_pi_to_rxnorm.py",
        "args": []
    },
    {
        "num": 9,
        "name": "Link DailyMed to RxNorm (Set ID)",
        "script": "06_dailymed_link/01_link_dailymed_to_rxnorm_by_setid.py",
        "args": [],
        "description": "Links PackageInserts to RxNorm using SPL Set IDs (primary) and NDC fallback"
    },
    {
        "num": 10,
        "name": "Ensure 100% Provenance",
        "script": "internal",
        "args": []
    },
    {
        "num": 11,
        "name": "Validate All",
        "script": "00_schema/validate_all.py",
        "args": []
    }
]

def run_step(step, limit=None, force=False):
    """Run a single pipeline step."""
    # Handle internal steps (functions defined in this file)
    if step["script"] == "internal":
        if step["name"] == "Ensure 100% Provenance":
            return ensure_provenance_coverage(limit)
        else:
            print(f"  Unknown internal step: {step['name']}")
            return False
    
    script_path = BASE_DIR / step["script"]
    
    # Build command
    cmd = [sys.executable, str(script_path)]
    
    # Add step-specific arguments
    cmd.extend(step["args"])
    
    # Add limit if supported
    if limit is not None:
        if step["num"] == 1:  # DailyMed
            cmd.extend(["--limit", str(limit)])
    
    # Run
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    
    return result.returncode == 0

def ensure_provenance_coverage(limit=None):
    """Ensure 100% provenance coverage on the final output."""
    print("\n" + "="*80)
    print("ENSURING 100% PROVENANCE COVERAGE")
    print("="*80 + "\n")
    
    from provenance_manager import ProvenanceManager
    
    pm = ProvenanceManager()
    
    # Load merged entities and relations (JSONL format)
    entities_file = DATA_DIR / "grc20_merged_entities.jsonl"
    relations_file = DATA_DIR / "grc20_merged_relations.jsonl"
    
    if not entities_file.exists():
        print("  ⚠️  No merged entities file found - skipping provenance check")
        return True
    
    print(f"  Loading entities from: {entities_file}")
    print(f"  Loading relations from: {relations_file}")
    
    entities = pm.load_entities_jsonl(str(entities_file))
    relations = pm.load_relations_jsonl(str(relations_file)) if relations_file.exists() else []
    
    # Check coverage
    stats = pm.get_coverage_stats(entities, relations)
    
    print(f"  Total entities: {stats['total_entities']:,}")
    print(f"  Provenance entities: {stats['provenance_entities']}")
    print(f"  Non-provenance entities: {stats['non_provenance_entities']:,}")
    print(f"  With provenance: {stats['with_provenance']:,}")
    print(f"  Without provenance: {stats['without_provenance']:,}")
    print(f"  Current coverage: {stats['coverage']:.1f}%")
    
    # If coverage < 100%, add provenance to missing entities using RxNorm source
    if stats['coverage'] < 100:
        print(f"  ⚠️  Coverage is {stats['coverage']:.1f}%. Fixing missing provenance...")
        
        # Get RxNorm Provenance ID from schema
        from pharma_schema import PharmaSchema
        schema = PharmaSchema()
        rxnorm_prov_id = schema.provenance_entities.get('RxNorm')
        
        if not rxnorm_prov_id:
            print("  ⚠️  Could not find RxNorm Provenance ID. Skipping fix.")
        else:
            entities, relations, added = pm.add_provenance_to_entities(
                entities, relations, rxnorm_prov_id
            )
            print(f"  ✅ Added provenance to {added} entities.")
            
            # Save the updated files
            pm.save_entities_jsonl(entities, str(entities_file))
            pm.save_relations_jsonl(relations, str(relations_file))
            print(f"  ✅ Saved updated entities and relations.")
    return True

def clean_outputs():
    """Clean old output files before fresh run."""
    print("\nCleaning old outputs...")
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Only delete backup files, preserve all data files
    for f in DATA_DIR.glob("*.json"):
        if "backup" in f.name.lower():
            f.unlink()
    
    print("  ✅ Cleanup complete (preserved all data files)")

def main():
    parser = argparse.ArgumentParser(description="GRC-20 Pharmaceutical Pipeline Runner")
    parser.add_argument("--limit", type=int, help="Limit number of documents to process")
    parser.add_argument("--force", action="store_true", help="Force rerun of all steps")
    parser.add_argument("--step", type=int, help="Run only specific step")
    parser.add_argument("--clean", action="store_true", help="Clean outputs before running (only for full runs)")
    parser.add_argument("--configure", action="store_true", help="Run the preflight configuration menu")
    
    args = parser.parse_args()
    
    # Check for configuration or run preflight
    config = None
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
    
    # Check if reconfigure is requested
    if "--configure" in sys.argv:
        run_preflight_menu()
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
    
    # If no config, run preflight
    if not config:
        run_preflight_menu()
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
    
    # Apply config to args
    if 'document_limit' in config and config['document_limit']:
        if not args.limit:
            args.limit = config['document_limit']
    
    # Handle RxNorm source
    if 'rxnorm_source' in config and config['rxnorm_source']:
        for step in STEPS:
            if step['num'] == 2:
                # Pass the zip file to the RxNorm step
                step['args'] = [f"--rxnorm-file={config['rxnorm_source']}"]
            elif step['num'] == 3:
                # Pass the extracted directory to the NDC step
                zip_name = config['rxnorm_source']
                dir_name = zip_name.replace('.zip', '') + '_extracted'
                rxnorm_extracted_dir = RAW_DATA_DIR / "extracted_rrf" / dir_name
                step['args'] = [f"--rxnorm-dir={rxnorm_extracted_dir}"]

    # Handle DailyMed download
    if config.get('dailymed_mode') == 'download' and not args.step:
        print("\n[0/12] DailyMed Download")
        print("-" * 80)
        script_path = BASE_DIR / "01_dailymed/ftp_ripper.py"
        subprocess.run([sys.executable, str(script_path)], check=True)
        print("[OK] Step 0 complete\n")

    print("="*80)
    print("GRC-20 PHARMACEUTICAL KNOWLEDGE GRAPH PIPELINE")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.limit:
        print(f"Limit: {args.limit} documents")
    print()
    
    # Clean outputs only for full runs (not when running specific steps)
    if not args.step and args.clean:
        clean_outputs()
    elif not args.step:
        print("[SKIP] Not cleaning outputs (use --clean to clean)")
    else:
        print(f"[STEP {args.step}] Running specific step without cleaning")
    
    # Run steps
    start_step = args.step if args.step else 1
    end_step = args.step if args.step else len(STEPS)
    
    for step in STEPS[start_step-1:end_step]:
        print(f"\n[{step['num']}/{len(STEPS)}] {step['name']}")
        print("-" * 80)
        
        if step['num'] == 10:  # Provenance step
            success = ensure_provenance_coverage(args.limit)
        else:
            success = run_step(step, args.limit, args.force)
        
        if not success:
            print(f"\n❌ Failed at step {step['num']}: {step['name']}")
            sys.exit(1)
        
        print(f"  ✅ Complete")
    
    # Final summary (only show at end of full pipeline or last step)
    if not args.step or args.step == len(STEPS):  # Last step
        entities_file = DATA_DIR / "grc20_merged_entities.jsonl"
        relations_file = DATA_DIR / "grc20_merged_relations.jsonl"
        
        if entities_file.exists() and relations_file.exists():
            entities_size = entities_file.stat().st_size / (1024 * 1024)
            relations_size = relations_file.stat().st_size / (1024 * 1024)
            total_size = entities_size + relations_size
            
            print(f"\n" + "="*80)
            print("✅ PIPELINE COMPLETE")
            print("="*80)
            print(f"Output Directory: {DATA_DIR}")
            print(f"  Entities: {entities_file.name} ({entities_size:.2f} MB)")
            print(f"  Relations: {relations_file.name} ({relations_size:.2f} MB)")
            print(f"  Total Size: {total_size:.2f} MB")
            print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
