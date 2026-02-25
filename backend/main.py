from llm_chat import chat_query
"""
Pharmaceutical Knowledge Graph API
Hybrid v3 - Redis (fast lookup) + Neo4j (graph relationships)
"""

import os
import json
import re
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
import redis
from neo4j import GraphDatabase

# =============================================================================
# CONFIGURATION
# =============================================================================

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "Nani*48301")

# =============================================================================
# CONNECTIONS
# =============================================================================

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
redis_drugs = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=15, decode_responses=True)
neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
from graph_weights_admin import get_admin, GraphWeightsAdmin
from admin_routes_graph import register_graph_admin_routes


app = FastAPI(
    title="Pharmaceutical Knowledge Graph API - Hybrid",
    description="Redis (fast) + Neo4j (graph) hybrid API",
    version="3.0.4"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DRUG_SEARCH_INDEX: Dict[str, List[Dict[str, str]]] = {}

def build_search_index():
    """Build search index from Redis data."""
    global DRUG_SEARCH_INDEX
    DRUG_SEARCH_INDEX = {}
    if not redis_drugs:
        print("❌ Redis drugs connection not available")
        return
    try:
        # Load from drug_index (new format)
        index_json = redis_drugs.get('pharma:drug_index')
        if index_json:
            DRUG_SEARCH_INDEX = json.loads(index_json)
            total_variants = sum(len(v) for v in DRUG_SEARCH_INDEX.values())
            print(f"✅ Search index loaded: {len(DRUG_SEARCH_INDEX)} unique drugs, {total_variants} total variants")
            return
        else:
            print("❌ No drug index found in Redis db15")
    except Exception as e:
        print(f"❌ Error loading search index: {e}")

# Load search index on startup
build_search_index()

# =============================================================================
# NDC NORMALIZATION
# =============================================================================

def normalize_ndc_to_11(ndc_str: str) -> Optional[str]:
    if not ndc_str:
        return None
    clean = ndc_str.strip().replace("-", "").replace(" ", "")
    if not clean.isdigit():
        return None
    if len(clean) == 11:
        return clean
    elif len(clean) == 10:
        return clean[:5] + clean[5:8].zfill(4) + clean[8:]
    return None

def normalize_ndc_list(ndc_str: str) -> List[str]:
    if not ndc_str:
        return []
    ndcs = []
    for ndc in ndc_str.split(","):
        normalized = normalize_ndc_to_11(ndc.strip())
        if normalized:
            ndcs.append(normalized)
    return ndcs

# =============================================================================
# NEO4J HELPERS - CORRECT BRIDGE PATH
# =============================================================================

def neo4j_query(query: str, params: dict = None) -> List[Dict]:
    with neo4j_driver.session() as session:
        result = session.run(query, params or {})
        return [dict(record) for record in result]

def get_drug_from_neo4j_by_set_id(set_id: str) -> Dict:
    """Get drug info from Neo4j via FDA set_id with correct ingredient bridge."""
    query = """
    MATCH (e:Entity {fda_set_id: $set_id})
    WHERE (e)-[:HAS_NDC]->()
    OPTIONAL MATCH (e)-[:HAS_NDC]->(ndc:Entity)
    OPTIONAL MATCH (ndc)-[:MAPS_TO_RXCUI]->(cd:ClinicalDrug)
    OPTIONAL MATCH (cd)-[:CONSTITUTES]->(scc:RxNormConcept)<-[:HAS_INGREDIENT]-(ing:Ingredient)
    OPTIONAL MATCH (scc)-[:HAS_DOSE_FORM]->(df:DoseForm)
    WITH e, ndc, cd, ing, df
    WITH e, 
         collect(DISTINCT ndc.name) as ndc_codes,
         collect(DISTINCT cd.name) as clinical_drugs,
         collect(DISTINCT cd.rxcui) as rxcuis,
         collect(DISTINCT ing.name) as ingredients,
         collect(DISTINCT df.name) as dose_forms
    RETURN e.name as name, 
           e.fda_set_id as fda_set_id,
           e.entity_id as neo4j_entity_id,
           ndc_codes,
           clinical_drugs,
           rxcuis,
           ingredients,
           dose_forms
    LIMIT 1
    """
    results = neo4j_query(query, {"set_id": set_id})
    if results:
        r = results[0]
        return {
            'name': r.get('name'),
            'fda_set_id': r.get('fda_set_id'),
            'neo4j_entity_id': r.get('neo4j_entity_id'),
            'ndc_codes': [x for x in r.get('ndc_codes', []) if x],
            'clinical_drugs': [x for x in r.get('clinical_drugs', []) if x],
            'rxcuis': [x for x in r.get('rxcuis', []) if x],
            'ingredients': [x for x in r.get('ingredients', []) if x],
            'dose_forms': [x for x in r.get('dose_forms', []) if x]
        }
    return {}

def get_related_drugs_by_set_id(set_id: str, indication: str = None) -> List[Dict]:
    """Find drugs related by shared ingredients with clinical weighting."""
    from clinical_weights_admin import get_combined_weight, weight_to_priority, get_weight_provenance
    
    # Method 1: Find drugs with same ingredient (generics/alternatives)
    query1 = """
    MATCH (e:Entity)-[:HAS_INGREDIENT_NAME]->(i:Ingredient)
    WHERE e.fda_set_id = $set_id
    WITH DISTINCT i
    MATCH (i)<-[:HAS_INGREDIENT_NAME]-(other:Entity)
    WHERE other.fda_set_id <> $set_id
    RETURN DISTINCT 
           other.name as name,
           other.fda_set_id as set_id,
           'same_ingredient' as relationship,
           i.name as ingredient,
           0 as class_size
    LIMIT 10
    """
    related_by_ingredient = neo4j_query(query1, {"set_id": set_id})
    
    # Method 2: Find drugs by pharmacological class
    query2 = """
    MATCH (e:Entity)-[:HAS_INGREDIENT_NAME]->(i:Ingredient)
    WHERE e.fda_set_id = $set_id AND i.mesh_pharm IS NOT NULL
    WITH i, split(i.mesh_pharm, '|') as source_classes
    UNWIND source_classes as source_class
    WITH i, source_class
    MATCH (other_ing:Ingredient)
    WHERE other_ing.mesh_pharm IS NOT NULL 
      AND other_ing.name <> i.name
      AND other_ing.mesh_pharm CONTAINS source_class
    WITH source_class, other_ing, i,
         size((other_ing)<-[:HAS_INGREDIENT_NAME]-()) as drugs_in_class
    MATCH (other_ing)<-[:HAS_INGREDIENT_NAME]-(other_drug:Entity)
    WHERE other_drug.fda_set_id <> $set_id
    WITH other_drug, other_ing, source_class, drugs_in_class,
         other_ing.mesh_pharm_prov as provenance,
         other_ing.pmid as pmid,
         other_ing.sid as sid
    RETURN DISTINCT
           other_drug.name as name,
           other_drug.fda_set_id as set_id,
           'pharmacological_class' as relationship,
           other_ing.name as related_ingredient,
           source_class as shared_class,
           drugs_in_class as class_size,
           provenance as mesh_provenance,
           pmid as pubmed_id,
           sid as pubchem_sid
    ORDER BY drugs_in_class ASC
    LIMIT 30
    """
    related_by_class = neo4j_query(query2, {"set_id": set_id})
    
    # Combine results
    all_related = []
    seen = set()
    
    # Process same ingredient matches (weight = 100, PRIMARY)
    for r in related_by_ingredient:
        key = r.get('name', '').lower()
        if key not in seen:
            seen.add(key)
            r['clinical_weight'] = 100
            r['weight_source'] = 'exact_match'
            r['clinical_priority'] = 'PRIMARY'
            all_related.append(r)
    
    # Process pharmacological class matches with clinical weighting
    for r in related_by_class:
        key = r.get('name', '').lower()
        if key not in seen:
            seen.add(key)
            
            ingredient = r.get('related_ingredient', '')
            class_size = r.get('class_size', 999)
            
            # Get combined weight (expert or auto), with indication context
            weight, source, rationale, evidence, note = get_combined_weight(ingredient, class_size, indication)
            
            r['clinical_weight'] = weight
            r['weight_source'] = source
            r['clinical_priority'] = weight_to_priority(weight)
            
            if rationale:
                r['weight_rationale'] = rationale
            if evidence:
                r['weight_evidence'] = evidence
            if note:
                r['clinical_note'] = note
            
            # Add curator provenance for expert weights
            if source.startswith('expert'):
                provenance = get_weight_provenance(ingredient, indication)
                if provenance and provenance.get('curator'):
                    curator = provenance['curator']
                    r['weight_provenance'] = {
                        "curator": curator['name'],
                        "credentials": curator['credentials'],
                        "license": curator['license'],
                        "provenance_hash": provenance.get('curator_hash', ''),
                        "last_reviewed": provenance.get('last_updated', ''),
                    }
            
            all_related.append(r)
    
    # Sort by clinical_weight descending, then class_size ascending
    all_related.sort(key=lambda x: (-x.get('clinical_weight', 50), x.get('class_size', 999)))
    
    return all_related[:25]


@app.get("/")
async def root():
    return {
        "message": "Pharmaceutical Knowledge Graph API - Hybrid v3.0.3",
        "status": "running",
        "backends": {"redis": "connected", "neo4j": "connected"},
        "endpoints": {
            "drug": "/drug/{drug_id}",
            "search": "/api/search?q={query}",
            "suggestions": "/api/search/suggestions?q={query}",
            "stats": "/api/stats",
            "neo4j": {
                "related": "/api/drug/{drug_id}/related",
                "equivalents": "/api/drug/{drug_id}/equivalents",
                "ingredients": "/api/drug/{drug_id}/ingredients",
                "graph": "/api/drug/{drug_id}/graph"
            },
            "lookup": {
                "by_ndc": "/api/ndc/{ndc_code}",
                "by_set_id": "/api/set_id/{set_id}",
                "by_rxcui": "/api/rxcui/{rxcui}"
            }
        }
    }

@app.get("/api/health")
async def health_check():
    redis_status = "ok" if redis_client.ping() else "error"
    neo4j_status = "ok"
    try:
        neo4j_query("RETURN 1")
    except:
        neo4j_status = "error"
    return {
        "status": "healthy",
        "redis": redis_status,
        "neo4j": neo4j_status,
        "drug_count": len(DRUG_SEARCH_INDEX)
    }

@app.get("/api/stats")
async def get_stats():
    drug_count = redis_client.hlen("pharma:enhanced_drugs")
    section_count = redis_client.hlen("pharma:entities")
    
    neo4j_stats = neo4j_query("MATCH (n) RETURN count(n) as node_count")
    node_count = neo4j_stats[0]['node_count'] if neo4j_stats else 0
    
    rel_stats = neo4j_query("MATCH ()-[r]->() RETURN count(r) as rel_count")
    rel_count = rel_stats[0]['rel_count'] if rel_stats else 0
    
    # Count FDA drugs with ingredient bridges
    bridge_stats = neo4j_query("""
        MATCH (e:Entity)-[:HAS_NDC]->(ndc:Entity)-[:MAPS_TO_RXCUI]->(cd:ClinicalDrug)-[:CONSTITUTES]->(scc:RxNormConcept)<-[:HAS_INGREDIENT]-(ing:Ingredient)
        WHERE e.fda_set_id IS NOT NULL
        RETURN count(DISTINCT e) as count
    """)
    bridge_count = bridge_stats[0]['count'] if bridge_stats else 0
    
    return {
        "redis": {
            "drugs": drug_count,
            "sections": section_count,
            "unique_names": len(DRUG_SEARCH_INDEX)
        },
        "neo4j": {
            "nodes": node_count,
            "relationships": rel_count,
            "fda_drugs_with_ingredients": bridge_count
        }
    }

# =============================================================================
# REDIS ENDPOINTS
# =============================================================================

@app.get("/api/search/suggestions")
async def get_suggestions(q: str = Query(..., min_length=2)):
    """Get search suggestions for drug names (grouped by name)"""
    q_lower = q.lower()
    suggestions = []
    
    for name, variants in DRUG_SEARCH_INDEX.items():
        if q_lower in name:
            suggestions.append({
                "name": name.title(),
                "variant_count": len(variants),
                "top_manufacturer": variants[0].get('manufacturer', 'Unknown') if variants else 'Unknown'
            })
            if len(suggestions) >= 15:
                break
    
    return {"suggestions": suggestions}

@app.get("/api/drug-variants/{drug_name}")
async def get_drug_variants(drug_name: str):
    """Get all manufacturer variants for a drug name"""
    drug_name_lower = drug_name.lower().strip()
    
    if drug_name_lower not in DRUG_SEARCH_INDEX:
        raise HTTPException(status_code=404, detail="Drug not found")
    
    variants = DRUG_SEARCH_INDEX[drug_name_lower]
    
    # Add section count to each variant
    enriched_variants = []
    for v in variants:
        section_count = redis_client.scard(f"pharma:drug:{v['id']}:sections")
        enriched_variants.append({
            **v,
            "section_count": section_count
        })
    
    return {
        "drug_name": drug_name.title(),
        "total_variants": len(enriched_variants),
        "variants": enriched_variants
    }


@app.get("/api/drug-variants/{drug_name}")
async def get_drug_variants(drug_name: str):
    name_lower = drug_name.lower()
    variants = DRUG_SEARCH_INDEX.get(name_lower, [])
    return {"name": drug_name, "variants": variants}

@app.get("/drug/{drug_id}")
async def get_drug(drug_id: str):
    """Get full drug info - Redis for content, Neo4j for relationships."""
    drug_data = get_drug_from_redis(drug_id)
    if not drug_data:
        raise HTTPException(status_code=404, detail="Drug not found")
    
    sections = get_sections_from_redis(drug_id)
    
    set_id = drug_data.get('set_id', '')
    ndc_codes = normalize_ndc_list(drug_data.get('ndc', ''))
    
    neo4j_data = {}
    try:
        if set_id:
            neo4j_data = get_drug_from_neo4j_by_set_id(set_id)
        if not neo4j_data and ndc_codes:
            neo4j_data = get_drug_from_neo4j_by_ndc(ndc_codes)
    except Exception as e:
        print(f"Neo4j lookup error: {e}")
    
    response = {
        "id": drug_id,
        "name": drug_data.get('name', ''),
        "set_id": set_id,
        "manufacturer": drug_data.get('manufacturer', ''),
        "nda": drug_data.get('nda', ''),
        "ndc": drug_data.get('ndc', ''),
        "ndc_normalized": ndc_codes,
        "ama_citation": drug_data.get('ama_citation', ''),
        "drug_id": drug_id,
        "section_count": len(sections),
        "sections": sections,
        "graph_data": {
            "neo4j_entity_id": neo4j_data.get('neo4j_entity_id'),
            "clinical_drugs": neo4j_data.get('clinical_drugs', []),
            "rxcuis": neo4j_data.get('rxcuis', []),
            "ingredients": neo4j_data.get('ingredients', []),
            "dose_forms": neo4j_data.get('dose_forms', []),
            "ndc_codes_neo4j": neo4j_data.get('ndc_codes', [])
        }
    }
    
    return response

@app.get("/section/{section_id}")
async def get_section(section_id: str):
    entity_data = redis_client.hget("pharma:entities", section_id)
    if not entity_data:
        raise HTTPException(status_code=404, detail="Section not found")
    
    entity = json.loads(entity_data)
    parsed = parse_section_triples(entity.get('triples', []))
    
    return {
        "section_id": section_id,
        "title": parsed['title'],
        "section_type": parsed['section_type'],
        "content": parsed['content'],
        "drug_id": parsed['drug_id'],
        "provenance_hash": parsed['provenance_hash']
    }

@app.get("/api/search")
async def search_drugs(q: str, limit: int = 20):
    q_lower = q.lower()
    results = []
    for name, drugs in DRUG_SEARCH_INDEX.items():
        if q_lower in name:
            for drug in drugs:
                result_item = {
                    'id': drug['id'],
                    'name': drug['name'],
                    'rxcui': drug.get('rxcui', ''),
                    'tty': drug.get('tty', ''),
                    'citation': drug.get('citation', '')
                }
                if drug.get('manufacturer'):
                    result_item['manufacturer'] = drug['manufacturer']
                if drug.get('nda'):
                    result_item['nda'] = drug['nda']
                results.append(result_item)
                if len(results) >= limit:
                    break
        if len(results) >= limit:
            break
    return {"query": q, "count": len(results), "results": results}

@app.get("/api/drugs")
async def list_drugs(limit: int = 50, offset: int = 0):
    drugs = []
    cursor = 0
    count = 0
    while count < offset + limit:
        cursor, items = redis_client.hscan("pharma:enhanced_drugs", cursor, count=100)
        for entity_id, drug_json in items:
            if count >= offset and len(drugs) < limit:
                drug = json.loads(drug_json)
                drugs.append({
                    'id': entity_id,
                    'name': drug.get('name', ''),
                    'manufacturer': drug.get('manufacturer', ''),
                    'nda': drug.get('nda', '')
                })
            count += 1
        if cursor == 0:
            break
    return {"count": len(drugs), "drugs": drugs}

# =============================================================================
# NEO4J ENDPOINTS
# =============================================================================



@app.get("/api/drug/{drug_id}/related")
async def get_related_drugs(drug_id: str, indication: str = None):
    """Get drugs related by shared ingredients with clinical weighting.
    
    Args:
        drug_id: Drug identifier (FDA entity_id or RxNorm ID)
        indication: Optional disease state for indication-specific weighting
                   Options: hyperlipidemia, cv_risk_reduction, hypertriglyceridemia, statin_intolerance
    """
    # Normalize indication parameter (convert spaces to underscores, lowercase)
    if indication:
        indication = indication.replace(" ", "_").lower()
    
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
    }


@app.get("/api/clinical/weights")
async def get_clinical_weights():
    """Get all clinical expert weights."""
    from clinical_weights_admin import get_all_weights, get_curator_info
    return {
        "curator": get_curator_info(),
        "weights": get_all_weights()
    }


@app.get("/api/clinical/disease-states")
async def get_disease_states():
    """Get supported disease states for indication-specific weighting."""
    from clinical_weights_admin import get_disease_states
    return get_disease_states()


# =============================================================================
# REDIS HELPER FUNCTIONS
# =============================================================================


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

def get_drug_from_redis(drug_id: str) -> Dict:
    """Get drug data from Redis by entity_id."""
    try:
        drug_json = redis_client.hget("pharma:enhanced_drugs", drug_id)
        if drug_json:
            return json.loads(drug_json)
        return None
    except Exception as e:
        print(f"Redis error getting drug {drug_id}: {e}")
        return None


def get_sections_from_redis(drug_id: str) -> List[Dict]:
    """Get all sections for a drug from Redis."""
    sections = []
    try:
        section_ids = redis_client.smembers(f"pharma:drug:{drug_id}:sections")
        for section_id in section_ids:
            section_json = redis_client.hget("pharma:entities", section_id)
            if section_json:
                section = json.loads(section_json)
                sections.append({
                    'id': section_id,
                    'title': section.get('title', ''),
                    'content': section.get('content', '')[:500],  # Truncate for list view
                    'section_type': section.get('section_type', ''),
                    'provenance_hash': section.get('provenance_hash', '')
                })
    except Exception as e:
        print(f"Redis error getting sections for {drug_id}: {e}")
    return sections


# =============================================================================
# CLINICAL WEIGHTS ADMIN API
# =============================================================================

@app.get("/api/admin/weights")
async def admin_list_weights():
    """List all drugs with clinical weights."""
    from clinical_weights_admin import load_weights
    data = load_weights()
    return {
        "count": len(data.get("drugs", {})),
        "curator": data.get("curator"),
        "last_updated": data.get("last_updated"),
        "drugs": data.get("drugs", {})
    }


@app.get("/api/admin/weights/{drug_name}")
async def admin_get_weight(drug_name: str):
    """Get weight for a specific drug."""
    from clinical_weights_admin import get_drug_weight
    weight = get_drug_weight(drug_name)
    if not weight:
        raise HTTPException(status_code=404, detail=f"Drug '{drug_name}' not found in weights")
    return {"drug": drug_name.lower(), "weight": weight}


@app.post("/api/admin/weights/{drug_name}")
async def admin_set_weight(drug_name: str, weight_data: dict):
    """Create or update weight for a drug.
    
    Example body:
    {
        "default": {
            "weight": 80,
            "rationale": "Well-tolerated, generic available",
            "evidence": "ACC/AHA 2018 Class IIa"
        },
        "indications": {
            "statin_intolerance": {"weight": 90, "rationale": "First-line alternative"}
        },
        "clinical_note": "Generic available. Good safety profile.",
        "drug_class": "Cholesterol Absorption Inhibitor"
    }
    """
    from clinical_weights_admin import set_drug_weight
    try:
        result = set_drug_weight(drug_name, weight_data)
        return {"status": "success", "drug": drug_name.lower(), "weight": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/admin/weights/{drug_name}")
async def admin_delete_weight(drug_name: str):
    """Delete a drug's weight entry."""
    from clinical_weights_admin import delete_drug_weight
    if delete_drug_weight(drug_name):
        return {"status": "deleted", "drug": drug_name.lower()}
    raise HTTPException(status_code=404, detail=f"Drug '{drug_name}' not found")


@app.get("/api/admin/disease-states")
async def admin_list_disease_states():
    """List all disease states for indication-specific weighting."""
    from clinical_weights_admin import get_disease_states
    return get_disease_states()


@app.post("/api/admin/disease-states/{key}")
async def admin_add_disease_state(key: str, info: dict):
    """Add or update a disease state.
    
    Example body:
    {
        "name": "Diabetic Dyslipidemia",
        "description": "Lipid abnormalities in diabetic patients",
        "first_line": "High-intensity statins",
        "guidelines": "ADA 2023, ACC/AHA 2018"
    }
    """
    from clinical_weights_admin import add_disease_state
    return add_disease_state(key, info)


@app.get("/api/admin/curator")
async def admin_get_curator():
    """Get curator credentials."""
    from clinical_weights_admin import get_curator_info
    return get_curator_info()


@app.put("/api/admin/curator")
async def admin_set_curator(curator: dict):
    """Update curator credentials.
    
    Example body:
    {
        "name": "Kevin G",
        "credentials": "PharmD",
        "license": "WA DOH RPH License #PH61629288",
        "experience": "20+ years clinical pharmacy practice",
        "specialization": "Ambulatory care, chronic disease management"
    }
    """
    from clinical_weights_admin import set_curator_info
    return set_curator_info(curator)


@app.get("/api/admin/summary")
async def admin_summary():
    """Get summary statistics of the weight system."""
    from clinical_weights_admin import load_weights
    data = load_weights()
    drugs = data.get("drugs", {})
    
    # Count by priority
    priority_counts = {"PRIMARY": 0, "SECONDARY": 0, "TERTIARY": 0, "CAUTION": 0}
    indication_counts = {}
    
    for drug, info in drugs.items():
        weight = info.get("default", {}).get("weight", 50)
        if weight >= 90:
            priority_counts["PRIMARY"] += 1
        elif weight >= 60:
            priority_counts["SECONDARY"] += 1
        elif weight >= 30:
            priority_counts["TERTIARY"] += 1
        else:
            priority_counts["CAUTION"] += 1
        
        for ind in info.get("indications", {}).keys():
            indication_counts[ind] = indication_counts.get(ind, 0) + 1
    
    return {
        "total_drugs": len(drugs),
        "priority_distribution": priority_counts,
        "indications_supported": indication_counts,
        "curator": data.get("curator", {}).get("name"),
        "last_updated": data.get("last_updated"),
        "version": data.get("version")
    }


# =============================================================================
# GRAPH-BASED ADMIN ROUTES
# =============================================================================

# Register graph-based admin routes
register_graph_admin_routes(app)

@app.get("/api/graph/weight/{ingredient}")
async def graph_get_weight(ingredient: str, indication: str = None):
    """Get clinical weight for an ingredient from the graph."""
    from graph_weights_admin import get_admin
    admin = get_admin()
    weight = admin.get_weight(ingredient, indication)
    if not weight:
        raise HTTPException(status_code=404, detail=f"No weight found for '{ingredient}'")
    return {"ingredient": ingredient, "indication": indication or "default", **weight}


@app.get("/api/graph/recommendations/{drug}")
async def graph_get_recommendations(drug: str, indication: str = "default"):
    """Get clinically weighted recommendations for a drug from the graph."""
    from graph_weights_admin import get_admin
    admin = get_admin()
    recs = admin.get_recommendations_for_indication(drug, indication)
    return {
        "drug": drug,
        "indication": indication,
        "recommendations": recs,
        "source": "neo4j_graph"
    }


@app.get("/api/graph/provenance/{ingredient}")
async def graph_get_provenance(ingredient: str, indication: str = None):
    """Get full provenance for a clinical weight."""
    from graph_weights_admin import get_admin
    admin = get_admin()
    weight = admin.get_weight(ingredient, indication)
    if not weight:
        raise HTTPException(status_code=404, detail=f"No weight found for '{ingredient}'")
    
    return {
        "ingredient": ingredient,
        "indication": indication or "default",
        "weight": weight['weight'],
        "rationale": weight['rationale'],
        "evidence": weight.get('evidence'),
        "curator": {
            "name": weight.get('curator'),
            "credentials": weight.get('curator_credentials'),
            "license": weight.get('curator_license'),
            "hash": weight.get('curator_hash')
        },
        "updated_at": weight.get('updated_at'),
        "source": "neo4j_graph"
    }

# Serve static admin page
from fastapi.staticfiles import StaticFiles
import os

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/admin", StaticFiles(directory=static_dir, html=True), name="admin")

# =============================================================================
# ADMIN AUTH
# =============================================================================

import hashlib
import secrets
from datetime import datetime, timedelta

# Simple session storage (in production, use Redis)
ADMIN_SESSIONS = {}

ADMIN_PASSWORD_HASH = hashlib.sha256("Nani*48301".encode()).hexdigest()

@app.post("/api/admin/auth")
async def admin_auth(request: dict):
    """Authenticate admin access."""
    password = request.get("password", "")
    if hashlib.sha256(password.encode()).hexdigest() == ADMIN_PASSWORD_HASH:
        token = secrets.token_hex(32)
        ADMIN_SESSIONS[token] = datetime.now() + timedelta(hours=24)
        return {"status": "success", "token": token, "expires_in": 86400}
    raise HTTPException(status_code=401, detail="Invalid password")

@app.post("/api/admin/verify")
async def admin_verify(token: str):
    """Verify admin session token."""
    if token in ADMIN_SESSIONS and ADMIN_SESSIONS[token] > datetime.now():
        return {"status": "valid"}
    return {"status": "invalid"}

@app.post("/api/admin/logout")
async def admin_logout(token: str):
    """Logout admin session."""
    if token in ADMIN_SESSIONS:
        del ADMIN_SESSIONS[token]
    return {"status": "logged_out"}

# Protect admin endpoints with token verification
def verify_admin_token(token: str = None):
    if not token or token not in ADMIN_SESSIONS or ADMIN_SESSIONS[token] < datetime.now():
        raise HTTPException(status_code=401, detail="Admin authentication required")
    return True

# =============================================================================
# CHAT ENDPOINT - Natural Language Query Interface
# =============================================================================

from pydantic import BaseModel
from typing import List, Dict, Optional

class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[Dict]] = None

class ChatResponse(BaseModel):
    response: str
    tool_calls: Optional[List[Dict]] = None
    drugs_found: Optional[List[Dict]] = None

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Natural language query interface for drug information."""
    result = await chat_query(request.message, request.conversation_history)
    return ChatResponse(
        response=result.get("response", ""),
        tool_calls=result.get("tool_calls"),
        drugs_found=result.get("drugs_found")
    )

# =============================================================================
# SERVER STARTUP
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Pharmaceutical Knowledge Graph API...")
    print("   API docs: http://localhost:8002/docs")
    print("   Admin UI: http://localhost:8002/admin")
    uvicorn.run(app, host="0.0.0.0", port=8002)
