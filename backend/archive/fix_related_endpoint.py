"""
Fix the get_related_drugs endpoint to bridge RxNorm IDs to FDA entities
"""
import re

# Read the current main file
with open('/mnt/fast_raid/server_projects/Geo/graph_workshop/pharma-backend/main_v3_hybrid_v2.py', 'r') as f:
    content = f.read()

# Add the bridge function before get_drug_from_redis
bridge_function = '''
def get_fda_entity_from_rxnorm(drug_id: str) -> tuple:
    """Bridge RxNorm ID to FDA entity_id via Neo4j.
    
    Returns: (entity_id, set_id, drug_name) or (None, None, None)
    """
    # First check if this is already an FDA entity_id
    drug_data = get_drug_from_redis(drug_id)
    if drug_data:
        return drug_data.get('entity_id'), drug_data.get('set_id'), drug_data.get('name')
    
    # Try to find RxCUI from drug_index
    import redis as redis_module
    r_drugs = redis_module.Redis(host='localhost', port=6379, db=15, decode_responses=True)
    
    idx_json = r_drugs.get('pharma:drug_index')
    if idx_json:
        idx = json.loads(idx_json)
        # Search for drug_id in the index
        for name, variants in idx.items():
            for v in variants:
                if v.get('id') == drug_id:
                    rxcui = v.get('rxcui')
                    drug_name = v.get('name')
                    if rxcui:
                        # Find FDA Entity via Ingredient RxCUI in Neo4j
                        query = """
                        MATCH (e:Entity)-[:HAS_INGREDIENT_NAME]->(i:Ingredient)
                        WHERE i.rxcui = $rxcui
                        RETURN e.name as name, e.fda_set_id as set_id
                        LIMIT 1
                        """
                        results = neo4j_query(query, {"rxcui": rxcui})
                        if results:
                            set_id = results[0].get('set_id')
                            # Look up entity_id in Redis
                            for k, v in redis_client.hgetall("pharma:enhanced_drugs").items():
                                data = json.loads(v)
                                if data.get('set_id') == set_id:
                                    return data.get('entity_id'), set_id, drug_name
                    break
    return None, None, None

'''

# Find where to insert
if 'def get_fda_entity_from_rxnorm' not in content:
    # Insert before get_drug_from_redis
    insert_pos = content.find('def get_drug_from_redis(')
    if insert_pos > 0:
        content = content[:insert_pos] + bridge_function + content[insert_pos:]

# Update the get_related_drugs endpoint to use the bridge
old_endpoint = '''@app.get("/api/drug/{drug_id}/related")
async def get_related_drugs(drug_id: str, indication: str = None):
    """Get drugs related by shared ingredients with clinical weighting.
    
    Args:
        drug_id: Drug identifier
        indication: Optional disease state for indication-specific weighting
                   Options: hyperlipidemia, cv_risk_reduction, hypertriglyceridemia, statin_intolerance
    """
    drug_data = get_drug_from_redis(drug_id)
    if not drug_data:
        raise HTTPException(status_code=404, detail="Drug not found")
    
    set_id = drug_data.get('set_id', '')
    if not set_id:
        return {"drug_id": drug_id, "related_drugs": [], "message": "No set_id found"}
    
    related = get_related_drugs_by_set_id(set_id, indication=indication)
    
    return {
        "drug_id": drug_id, 
        "set_id": set_id, 
        "indication": indication,
        "related_drugs": related
    }'''

new_endpoint = '''@app.get("/api/drug/{drug_id}/related")
async def get_related_drugs(drug_id: str, indication: str = None):
    """Get drugs related by shared ingredients with clinical weighting.
    
    Args:
        drug_id: Drug identifier (FDA entity_id or RxNorm ID)
        indication: Optional disease state for indication-specific weighting
                   Options: hyperlipidemia, cv_risk_reduction, hypertriglyceridemia, statin_intolerance
    """
    # Try to bridge RxNorm ID to FDA entity
    entity_id, set_id, drug_name = get_fda_entity_from_rxnorm(drug_id)
    
    if not set_id:
        raise HTTPException(status_code=404, detail=f"Drug not found: {drug_id}")
    
    related = get_related_drugs_by_set_id(set_id, indication=indication)
    
    return {
        "drug_id": drug_id,
        "entity_id": entity_id,
        "set_id": set_id, 
        "drug_name": drug_name,
        "indication": indication,
        "related_drugs": related
    }'''

content = content.replace(old_endpoint, new_endpoint)

# Save the updated file
with open('/mnt/fast_raid/server_projects/Geo/graph_workshop/pharma-backend/main_v3_hybrid_v2.py', 'w') as f:
    f.write(content)

print("✅ Updated main_v3_hybrid_v2.py with RxNorm bridge")
