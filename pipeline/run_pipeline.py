#!/usr/bin/env python3
"""
GRC-20 Pipeline Orchestrator

Runs the complete RxNorm → GRC-20 pipeline with clean progress output.

Usage:
    python run_pipeline.py              # Interactive mode with progress bars
    python run_pipeline.py --debug      # Show raw output from each step
    python run_pipeline.py --auto       # Use defaults, no prompts
    python run_pipeline.py --step 3     # Run only step 3

Steps:
    1. RxNorm to GRC-20       - Parse RxNorm files, create entities/relations
    2. NDC Extraction         - Extract NDC codes from RXNSAT
    3. NDC Bridge             - Link NDCs to RxNorm entities
    4. PubChem CID Matching   - Match ingredients to PubChem CIDs
    5. PubChem Properties     - Fetch properties from PubChem
    6. Merge & Enrich         - Combine all into grc20_merged.json
"""

import os
import sys
import json
import subprocess
import argparse
from datetime import datetime
from pathlib import Path

# Pipeline configuration
PIPELINE_DIR = Path(__file__).parent
DATA_DIR = PIPELINE_DIR.parent.parent.parent / "data" / "grc20_v2"
RAW_DATA_DIR = PIPELINE_DIR.parent.parent.parent / "data" / "raw_data"
STATE_FILE = DATA_DIR / "pipeline_state.json"

STEPS = [
    {
        "num": 1,
        "name": "RxNorm to GRC-20",
        "script": "02_rxnorm/01_rxnorm_to_grc20.py",
        "output": "rxnorm_entities.json",
        "interactive": True,
    },
    {
        "num": 2,
        "name": "NDC Extraction",
        "script": "03_ndc_bridge/01_extract_ndcs.py",
        "output": "ndc_to_rxcui.json",
        "interactive": False,
    },
    {
        "num": 3,
        "name": "NDC Bridge",
        "script": "03_ndc_bridge/02_ndc_bridge_to_grc20.py",
        "output": "ndc_bridge_entities.json",
        "interactive": False,
    },
    {
        "num": 4,
        "name": "PubChem CID Matching",
        "script": "04_pubchem/01_enrich_by_cid.py",
        "output": "pubchem_cid_mapping.json",
        "interactive": False,
    },
    {
        "num": 5,
        "name": "PubChem Properties",
        "script": "04_pubchem/02_fetch_properties.py",
        "output": "pubchem_properties.json",
        "interactive": True,
    },
    {
        "num": 6,
        "name": "Merge & Enrich",
        "script": "05_triple_converter/01_merge_enrich.py",
        "output": "grc20_merged.json",
        "interactive": False,
    },
]


class PipelineRunner:
    def __init__(self, debug: bool = False, auto: bool = False, step: int = None):
        self.debug = debug
        self.auto = auto
        self.single_step = step
        self.state = self.load_state()
        
    def load_state(self) -> dict:
        """Load pipeline state from file."""
        if STATE_FILE.exists():
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        return {
            "source_date": None,
            "source_path": None,
            "completed_steps": [],
            "last_run": None,
        }
    
    def save_state(self):
        """Save pipeline state to file."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.state["last_run"] = datetime.now().isoformat()
        with open(STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def print_header(self):
        """Print pipeline header."""
        if self.debug:
            return
        
        print()
        print("█" * 70)
        print("█" + " " * 68 + "█")
        print("█" + "  GRC-20 PIPELINE ORCHESTRATOR".center(68) + "█")
        print("█" + " " * 68 + "█")
        print("█" * 70)
        print()
        
        if self.state.get("source_date"):
            print(f"  Source: {self.state['source_date']}")
        if self.state.get("completed_steps"):
            completed = [s["name"] for s in STEPS if s["num"] in self.state["completed_steps"]]
            if completed:
                print(f"  Completed: {', '.join(completed)}")
        print()
    
    def print_progress(self, step: dict, status: str):
        """Print progress for a step."""
        if self.debug:
            return
        
        total = len(STEPS)
        bar_width = 50
        filled = int(bar_width * step["num"] / total)
        bar = "━" * filled + "─" * (bar_width - filled)
        
        # Status icons
        icons = {
            "running": "🔵",
            "done": "✅",
            "error": "❌",
            "skipped": "⏭️",
        }
        
        icon = icons.get(status, "⚪")
        
        print(f"\r  [{step['num']}/{total}] {step['name']} {icon} {bar} ", end="", flush=True)
        
        if status in ("done", "error", "skipped"):
            print()
    
    def print_final(self, success: bool):
        """Print final summary."""
        if self.debug:
            return
        
        print()
        if success:
            output_file = DATA_DIR / "grc20_merged.json"
            if output_file.exists():
                size_mb = output_file.stat().st_size / 1024 / 1024
                print(f"  ✓ Complete: {output_file.name} ({size_mb:.1f} MB)")
            else:
                print("  ✓ Pipeline complete")
        else:
            print("  ✗ Pipeline failed - see errors above")
        print()
    
    def run_step(self, step: dict) -> bool:
        """Run a single pipeline step."""
        script_path = PIPELINE_DIR / step["script"]
        
        if not script_path.exists():
            print(f"\n  ✗ Script not found: {script_path}")
            return False
        
        # Build command
        cmd = [sys.executable, str(script_path)]
        
        # Add auto flag for non-interactive scripts
        if self.auto and not step["interactive"]:
            cmd.append("--auto")
        
        # Add source date for steps that need it (NDC extraction and bridge)
        if self.state.get("source_date") and step["num"] == 2:
            cmd.extend(["--source-date", self.state["source_date"]])
        
        self.print_progress(step, "running")
        
        if self.debug:
            print(f"\n{'='*70}")
            print(f"  RUNNING: {step['script']}")
            print(f"  CMD: {' '.join(cmd)}")
            print("="*70)
        
        try:
            result = subprocess.run(
                cmd,
                cwd=str(PIPELINE_DIR),
                capture_output=not self.debug,
                text=True,
            )
            
            if result.returncode != 0:
                self.print_progress(step, "error")
                if not self.debug and result.stderr:
                    print(f"\n  Error: {result.stderr[:500]}")
                return False
            
            # Update state after successful step
            self.state["completed_steps"].append(step["num"])
            self.save_state()
            
            self.print_progress(step, "done")
            return True
            
        except Exception as e:
            self.print_progress(step, "error")
            print(f"\n  Exception: {e}")
            return False
    
    def update_state_from_output(self, step: dict):
        """Update state based on step output files."""
        output_path = DATA_DIR / step["output"]
        
        if not output_path.exists():
            return
        
        # For step 1, extract source info from rxnorm_entities.json
        if step["num"] == 1 and output_path.exists():
            try:
                with open(output_path, 'r') as f:
                    data = json.load(f)
                if data.get("source_date"):
                    self.state["source_date"] = data["source_date"]
                if data.get("source_file"):
                    self.state["source_path"] = data["source_file"]
                self.save_state()
            except:
                pass
    
    def run(self):
        """Run the pipeline."""
        self.print_header()
        
        steps_to_run = STEPS
        if self.single_step:
            steps_to_run = [s for s in STEPS if s["num"] == self.single_step]
            if not steps_to_run:
                print(f"  ✗ Invalid step number: {self.single_step}")
                return False
        
        success = True
        for step in steps_to_run:
            if not self.run_step(step):
                success = False
                break
            
            # Update state from output
            self.update_state_from_output(step)
        
        self.print_final(success)
        return success


def main():
    parser = argparse.ArgumentParser(
        description="GRC-20 Pipeline Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show raw output from each step",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Use defaults, skip interactive prompts",
    )
    parser.add_argument(
        "--step",
        type=int,
        choices=range(1, 7),
        help="Run only the specified step",
    )
    
    args = parser.parse_args()
    
    runner = PipelineRunner(
        debug=args.debug,
        auto=args.auto,
        step=args.step,
    )
    
    success = runner.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
