"""
Graph-Based Admin Routes for Clinical Weights
==============================================
Replaces JSON-based admin with Neo4j graph backend.
All updates are atomic and immediately live.
"""

from fastapi import HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, List
from graph_weights_admin import GraphWeightsAdmin, get_admin

# Pydantic models for request validation
class WeightUpdate(BaseModel):
    weight: int
    rationale: Optional[str] = None
    evidence_id: Optional[str] = None
    clinical_note: Optional[str] = None

class CuratorUpdate(BaseModel):
    name: str
    credentials: str
    license: str
    experience: Optional[str] = None
    specialization: Optional[str] = None

class EvidenceCreate(BaseModel):
    evidence_id: str
    name: str
    type: str  # 'clinical_trial', 'guideline', 'meta_analysis', etc.
    year: Optional[int] = None
    url: Optional[str] = None

class IndicationUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    first_line: Optional[str] = None
    guidelines: Optional[str] = None


# Get admin singleton
def get_graph_admin() -> GraphWeightsAdmin:
    return get_admin()


# =============================================================================
# WEIGHT ENDPOINTS
# =============================================================================

async def admin_list_weights():
    """List all drugs with clinical weights from the graph."""
    admin = get_graph_admin()
    ingredients = admin.list_all_weighted_ingredients()
    
    # Get curator info
    expert = admin.get_expert(name="Kevin")
    
    return {
        "count": len(ingredients),
        "curator": expert,
        "source": "neo4j_graph",
        "drugs": {ing['ingredient']: {
            "weight_count": ing['weight_count'],
            "indications": ing['indications']
        } for ing in ingredients}
    }


async def admin_get_weight(drug_name: str):
    """Get all weights for a specific drug from the graph."""
    admin = get_graph_admin()
    weights = admin.get_all_weights_for_ingredient(drug_name)
    
    if not weights:
        raise HTTPException(status_code=404, detail=f"Drug '{drug_name}' not found in weights")
    
    return {
        "drug": drug_name.lower(),
        "source": "neo4j_graph",
        "weights": weights
    }


async def admin_update_weight(drug_name: str, indication: str, update: WeightUpdate):
    """
    Atomically update a weight in the graph.
    
    This is the main admin update endpoint - changes are immediately live.
    """
    admin = get_graph_admin()
    
    result = admin.update_weight(
        ingredient=drug_name,
        indication=indication,
        weight=update.weight,
        rationale=update.rationale,
        evidence_id=update.evidence_id,
        clinical_note=update.clinical_note
    )
    
    if not result.get('success'):
        raise HTTPException(status_code=400, detail=result.get('error', 'Update failed'))
    
    return {
        "status": "success",
        "source": "neo4j_graph",
        "updated": result
    }


async def admin_delete_weight(drug_name: str, indication: str):
    """Delete a weight from the graph."""
    admin = get_graph_admin()
    
    result = admin.delete_weight(drug_name, indication)
    
    if not result.get('success'):
        raise HTTPException(status_code=404, detail=result.get('error', 'Weight not found'))
    
    return {
        "status": "deleted",
        "drug": drug_name.lower(),
        "indication": indication
    }


# =============================================================================
# EVIDENCE ENDPOINTS
# =============================================================================

async def admin_list_evidence():
    """List all evidence sources from the graph."""
    admin = get_graph_admin()
    evidence = admin.list_evidence()
    return {
        "count": len(evidence),
        "evidence": evidence
    }


async def admin_add_evidence(ev: EvidenceCreate):
    """Add a new evidence source to the graph."""
    admin = get_graph_admin()
    
    result = admin.add_evidence(
        evidence_id=ev.evidence_id,
        name=ev.name,
        evidence_type=ev.type,
        year=ev.year,
        url=ev.url
    )
    
    if not result.get('success'):
        raise HTTPException(status_code=400, detail=result.get('error', 'Failed to add evidence'))
    
    return {
        "status": "success",
        "evidence_id": ev.evidence_id
    }


# =============================================================================
# INDICATION ENDPOINTS
# =============================================================================

async def admin_list_indications():
    """List all disease state indications from the graph."""
    admin = get_graph_admin()
    indications = admin.list_indications()
    return {
        "count": len(indications),
        "indications": indications
    }


async def admin_update_indication(name: str, update: IndicationUpdate):
    """Update an indication's metadata in the graph."""
    admin = get_graph_admin()
    
    result = admin.update_indication(
        name=name,
        display_name=update.display_name,
        description=update.description,
        first_line=update.first_line,
        guidelines=update.guidelines
    )
    
    if not result.get('success'):
        raise HTTPException(status_code=400, detail=result.get('error', 'Update failed'))
    
    return {
        "status": "success",
        "indication": name
    }


# =============================================================================
# EXPERT/CURATOR ENDPOINTS
# =============================================================================

async def admin_get_curator():
    """Get curator/expert credentials from the graph."""
    admin = get_graph_admin()
    expert = admin.get_expert(name="Kevin")  # Default curator
    
    if not expert:
        # Return default if no expert found
        return {
            "name": "Kevin G",
            "credentials": "PharmD",
            "license": "WA DOH RPH License #PH61629288",
            "experience": "20+ years clinical pharmacy practice",
            "specialization": "Ambulatory care, chronic disease management"
        }
    
    return expert


async def admin_list_experts():
    """List all clinical experts in the graph."""
    admin = get_graph_admin()
    experts = admin.list_experts()
    return {
        "count": len(experts),
        "experts": experts
    }


# =============================================================================
# SUMMARY & EXPORT
# =============================================================================

async def admin_summary():
    """Get summary statistics from the graph."""
    admin = get_graph_admin()
    
    # Get all weighted ingredients
    ingredients = admin.list_all_weighted_ingredients()
    
    # Count by priority
    priority_counts = {"PRIMARY": 0, "SECONDARY": 0, "TERTIARY": 0, "CAUTION": 0}
    indication_counts = {}
    
    for ing in ingredients:
        for ind in ing.get('indications', []):
            # Get weight for this indication
            weight_data = admin.get_weight(ing['ingredient'], ind)
            if weight_data:
                weight = weight_data.get('weight', 50)
                if ind == 'default':
                    if weight >= 90:
                        priority_counts["PRIMARY"] += 1
                    elif weight >= 60:
                        priority_counts["SECONDARY"] += 1
                    elif weight >= 30:
                        priority_counts["TERTIARY"] += 1
                    else:
                        priority_counts["CAUTION"] += 1
                
                indication_counts[ind] = indication_counts.get(ind, 0) + 1
    
    expert = admin.get_expert(name="Kevin")
    
    return {
        "total_drugs": len(ingredients),
        "priority_distribution": priority_counts,
        "indications_supported": indication_counts,
        "curator": expert.get('name') if expert else None,
        "source": "neo4j_graph"
    }


async def admin_export():
    """Export all graph weights to JSON (for backup)."""
    admin = get_graph_admin()
    export = admin.export_to_json()
    return {
        "status": "success",
        "exported_at": export.get('exported_at'),
        "total_drugs": len(export.get('drugs', {})),
        "file": "clinical_weights.json"
    }


# =============================================================================
# ROUTE REGISTRATION HELPER
# =============================================================================

def register_graph_admin_routes(app):
    """
    Register graph-based admin routes on a FastAPI app.
    Replaces the JSON-based routes with graph-based ones.
    """
    
    @app.get("/api/graph/admin/weights")
    async def _admin_list_weights():
        return await admin_list_weights()
    
    @app.get("/api/graph/admin/weights/{drug_name}")
    async def _admin_get_weight(drug_name: str):
        return await admin_get_weight(drug_name)
    
    @app.post("/api/graph/admin/weights/{drug_name}/{indication}")
    async def _admin_update_weight(drug_name: str, indication: str, update: WeightUpdate):
        return await admin_update_weight(drug_name, indication, update)
    
    @app.delete("/api/graph/admin/weights/{drug_name}/{indication}")
    async def _admin_delete_weight(drug_name: str, indication: str):
        return await admin_delete_weight(drug_name, indication)
    
    @app.get("/api/graph/admin/evidence")
    async def _admin_list_evidence():
        return await admin_list_evidence()
    
    @app.post("/api/graph/admin/evidence")
    async def _admin_add_evidence(ev: EvidenceCreate):
        return await admin_add_evidence(ev)
    
    @app.get("/api/graph/admin/indications")
    async def _admin_list_indications():
        return await admin_list_indications()
    
    @app.put("/api/graph/admin/indications/{name}")
    async def _admin_update_indication(name: str, update: IndicationUpdate):
        return await admin_update_indication(name, update)
    
    @app.get("/api/graph/admin/curator")
    async def _admin_get_curator():
        return await admin_get_curator()
    
    @app.get("/api/graph/admin/experts")
    async def _admin_list_experts():
        return await admin_list_experts()
    
    @app.get("/api/graph/admin/summary")
    async def _admin_summary():
        return await admin_summary()
    
    @app.post("/api/graph/admin/export")
    async def _admin_export():
        return await admin_export()
    
    print("✅ Graph admin routes registered at /api/graph/admin/*")


if __name__ == "__main__":
    # Test the routes
    import asyncio
    
    async def test():
        print("=== Testing Graph Admin Routes ===\n")
        
        print("1. List weights:")
        result = await admin_list_weights()
        print(f"   Count: {result['count']}")
        
        print("\n2. Get weight for ezetimibe:")
        result = await admin_get_weight("ezetimibe")
        for w in result['weights'][:3]:
            print(f"   {w['indication']}: {w['weight']}/100")
        
        print("\n3. Update weight:")
        result = await admin_update_weight("ezetimibe", "statin_intolerance", WeightUpdate(
            weight=93,
            rationale="Updated via graph admin API"
        ))
        print(f"   Result: {result}")
        
        print("\n4. List evidence:")
        result = await admin_list_evidence()
        for ev in result['evidence']:
            print(f"   {ev['id']}: {ev['name']} ({ev['type']})")
        
        print("\n5. Summary:")
        result = await admin_summary()
        print(f"   Total drugs: {result['total_drugs']}")
        print(f"   Source: {result['source']}")
    
    asyncio.run(test())
