"""
Clinical Weights Admin System
==============================
JSON-backed weight storage with API for CRUD operations.
"""

import json
import os
from datetime import datetime
from typing import Dict, Optional, List, Tuple
import hashlib

WEIGHTS_FILE = "/mnt/fast_raid/server_projects/Geo/graph_workshop/pharma-backend/clinical_weights.json"

DEFAULT_CURATOR = {
    "name": "Kevin G",
    "credentials": "PharmD",
    "license": "WA DOH RPH License #PH61629288",
    "experience": "20+ years clinical pharmacy practice",
    "specialization": "Ambulatory care, chronic disease management"
}

def compute_curator_hash(curator: Dict) -> str:
    data = f"{curator['name']}|{curator['credentials']}|{curator['license']}|{datetime.now().strftime('%Y-%m-%d')}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]

def load_weights() -> Dict:
    if os.path.exists(WEIGHTS_FILE):
        with open(WEIGHTS_FILE, 'r') as f:
            return json.load(f)
    return {
        "version": "1.0",
        "last_updated": datetime.now().isoformat(),
        "curator": DEFAULT_CURATOR,
        "curator_hash": compute_curator_hash(DEFAULT_CURATOR),
        "disease_states": {
            "hyperlipidemia": {"name": "Hyperlipidemia", "description": "Elevated cholesterol", "first_line": "Statins", "guidelines": "ACC/AHA 2018"},
            "cv_risk_reduction": {"name": "CV Risk Reduction", "description": "Secondary prevention", "first_line": "High-intensity statins", "guidelines": "ACC/AHA 2018"},
            "hypertriglyceridemia": {"name": "Hypertriglyceridemia", "description": "Elevated TG", "first_line": "Fibrates", "guidelines": "ACC/AHA 2018"},
            "statin_intolerance": {"name": "Statin Intolerance", "description": "Cannot tolerate statins", "first_line": "Ezetimibe", "guidelines": "NLA 2018"}
        },
        "drugs": {}
    }

def save_weights(data: Dict) -> None:
    data["last_updated"] = datetime.now().isoformat()
    data["curator_hash"] = compute_curator_hash(data.get("curator", DEFAULT_CURATOR))
    with open(WEIGHTS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_all_drugs() -> List[str]:
    data = load_weights()
    return list(data.get("drugs", {}).keys())

def get_drug_weight(drug_name: str) -> Optional[Dict]:
    data = load_weights()
    return data.get("drugs", {}).get(drug_name.lower())

def set_drug_weight(drug_name: str, weight_data: Dict) -> Dict:
    data = load_weights()
    drug_key = drug_name.lower()
    if "default" not in weight_data:
        weight_data["default"] = {"weight": 50, "rationale": "Default weight"}
    data["drugs"][drug_key] = weight_data
    save_weights(data)
    return data["drugs"][drug_key]

def delete_drug_weight(drug_name: str) -> bool:
    data = load_weights()
    drug_key = drug_name.lower()
    if drug_key in data["drugs"]:
        del data["drugs"][drug_key]
        save_weights(data)
        return True
    return False

def get_weight(drug_name: str, indication: str = None) -> Tuple[int, str, Optional[str], Optional[str]]:
    data = load_weights()
    drug = data.get("drugs", {}).get(drug_name.lower())
    if not drug:
        return (None, None, None, None)
    if indication and indication in drug.get("indications", {}):
        ind_data = drug["indications"][indication]
        return (ind_data["weight"], f"expert:{indication}", ind_data.get("rationale"), drug["default"].get("evidence"))
    default = drug.get("default", {})
    return (default.get("weight"), "expert", default.get("rationale"), default.get("evidence"))

def get_combined_weight(drug_name: str, class_size: int, indication: str = None) -> Tuple[int, str, Optional[str], Optional[str], Optional[str]]:
    weight, source, rationale, evidence = get_weight(drug_name, indication)
    if weight is not None:
        data = load_weights()
        drug = data.get("drugs", {}).get(drug_name.lower(), {})
        return (weight, source, rationale, evidence, drug.get("clinical_note"))
    if class_size <= 15:
        return (90, "auto", None, None, None)
    elif class_size <= 50:
        return (66, "auto", None, None, None)
    else:
        return (33, "auto", None, None, None)

def weight_to_priority(weight: int) -> str:
    if weight >= 90:
        return "PRIMARY"
    elif weight >= 60:
        return "SECONDARY"
    elif weight >= 30:
        return "TERTIARY"
    else:
        return "CAUTION"

def get_weight_provenance(drug_name: str, indication: str = None) -> Optional[Dict]:
    data = load_weights()
    drug = data.get("drugs", {}).get(drug_name.lower())
    if not drug:
        return None
    weight_data = drug.get("default", {})
    indication_info = None
    if indication and indication in drug.get("indications", {}):
        indication_info = drug["indications"][indication]
        weight_data = {"weight": indication_info["weight"], "rationale": indication_info.get("rationale"), "evidence": drug["default"].get("evidence")}
    return {
        "ingredient": drug_name.lower(),
        "weight": weight_data.get("weight"),
        "rationale": weight_data.get("rationale"),
        "evidence": weight_data.get("evidence"),
        "indication": indication,
        "clinical_note": drug.get("clinical_note"),
        "drug_class": drug.get("drug_class"),
        "curator": data.get("curator", DEFAULT_CURATOR),
        "curator_hash": data.get("curator_hash"),
        "last_updated": data.get("last_updated"),
    }

def get_curator_info() -> Dict:
    data = load_weights()
    return data.get("curator", DEFAULT_CURATOR)

def set_curator_info(curator: Dict) -> Dict:
    data = load_weights()
    data["curator"] = curator
    save_weights(data)
    return data["curator"]

def get_disease_states() -> Dict:
    data = load_weights()
    return data.get("disease_states", {})

def add_disease_state(key: str, info: Dict) -> Dict:
    data = load_weights()
    data["disease_states"][key] = info
    save_weights(data)
    return data["disease_states"][key]
