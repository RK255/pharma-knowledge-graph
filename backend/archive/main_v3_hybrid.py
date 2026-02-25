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
neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

app = FastAPI(
    title="Pharmaceutical Knowledge Graph API - Hybrid",
    description="Redis (fast) + Neo4j (graph) hybrid API",
    version="3.0.3"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DRUG_SEARCH_INDEX: Dict[str, List[Dict[str, str]]] = {}

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

def get_related_drugs_by_set_id(set_id: str) -> List[Dict]:
    """Find drugs that share ingredients with the given drug."""
    query = """
    MATCH (e:Entity {fda_set_id: $set_id})-[:HAS_NDC]->(ndc:Entity)-[:MAPS_TO_RXCUI]->(cd:ClinicalDrug)-[:CONSTITUTES]->(scc:RxNormConcept)<-[:HAS_INGREDIENT]-(ing:Ingredient)
    MATCH (other_cd:ClinicalDrug)-[:CONSTITUTES]->(scc)
    WHERE other_cd <> cd
    MATCH (other_ndc:Entity)<-[:HAS_NDC]-(other_fda:Entity)
    WHERE (other_ndc)-[:MAPS_TO_RXCUI]->other_cd AND other_fda.fda_set_id <> $set_id
    OPTIONAL MATCH (other_fda)-[:HAS_NDC]->(on)
    RETURN DISTINCT other_fda.name as name,
           other_fda.fda_set_id as set_id,
           collect(DISTINCT on.name) as ndc_codes,
           ing.name as shared_ingredient
    LIMIT 20
    """
    return neo4j_query(query, {"set_id": set_id})

def get_equivalent_drugs_by_set_id(set_id: str) -> List[Dict]:
    """Get therapeutic equivalents (same ingredients, different manufacturer)."""
    query = """
    MATCH (e:Entity {fda_set_id: $set_id})-[:HAS_NDC]->(ndc:Entity)-[:MAPS_TO_RXCUI]->(cd:ClinicalDrug)
    MATCH (cd)-[:IS_A]->(parent:RxNormConcept)
    MATCH (other_cd:ClinicalDrug)-[:IS_A]->(parent)
    WHERE other_cd <> cd
    MATCH (other_ndc:Entity)<-[:HAS_NDC]-(other_fda:Entity)
    WHERE (other_ndc)-[:MAPS_TO_RXCUI]->other_cd AND other_fda.fda_set_id <> $set_id
    OPTIONAL MATCH (other_fda)-[:HAS_NDC]->(on)
    RETURN DISTINCT other_fda.name as name,
           other_fda.fda_set_id as set_id,
           collect(DISTINCT on.name) as ndc_codes,
           other_cd.name as equivalent_form
    LIMIT 20
    """
    return neo4j_query(query, {"set_id": set_id})

def get_ingredients_by_set_id(set_id: str) -> List[str]:
    """Get active ingredients for a drug by set_id."""
    query = """
    MATCH (e:Entity {fda_set_id: $set_id})-[:HAS_NDC]->(ndc:Entity)-[:MAPS_TO_RXCUI]->(cd:ClinicalDrug)-[:CONSTITUTES]->(scc:RxNormConcept)<-[:HAS_INGREDIENT]-(ing:Ingredient)
    RETURN collect(DISTINCT ing.name) as ingredients
    """
    results = neo4j_query(query, {"set_id": set_id})
    return results[0]['ingredients'] if results else []

def get_all_relationships_by_set_id(set_id: str) -> Dict:
    """Get all relationships for a drug."""
    query = """
    MATCH (e:Entity {fda_set_id: $set_id})
    WHERE (e)-[:HAS_NDC]->()
    OPTIONAL MATCH (e)-[:HAS_NDC]->(ndc:Entity)
    OPTIONAL MATCH (ndc)-[:MAPS_TO_RXCUI]->(cd:ClinicalDrug)
    OPTIONAL MATCH (cd)-[:CONSTITUTES]->(scc:RxNormConcept)<-[:HAS_INGREDIENT]-(ing:Ingredient)
    OPTIONAL MATCH (scc)-[:HAS_DOSE_FORM]->(df:DoseForm)
    OPTIONAL MATCH (cd)-[:IS_A]->(parent:RxNormConcept)
    WITH e, ndc, cd, ing, df, parent
    WITH e,
         collect(DISTINCT ndc.name) as ndcs,
         collect(DISTINCT cd.name) as clinical_drugs,
         collect(DISTINCT cd.rxcui) as rxcuis,
         collect(DISTINCT ing.name) as ingredients,
         collect(DISTINCT df.name) as dose_forms,
         collect(DISTINCT parent.name) as parent_concepts
    RETURN e.name as name, ndcs, clinical_drugs, rxcuis, ingredients, dose_forms, parent_concepts
    LIMIT 1
    """
    results = neo4j_query(query, {"set_id": set_id})
    if results:
        r = results[0]
        return {
            'name': r.get('name'),
            'ndcs': [x for x in r.get('ndcs', []) if x],
            'clinical_drugs': [x for x in r.get('clinical_drugs', []) if x],
            'rxcuis': [x for x in r.get('rxcuis', []) if x],
            'ingredients': [x for x in r.get('ingredients', []) if x],
            'dose_forms': [x for x in r.get('dose_forms', []) if x],
            'parent_concepts': [x for x in r.get('parent_concepts', []) if x]
        }
    return {}

def get_drug_from_neo4j_by_ndc(ndc_codes: List[str]) -> Dict:
    """Get drug info from Neo4j via NDC codes."""
    if not ndc_codes:
        return {}
    query = """
    MATCH (ndc:Entity)
    WHERE ndc.name IN $ndc_codes AND 'NDC' IN labels(ndc)
    OPTIONAL MATCH (fda:Entity)-[:HAS_NDC]->(ndc)
    OPTIONAL MATCH (ndc)-[:MAPS_TO_RXCUI]->(cd:ClinicalDrug)
    OPTIONAL MATCH (cd)-[:CONSTITUTES]->(scc:RxNormConcept)<-[:HAS_INGREDIENT]-(ing:Ingredient)
    WITH ndc, fda, cd, ing
    WITH fda, 
         collect(DISTINCT ndc.name) as ndc_codes,
         collect(DISTINCT cd.name) as clinical_drugs,
         collect(DISTINCT ing.name) as ingredients
    RETURN fda.name as name,
           fda.fda_set_id as fda_set_id,
           ndc_codes,
           clinical_drugs,
           ingredients
    LIMIT 1
    """
    results = neo4j_query(query, {"ndc_codes": ndc_codes})
    if results:
        r = results[0]
        return {
            'name': r.get('name'),
            'fda_set_id': r.get('fda_set_id'),
            'ndc_codes': [x for x in r.get('ndc_codes', []) if x],
            'clinical_drugs': [x for x in r.get('clinical_drugs', []) if x],
            'ingredients': [x for x in r.get('ingredients', []) if x]
        }
    return {}

# =============================================================================
# FDA SECTION ORDERING
# =============================================================================

FDA_SECTION_ORDER = {
    'INDICATIONS_AND_USAGE': 1, 'DOSAGE_AND_ADMINISTRATION': 2,
    'DOSAGE_FORMS_AND_STRENGTHS': 3, 'CONTRAINDICATIONS': 4,
    'WARNINGS_AND_PRECAUTIONS': 5, 'ADVERSE_REACTIONS': 6,
    'DRUG_INTERACTIONS': 7, 'USE_IN_SPECIFIC_POPULATIONS': 8,
    'DRUG_ABUSE_AND_DEPENDENCE': 9, 'OVERDOSAGE': 10,
    'DESCRIPTION': 11, 'CLINICAL_PHARMACOLOGY': 12,
    'NONCLINICAL_TOXICOLOGY': 13, 'CLINICAL_STUDIES': 14,
    'REFERENCES': 15, 'HOW_SUPPLIED': 16,
    'PATIENT_COUNSELING_INFORMATION': 17,
    'BOXED_WARNING': 0, 'UNKNOWN': 99,
}

def extract_section_number(title: str) -> tuple:
    title = title.strip()
    match = re.match(r'^(\d+)(?:\.(\d+))?\s+', title)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2)) if match.group(2) else 0
        return (major, minor, title)
    return (None, None, title)

def get_section_sort_key(section: dict) -> tuple:
    title = section.get('title', '')
    section_type = section.get('section_type', 'UNKNOWN')
    major, minor, _ = extract_section_number(title)
    if major is not None:
        return (0, major, minor, title.lower())
    return (1, FDA_SECTION_ORDER.get(section_type, 99), 0, title.lower())

def parse_section_triples(triples: list) -> dict:
    result = {'title': 'Unknown', 'section_type': 'UNKNOWN', 'content': '', 'drug_id': '', 'provenance_hash': ''}
    for i, triple in enumerate(triples):
        val = triple.get('value', '')
        if isinstance(val, dict):
            val = val.get('value', '')
        val_str = str(val)
        if i == 0:
            result['title'] = val_str
        elif i == 1:
            result['drug_id'] = val_str
        elif i == 2:
            if val_str in FDA_SECTION_ORDER or val_str.isupper():
                result['section_type'] = val_str
            elif len(val_str) > 100:
                result['content'] = val_str
        elif i == 3:
            if len(val_str) > 50:
                result['content'] = val_str
        elif i == 4:
            if len(val_str) == 16:
                result['provenance_hash'] = val_str
            elif len(val_str) > 100:
                result['content'] = val_str
    return result

# =============================================================================
# REDIS HELPERS
# =============================================================================

def get_drug_from_redis(drug_id: str) -> Optional[Dict]:
    data = redis_client.hget("pharma:enhanced_drugs", drug_id)
    if data:
        return json.loads(data)
    return None

def get_sections_from_redis(drug_id: str) -> List[Dict]:
    section_ids = redis_client.smembers(f"pharma:drug:{drug_id}:sections")
    sections = []
    for sid in section_ids:
        entity_data = redis_client.hget("pharma:entities", sid)
        if entity_data:
            entity = json.loads(entity_data)
            if entity.get("triples"):
                parsed = parse_section_triples(entity["triples"])
                sections.append({
                    'section_id': sid,
                    'title': parsed['title'],
                    'section_type': parsed['section_type'],
                    'content_preview': parsed['content'][:300] + '...' if len(parsed['content']) > 300 else parsed['content'],
                    'provenance_hash': parsed['provenance_hash']
                })
    sections.sort(key=get_section_sort_key)
    return sections

def build_memory_index():
    global DRUG_SEARCH_INDEX
    DRUG_SEARCH_INDEX = {}
    count = 0
    for entity_id, drug_json in redis_client.hscan_iter("pharma:enhanced_drugs"):
        try:
            drug = json.loads(drug_json)
            name = drug.get('name', '').lower()
            if name:
                if name not in DRUG_SEARCH_INDEX:
                    DRUG_SEARCH_INDEX[name] = []
                DRUG_SEARCH_INDEX[name].append({
                    'id': entity_id,
                    'name': drug.get('name', ''),
                    'manufacturer': drug.get('manufacturer', ''),
                    'nda': drug.get('nda', ''),
                    'set_id': drug.get('set_id', '')
                })
            count += 1
        except:
            pass
    print(f"Built search index with {count} drugs, {len(DRUG_SEARCH_INDEX)} unique names")

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.on_event("startup")
async def startup_event():
    build_memory_index()
    print("✅ Hybrid API v3.0.3 started: Redis + Neo4j connected")

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
async def get_suggestions(q: str = Query(..., min_length=1)):
    q_lower = q.lower()
    suggestions = []
    for name, drugs in DRUG_SEARCH_INDEX.items():
        if q_lower in name:
            suggestions.extend(drugs[:3])
        if len(suggestions) >= 20:
            break
    return {"query": q, "suggestions": suggestions[:20]}

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
                results.append({
                    'id': drug['id'],
                    'name': drug['name'],
                    'manufacturer': drug['manufacturer'],
                    'nda': drug['nda']
                })
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
async def get_related_drugs(drug_id: str):
    """Get drugs related by shared ingredients."""
    drug_data = get_drug_from_redis(drug_id)
    if not drug_data:
        raise HTTPException(status_code=404, detail="Drug not found")
    
    set_id = drug_data.get('set_id', '')
    if not set_id:
        return {"drug_id": drug_id, "related_drugs": [], "message": "No set_id found"}
    
    related = get_related_drugs_by_set_id(set_id)
    return {"drug_id": drug_id, "set_id": set_id, "related_drugs": related}

@app.get("/api/drug/{drug_id}/equivalents")
async def get_equivalents(drug_id: str):
    """Get therapeutic equivalents."""
    drug_data = get_drug_from_redis(drug_id)
    if not drug_data:
        raise HTTPException(status_code=404, detail="Drug not found")
    
    set_id = drug_data.get('set_id', '')
    if not set_id:
        return {"drug_id": drug_id, "equivalents": [], "message": "No set_id found"}
    
    equivalents = get_equivalent_drugs_by_set_id(set_id)
    return {"drug_id": drug_id, "set_id": set_id, "equivalents": equivalents}

@app.get("/api/drug/{drug_id}/ingredients")
async def get_ingredients(drug_id: str):
    """Get active ingredients."""
    drug_data = get_drug_from_redis(drug_id)
    if not drug_data:
        raise HTTPException(status_code=404, detail="Drug not found")
    
    set_id = drug_data.get('set_id', '')
    if not set_id:
        return {"drug_id": drug_id, "ingredients": [], "message": "No set_id found"}
    
    ingredients = get_ingredients_by_set_id(set_id)
    return {"drug_id": drug_id, "set_id": set_id, "ingredients": ingredients}

@app.get("/api/drug/{drug_id}/graph")
async def get_drug_graph(drug_id: str):
    """Get all Neo4j graph relationships for a drug."""
    drug_data = get_drug_from_redis(drug_id)
    if not drug_data:
        raise HTTPException(status_code=404, detail="Drug not found")
    
    set_id = drug_data.get('set_id', '')
    if not set_id:
        return {"drug_id": drug_id, "graph": {}, "message": "No set_id found"}
    
    graph = get_all_relationships_by_set_id(set_id)
    return {"drug_id": drug_id, "set_id": set_id, "graph": graph}

@app.get("/api/ndc/{ndc_code}")
async def lookup_by_ndc(ndc_code: str):
    """Look up drug by NDC code."""
    ndc_normalized = normalize_ndc_to_11(ndc_code)
    if not ndc_normalized:
        raise HTTPException(status_code=400, detail="Invalid NDC format")
    
    query = """
    MATCH (e:Entity)-[:HAS_NDC]->(n:Entity)
    WHERE n.name = $ndc AND 'NDC' IN labels(n)
    RETURN e.name as name, e.entity_id as entity_id, e.fda_set_id as fda_set_id
    """
    results = neo4j_query(query, {"ndc": ndc_normalized})
    if not results:
        raise HTTPException(status_code=404, detail="NDC not found in graph")
    
    drug_info = results[0]
    set_id = drug_info.get('fda_set_id')
    
    redis_data = None
    if set_id:
        for eid, drug_json in redis_client.hscan_iter("pharma:enhanced_drugs"):
            drug = json.loads(drug_json)
            if drug.get('set_id') == set_id:
                redis_data = drug
                redis_data['redis_id'] = eid
                break
    
    return {
        "ndc_input": ndc_code,
        "ndc_normalized": ndc_normalized,
        "graph_match": drug_info,
        "redis_data": redis_data
    }

@app.get("/api/set_id/{set_id}")
async def lookup_by_set_id(set_id: str):
    """Look up drug by FDA set_id."""
    neo4j_data = get_drug_from_neo4j_by_set_id(set_id)
    
    redis_data = None
    redis_id = None
    for eid, drug_json in redis_client.hscan_iter("pharma:enhanced_drugs"):
        drug = json.loads(drug_json)
        if drug.get('set_id') == set_id:
            redis_data = drug
            redis_id = eid
            break
    
    return {
        "set_id": set_id,
        "redis_id": redis_id,
        "redis_data": redis_data,
        "neo4j_data": neo4j_data
    }

@app.get("/api/rxcui/{rxcui}")
async def lookup_by_rxcui(rxcui: str):
    """Look up drug by RxNorm RxCUI."""
    query = """
    MATCH (r:RxNormConcept {rxcui: $rxcui})
    OPTIONAL MATCH (r)<-[:CONSTITUTES]-(cd:ClinicalDrug)
    OPTIONAL MATCH (cd)<-[:MAPS_TO_RXCUI]-(ndc:Entity)
    OPTIONAL MATCH (r)<-[:HAS_INGREDIENT]-(ing:Ingredient)
    RETURN r.name as name,
           r.rxcui as rxcui,
           r.tty as tty,
           collect(DISTINCT cd.name) as clinical_drugs,
           collect(DISTINCT ndc.name) as ndc_codes,
           collect(DISTINCT ing.name) as ingredients
    """
    results = neo4j_query(query, {"rxcui": rxcui})
    if not results:
        raise HTTPException(status_code=404, detail="RxCUI not found")
    return results[0]

@app.get("/api/section-types")
async def get_section_types():
    return {"section_types": list(FDA_SECTION_ORDER.keys())}

# =============================================================================
# CATCH-ALL FOR FRONTEND
# =============================================================================

@app.get("/{path:path}")
async def catch_all(path: str):
    frontend_path = f"/mnt/fast_raid/server_projects/Geo/graph_workshop/pharma-frontend/build/{path}"
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path)
    return FileResponse("/mnt/fast_raid/server_projects/Geo/graph_workshop/pharma-frontend/build/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
