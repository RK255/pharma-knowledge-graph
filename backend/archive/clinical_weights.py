"""
Clinical Expert Weighting System
=================================
PharmD-Curated Drug Recommendations with Full Provenance

Weight Scale: 1-100
  90-100 = PRIMARY (First-line, preferred)
  60-89  = SECONDARY (Alternative, consider after first-line)
  30-59  = TERTIARY (Limited role, specific situations)
  1-29   = CAUTION (Rarely appropriate, significant limitations)

Provenance: Every weight includes:
  - Weight value and rationale
  - Supporting evidence (guidelines, trials)
  - Curator credentials (PharmD, license info)
  - Last review date
"""

import json
import hashlib
from datetime import datetime
from typing import Dict, Optional, List, Tuple

# ============================================================
# CURATOR CREDENTIALS - This is YOUR expertise, tracked
# ============================================================

CURATOR = {
    "name": "Kevin G",
    "credentials": "PharmD",
    "license": "WA DOH RPH License #PH61629288",
    "experience": "20+ years clinical pharmacy practice",
    "specialization": "Ambulatory care, chronic disease management",
    "last_updated": "2024-02-24",
    "review_frequency": "quarterly",
    "provenance_hash": None  # Computed below
}

# Compute provenance hash for curator credentials
def compute_curator_hash():
    data = f"{CURATOR['name']}|{CURATOR['credentials']}|{CURATOR['license']}|{CURATOR['last_updated']}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]

CURATOR["provenance_hash"] = compute_curator_hash()

# ============================================================
# DISEASE STATE PROFILES
# ============================================================

DISEASE_STATES = {
    "hyperlipidemia": {
        "name": "Hyperlipidemia / Dyslipidemia",
        "description": "Elevated cholesterol/lipids requiring treatment",
        "first_line": "Statins",
        "guidelines": "ACC/AHA 2018 Cholesterol Guidelines"
    },
    "cv_risk_reduction": {
        "name": "Cardiovascular Risk Reduction",
        "description": "Secondary prevention in established ASCVD",
        "first_line": "High-intensity statins, PCSK9 inhibitors",
        "guidelines": "ACC/AHA 2018, ESC/EAS 2019"
    },
    "hypertriglyceridemia": {
        "name": "Hypertriglyceridemia",
        "description": "Elevated triglycerides (TG > 500 mg/dL)",
        "first_line": "Fibrates, omega-3 fatty acids",
        "guidelines": "ACC/AHA 2018, Endocrine Society"
    },
    "statin_intolerance": {
        "name": "Statin Intolerance",
        "description": "Patients unable to tolerate statin therapy",
        "first_line": "Ezetimibe, PCSK9 inhibitors, alternate statins",
        "guidelines": "NLA 2018, ACC Consensus"
    }
}

# ============================================================
# MASTER WEIGHT FILE - Full Provenance
# ============================================================

EXPERT_WEIGHTS = {
    # ---------------------------------------------------------
    # STATINS - First line for hyperlipidemia
    # ---------------------------------------------------------
    "atorvastatin": {
        "default": {
            "weight": 100,
            "rationale": "Most potent statin, generic available, extensive outcome data",
            "evidence": "ACC/AHA 2018 Cholesterol Guidelines Class I",
        },
        "indications": {
            "hyperlipidemia": {"weight": 100, "rationale": "First-line for LDL reduction"},
            "cv_risk_reduction": {"weight": 100, "rationale": "High-intensity option, extensive outcomes data"},
            "hypertriglyceridemia": {"weight": 70, "rationale": "Moderate TG reduction, not primary indication"},
            "statin_intolerance": {"weight": 40, "rationale": "May try alternate dosing (every other day)"},
        },
        "clinical_note": "Generic (Lipitor). Most potent LDL reduction.",
        "drug_class": "HMG-CoA Reductase Inhibitor"
    },
    "rosuvastatin": {
        "default": {
            "weight": 100,
            "rationale": "Most potent statin, favorable PK, generic available",
            "evidence": "ACC/AHA 2018 Class I, JUPITER trial",
        },
        "indications": {
            "hyperlipidemia": {"weight": 100, "rationale": "First-line, highest potency"},
            "cv_risk_reduction": {"weight": 100, "rationale": "High-intensity, JUPITER outcomes"},
            "hypertriglyceridemia": {"weight": 70, "rationale": "Moderate TG reduction"},
            "statin_intolerance": {"weight": 40, "rationale": "Try alternate dosing or lower dose"},
        },
        "clinical_note": "Generic (Crestor). Highest potency, fewer interactions.",
        "drug_class": "HMG-CoA Reductase Inhibitor"
    },
    "simvastatin": {
        "default": {
            "weight": 90,
            "rationale": "Good efficacy, generic, CYP3A4 limits dosing",
            "evidence": "ACC/AHA 2018 Class I",
        },
        "indications": {
            "hyperlipidemia": {"weight": 90, "rationale": "First-line, moderate-high intensity"},
            "cv_risk_reduction": {"weight": 85, "rationale": "Moderate intensity limits high-risk use"},
            "hypertriglyceridemia": {"weight": 65, "rationale": "Moderate TG reduction"},
            "statin_intolerance": {"weight": 35, "rationale": "Try alternate dosing"},
        },
        "clinical_note": "Generic. Max 20mg with amiodarone, amlodipine, diltiazem.",
        "drug_class": "HMG-CoA Reductase Inhibitor"
    },
    "pravastatin": {
        "default": {
            "weight": 90,
            "rationale": "Good safety, not CYP3A4 substrate, fewer interactions",
            "evidence": "ACC/AHA 2018 Class I",
        },
        "indications": {
            "hyperlipidemia": {"weight": 90, "rationale": "First-line, good safety profile"},
            "cv_risk_reduction": {"weight": 80, "rationale": "Moderate intensity"},
            "hypertriglyceridemia": {"weight": 65, "rationale": "Moderate TG reduction"},
            "statin_intolerance": {"weight": 50, "rationale": "Try lower dose, good tolerability"},
        },
        "clinical_note": "Generic. Preferred with multiple CYP3A4 substrates.",
        "drug_class": "HMG-CoA Reductase Inhibitor"
    },
    "pitavastatin": {
        "default": {
            "weight": 90,
            "rationale": "Effective statin, minimal CYP interactions, check generic availability",
            "evidence": "ACC/AHA 2018 Class I",
        },
        "indications": {
            "hyperlipidemia": {"weight": 90, "rationale": "First-line statin, good safety"},
            "cv_risk_reduction": {"weight": 85, "rationale": "Moderate-high intensity"},
            "hypertriglyceridemia": {"weight": 65, "rationale": "Moderate TG reduction"},
            "statin_intolerance": {"weight": 55, "rationale": "Minimal interactions, good tolerability"},
        },
        "clinical_note": "Check generic availability. Minimal CYP interactions. Good for polypharmacy.",
        "drug_class": "HMG-CoA Reductase Inhibitor"
    },
    "lovastatin": {
        "default": {
            "weight": 70,
            "rationale": "Older, less potent, inexpensive generic",
            "evidence": "ACC/AHA 2018 Class I",
        },
        "indications": {
            "hyperlipidemia": {"weight": 70, "rationale": "Moderate intensity option"},
            "cv_risk_reduction": {"weight": 60, "rationale": "Limited intensity"},
            "hypertriglyceridemia": {"weight": 50, "rationale": "Modest TG reduction"},
            "statin_intolerance": {"weight": 30, "rationale": "May try alternate dosing"},
        },
        "clinical_note": "Generic. Take with evening meal for absorption.",
        "drug_class": "HMG-CoA Reductase Inhibitor"
    },
    "fluvastatin": {
        "default": {
            "weight": 60,
            "rationale": "Least potent, limited outcome data, good safety",
            "evidence": "ACC/AHA 2018 Class IIa",
        },
        "indications": {
            "hyperlipidemia": {"weight": 60, "rationale": "Lower intensity option"},
            "cv_risk_reduction": {"weight": 50, "rationale": "Limited intensity for high-risk"},
            "hypertriglyceridemia": {"weight": 40, "rationale": "Modest TG reduction"},
            "statin_intolerance": {"weight": 55, "rationale": "Good tolerability profile"},
        },
        "clinical_note": "Generic. Lower potency, for statin-intolerant.",
        "drug_class": "HMG-CoA Reductase Inhibitor"
    },
    
    # ---------------------------------------------------------
    # NON-STATIN LIPID LOWERING
    # ---------------------------------------------------------
    "ezetimibe": {
        "default": {
            "weight": 80,
            "rationale": "Well-tolerated, generic, synergistic with statins",
            "evidence": "IMPROVE-IT, ACC/AHA 2018 Class IIa",
        },
        "indications": {
            "hyperlipidemia": {"weight": 80, "rationale": "Excellent add-on to statins"},
            "cv_risk_reduction": {"weight": 85, "rationale": "IMPROVE-IT showed added benefit"},
            "hypertriglyceridemia": {"weight": 30, "rationale": "Minimal effect on TG"},
            "statin_intolerance": {"weight": 90, "rationale": "First-line non-statin alternative"},
        },
        "clinical_note": "Generic (Zetia). Excellent add-on or statin alternative.",
        "drug_class": "Cholesterol Absorption Inhibitor"
    },
    
    # ---------------------------------------------------------
    # PCSK9 INHIBITORS
    # ---------------------------------------------------------
    "alirocumab": {
        "default": {
            "weight": 75,
            "rationale": "Potent LDL reduction, outcomes data, cost decreased",
            "evidence": "ODYSSEY Outcomes, ACC/AHA Class IIa",
        },
        "indications": {
            "hyperlipidemia": {"weight": 75, "rationale": "For very high LDL or FH"},
            "cv_risk_reduction": {"weight": 85, "rationale": "ODYSSEY outcomes benefit"},
            "hypertriglyceridemia": {"weight": 30, "rationale": "Minimal TG effect"},
            "statin_intolerance": {"weight": 85, "rationale": "Excellent alternative for intolerance"},
        },
        "clinical_note": "Praluent Q2W/Q4W. Cost down, coverage improving.",
        "drug_class": "PCSK9 Inhibitor"
    },
    "evolocumab": {
        "default": {
            "weight": 75,
            "rationale": "Potent LDL reduction, outcomes data, dosing convenience",
            "evidence": "FOURIER, ACC/AHA Class IIa",
        },
        "indications": {
            "hyperlipidemia": {"weight": 75, "rationale": "For very high LDL or FH"},
            "cv_risk_reduction": {"weight": 85, "rationale": "FOURIER outcomes benefit"},
            "hypertriglyceridemia": {"weight": 30, "rationale": "Minimal TG effect"},
            "statin_intolerance": {"weight": 85, "rationale": "Excellent alternative for intolerance"},
        },
        "clinical_note": "Repatha Q2W/Q4W. Strong CV outcomes data.",
        "drug_class": "PCSK9 Inhibitor"
    },
    
    # ---------------------------------------------------------
    # FIBRATES
    # ---------------------------------------------------------
    "fenofibrate": {
        "default": {
            "weight": 50,
            "rationale": "Preferred fibrate for TG >500, can combine with statins",
            "evidence": "ACC/AHA 2018 for TG >500",
        },
        "indications": {
            "hyperlipidemia": {"weight": 40, "rationale": "Limited LDL effect"},
            "cv_risk_reduction": {"weight": 30, "rationale": "No clear CV outcome benefit"},
            "hypertriglyceridemia": {"weight": 85, "rationale": "First-line for TG >500"},
            "statin_intolerance": {"weight": 25, "rationale": "Only if TG elevated"},
        },
        "clinical_note": "Preferred over gemfibrozil for statin combo. Monitor renal.",
        "drug_class": "Fibrate"
    },
    "gemfibrozil": {
        "default": {
            "weight": 30,
            "rationale": "Avoid with statins (significant interaction)",
            "evidence": "FDA Drug Safety - statin interaction",
        },
        "indications": {
            "hyperlipidemia": {"weight": 20, "rationale": "Limited LDL effect"},
            "cv_risk_reduction": {"weight": 15, "rationale": "No CV outcome benefit"},
            "hypertriglyceridemia": {"weight": 70, "rationale": "Only if NOT on statin"},
            "statin_intolerance": {"weight": 20, "rationale": "Only for isolated hyperTG"},
        },
        "clinical_note": "DO NOT combine with statins. Only isolated hyperTG.",
        "drug_class": "Fibrate"
    },
    
    # ---------------------------------------------------------
    # NIACIN
    # ---------------------------------------------------------
    "niacin": {
        "default": {
            "weight": 15,
            "rationale": "Limited efficacy, significant side effects, no outcomes benefit",
            "evidence": "AIM-HIGH, HPS2-THRIVE - no benefit, more adverse events",
        },
        "indications": {
            "hyperlipidemia": {"weight": 10, "rationale": "Rarely appropriate"},
            "cv_risk_reduction": {"weight": 5, "rationale": "No outcome benefit, harm possible"},
            "hypertriglyceridemia": {"weight": 25, "rationale": "May consider for severe hyperTG if other options fail"},
            "statin_intolerance": {"weight": 10, "rationale": "Poor tolerability, flushing common"},
        },
        "clinical_note": "Rarely appropriate. Flushing, no CV outcome benefit.",
        "drug_class": "Vitamin B3 / Niacin"
    },
    
    # ---------------------------------------------------------
    # BILE ACID SEQUESTRANTS
    # ---------------------------------------------------------
    "colesevelam": {
        "default": {
            "weight": 45,
            "rationale": "Better tolerated than older resins, safe in pregnancy",
            "evidence": "ACC/AHA 2018 Class IIb",
        },
        "indications": {
            "hyperlipidemia": {"weight": 45, "rationale": "Add-on or for statin intolerance"},
            "cv_risk_reduction": {"weight": 35, "rationale": "Limited outcome data"},
            "hypertriglyceridemia": {"weight": 15, "rationale": "May increase TG - avoid"},
            "statin_intolerance": {"weight": 60, "rationale": "Good safety, GI side effects"},
        },
        "clinical_note": "Better tolerability. May improve glycemic control.",
        "drug_class": "Bile Acid Sequestrant"
    },
}


def get_weight_provenance(ingredient: str, indication: str = None) -> Dict:
    """
    Get full weight provenance including curator credentials.
    This is what gets attached to every recommendation.
    """
    data = EXPERT_WEIGHTS.get(ingredient.lower())
    if not data:
        return None
    
    # Get the weight (indication-specific or default)
    weight_data = data.get("default", {})
    indication_info = None
    
    if indication and indication in data.get("indications", {}):
        indication_info = data["indications"][indication]
        weight_data = {
            "weight": indication_info["weight"],
            "rationale": indication_info.get("rationale"),
            "evidence": data["default"].get("evidence"),
        }
    
    return {
        "ingredient": ingredient.lower(),
        "weight": weight_data.get("weight"),
        "rationale": weight_data.get("rationale"),
        "evidence": weight_data.get("evidence"),
        "indication": indication,
        "indication_rationale": indication_info.get("rationale") if indication_info else None,
        "clinical_note": data.get("clinical_note"),
        "drug_class": data.get("drug_class"),
        "curator": {
            "name": CURATOR["name"],
            "credentials": CURATOR["credentials"],
            "license": CURATOR["license"],
            "provenance_hash": CURATOR["provenance_hash"],
            "last_reviewed": CURATOR["last_updated"],
        },
        "weight_type": "indication_specific" if indication and indication_info else "default",
    }


def get_weight(ingredient: str, indication: str = None) -> Tuple[int, str, Optional[str], Optional[str]]:
    """Get weight for an ingredient, optionally for a specific indication."""
    data = EXPERT_WEIGHTS.get(ingredient.lower())
    if not data:
        return (None, None, None, None)
    
    if indication and indication in data.get("indications", {}):
        ind_data = data["indications"][indication]
        return (
            ind_data["weight"],
            f"expert:{indication}",
            ind_data.get("rationale"),
            data["default"].get("evidence")
        )
    
    default = data.get("default", {})
    return (
        default.get("weight"),
        "expert",
        default.get("rationale"),
        default.get("evidence")
    )


def get_combined_weight(ingredient: str, class_size: int, indication: str = None) -> Tuple[int, str, Optional[str], Optional[str], Optional[str]]:
    """
    Get combined weight: expert (with optional indication) overrides auto.
    Returns: (weight, source, rationale, evidence, clinical_note)
    """
    weight, source, rationale, evidence = get_weight(ingredient, indication)
    
    if weight is not None:
        data = EXPERT_WEIGHTS.get(ingredient.lower(), {})
        note = data.get("clinical_note")
        return (weight, source, rationale, evidence, note)
    
    # Auto-weight from class_size
    if class_size <= 15:
        return (90, "auto", None, None, None)
    elif class_size <= 50:
        return (66, "auto", None, None, None)
    else:
        return (33, "auto", None, None, None)


def get_auto_weight(class_size: int) -> int:
    if class_size <= 15:
        return 90
    elif class_size <= 50:
        return 66
    else:
        return 33


def weight_to_priority(weight: int) -> str:
    if weight >= 90:
        return "PRIMARY"
    elif weight >= 60:
        return "SECONDARY"
    elif weight >= 30:
        return "TERTIARY"
    else:
        return "CAUTION"


def get_curator_info() -> Dict:
    return CURATOR.copy()


def get_all_weights() -> Dict:
    return EXPERT_WEIGHTS.copy()


def get_disease_states() -> Dict:
    return DISEASE_STATES.copy()
