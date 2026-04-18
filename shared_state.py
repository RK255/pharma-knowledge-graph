#!/usr/bin/env python3
"""
Shared state module for pipeline coordination.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# State file location
STATE_DIR = Path(__file__).parent.parent.parent / "data" / "grc20_v2"
STATE_FILE = STATE_DIR / "pipeline_state.json"


def ensure_state_dir():
    """Ensure state directory exists."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_state() -> Dict[str, Any]:
    """Load the pipeline state."""
    if STATE_FILE.exists() and STATE_FILE.stat().st_size > 0:
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


def save_state(state: Dict[str, Any]):
    """Save the pipeline state."""
    ensure_state_dir()
    state["last_updated"] = datetime.now().isoformat()
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def save_source_selection(step_name: str, source_path: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
    """Save the selected source file for a pipeline step."""
    try:
        state = load_state()
        if "source_selections" not in state:
            state["source_selections"] = {}
        state["source_selections"][step_name] = {
            "path": str(source_path),
            "selected_at": datetime.now().isoformat(),
        }
        if metadata:
            state["source_selections"][step_name].update(metadata)
        save_state(state)
        return True
    except Exception as e:
        print(f"Error saving source selection: {e}")
        return False


def load_source_selection(step_name: str) -> Optional[Dict[str, Any]]:
    """Load the selected source file for a pipeline step."""
    try:
        state = load_state()
        selections = state.get("source_selections", {})
        return selections.get(step_name)
    except Exception as e:
        print(f"Error loading source selection: {e}")
        return None
