"""
Pharmaceutical Knowledge Graph API v3
Hybrid: Redis (FDA documents) + Neo4j (RxNorm + PubChem enrichment)
"""

import os
import json
import re
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis
from neo4j import GraphDatabase

# Redis Connection
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Neo4j Connection
neo4j_driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "Nani*48301"))



def fmt(val, default="-"):
    """Format value, return default for None/empty"""
    if val is None or val == "" or val == []:
        return default
    return val

# FastAPI App
app = FastAPI(
    title="Pharmaceutical Knowledge Graph API v3",
    description="Hybrid API: Redis for FDA documents + Neo4j for RxNorm/PubChem enrichment",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory search index
DRUG_SEARCH_INDEX: Dict[str, List[Dict[str, str]]] = {}
uuid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')


class IngredientInfo(BaseModel):
    name: str
    rxcui: str
    pubchem_cid: Optional[str] = None
    mesh_classes: Optional[List[str]] = None

class DrugDetailV3(BaseModel):
    drug_id: str
    name: str
    set_id: str
    nda: str
    ndc: str
    manufacturer: str
    ama_citation: str
    sections: List[Dict]
    section_count: int
    ingredients: List[IngredientInfo] = []
    clinical_drugs: List[str] = []

class StatsResponseV3(BaseModel):
    redis_drugs: int
    redis_sections: int
    neo4j_entities: int
    neo4j_ingredients: int
    linked_entities: int
    ingredients_with_mesh: int
    ingredients_with_ndc_path: int


def get_ingredients_for_set_id(set_id: str) -> tuple:
    """Get ingredients from Neo4j for a given FDA set_id via NDC path"""
    try:
        with neo4j_driver.session(database="neo4j") as session:
            # Correct path: Entity → NDC → ClinicalDrug → RxNormConcept ← Ingredient
            result = session.run("""
                MATCH (e:Entity {fda_set_id: $set_id})-[:HAS_NDC]->(:NDC)-[:MAPS_TO_RXCUI]->(:ClinicalDrug)-[:CONSTITUTES]->(:RxNormConcept)<-[:HAS_INGREDIENT]-(i:Ingredient)
                RETURN DISTINCT
                    i.name as name,
                    i.rxcui as rxcui,
                    i.pubchem_cid as cid,
                    i.mesh_pharm as mesh
            """, set_id=set_id)
            
            ingredients = {}
            for r in result:
                rxcui = r['rxcui']
                if rxcui not in ingredients:
                    ingredients[rxcui] = {
                        'name': r['name'],
                        'rxcui': str(rxcui),
                        'pubchem_cid': fmt(str(r['cid']) if r['cid'] else None),
                        'mesh_classes': fmt(r['mesh'].split('|') if r['mesh'] else None)
                    }
            
            if ingredients:
                return list(ingredients.values())
            return []  # Empty list - will trigger fallback in endpoint
    except Exception as e:
        print(f"Neo4j query error: {e}")
        return []




def get_ingredients_by_name(drug_name: str) -> list:
    """Fallback: lookup ingredients by drug name when NDC mapping fails"""
    try:
        # Normalize drug name
        name = drug_name.lower().strip()
        # Remove common suffixes
        for suffix in [' hydrochloride', ' hcl', ' sulfate', ' tablet', ' capsule', ' injection', ' oral']:
            name = name.replace(suffix, '')
        name = name.strip()
        
        with neo4j_driver.session(database="neo4j") as session:
            result = session.run("""
                MATCH (i:Ingredient)
                WHERE toLower(i.name) CONTAINS $name OR $name CONTAINS toLower(i.name)
                RETURN i.name as name, i.rxcui as rxcui, i.pubchem_cid as cid, i.mesh_pharm as mesh
                LIMIT 3
            """, name=name)
            
            ingredients = []
            for r in result:
                ingredients.append({
                    'name': r['name'],
                    'rxcui': str(r['rxcui']),
                    'pubchem_cid': str(r['cid']) if r['cid'] else '-',
                    'mesh_classes': r['mesh'].split('|') if r['mesh'] else ['-'],
                    'matched_by': 'name_fallback'
                })
            return ingredients
    except Exception as e:
        print(f"Fallback lookup error: {e}")
        return []

def build_memory_index():
    """Build search index from Redis"""
    global DRUG_SEARCH_INDEX
    DRUG_SEARCH_INDEX = {}
    
    for entity_id, data_str in redis_client.hscan_iter("pharma:enhanced_drugs"):
        try:
            data = json.loads(data_str)
            name = data.get('name', '').lower().strip()
            if name:
                if name not in DRUG_SEARCH_INDEX:
                    DRUG_SEARCH_INDEX[name] = []
                DRUG_SEARCH_INDEX[name].append({
                    "id": entity_id,
                    "name": name.title(),
                    "set_id": data.get('set_id', ''),
                    "manufacturer": data.get('manufacturer', 'Unknown'),
                    "nda": data.get('nda', 'N/A')
                })
        except:
            continue
    
    for name in DRUG_SEARCH_INDEX:
        DRUG_SEARCH_INDEX[name].sort(key=lambda x: x.get('manufacturer', ''))
    
    print(f"✅ Search index: {len(DRUG_SEARCH_INDEX)} unique drugs")


@app.on_event("startup")
async def startup_event():
    build_memory_index()
    print("✅ API v3 Ready (Redis + Neo4j)")


@app.get("/")
async def root():
    return {
        "name": "Pharmaceutical Knowledge Graph API v3",
        "version": "3.0.0",
        "status": "operational",
        "architecture": {
            "redis": "FDA package inserts (51K drugs, 1M sections)",
            "neo4j": "RxNorm + PubChem enrichment (8.7K ingredients, 1.3K with MeSH)"
        },
        "endpoints": {
            "search": "/api/search?q={query}",
            "drug": "/api/drug/{drug_id}",
            "drug_by_set_id": "/api/drug/set/{set_id}",
            "ingredient": "/api/ingredient/{rxcui}",
            "mesh_search": "/api/mesh/{mesh_class}",
            "stats": "/api/stats"
        }
    }


@app.get("/api/stats", response_model=StatsResponseV3)
async def get_stats():
    """Get database statistics"""
    redis_drugs = redis_client.scard("pharma:drugs")
    redis_sections = redis_client.scard("pharma:sections")
    
    with neo4j_driver.session(database="neo4j") as session:
        neo4j_entities = session.run("MATCH (e:Entity) RETURN count(e) as c").single()['c']
        neo4j_ingredients = session.run("MATCH (i:Ingredient) RETURN count(i) as c").single()['c']
        linked = session.run("""
            MATCH (e:Entity)-[:HAS_NDC]->()-[:MAPS_TO_RXCUI]->()
            RETURN count(DISTINCT e) as c
        """).single()['c']
        with_mesh = session.run("""
            MATCH (i:Ingredient) WHERE i.mesh_pharm IS NOT NULL
            RETURN count(i) as c
        """).single()['c']
        with_ndc_path = session.run("""
            MATCH (i:Ingredient)-[:HAS_INGREDIENT]->(:RxNormConcept)<-[:CONSTITUTES]-(:ClinicalDrug)<-[:MAPS_TO_RXCUI]-(:NDC)
            RETURN count(DISTINCT i) as c
        """).single()['c']
    
    return StatsResponseV3(
        redis_drugs=redis_drugs,
        redis_sections=redis_sections,
        neo4j_entities=neo4j_entities,
        neo4j_ingredients=neo4j_ingredients,
        linked_entities=linked,
        ingredients_with_mesh=with_mesh,
        ingredients_with_ndc_path=with_ndc_path
    )


@app.get("/api/search")
async def search_drugs(q: str = Query(..., min_length=2)):
    """Search drugs by name"""
    q_lower = q.lower()
    results = []
    
    for name, variants in DRUG_SEARCH_INDEX.items():
        if q_lower in name:
            set_id = variants[0].get('set_id', '')
            ingredients = get_ingredients_for_set_id(set_id)
            
            results.append({
                "name": name.title(),
                "variant_count": len(variants),
                "top_manufacturer": variants[0].get('manufacturer', 'Unknown'),
                "has_enrichment": len(ingredients) > 0,
                "ingredient_names": [i['name'] for i in ingredients[:3]]
            })
            
            if len(results) >= 15:
                break
    
    return {"query": q, "results": results}


@app.get("/api/drug/{drug_id}", response_model=DrugDetailV3)
async def get_drug_detail(drug_id: str):
    """Get full drug details with Neo4j enrichment"""
    drug_data = redis_client.hget("pharma:enhanced_drugs", drug_id)
    if not drug_data:
        raise HTTPException(status_code=404, detail="Drug not found")
    
    drug = json.loads(drug_data)
    set_id = drug.get('set_id', '')
    
    # Get sections from Redis
    section_ids = redis_client.smembers(f"pharma:drug:{drug_id}:sections")
    sections = []
    for sid in section_ids:
        section_raw = redis_client.hget("pharma:entities", sid)
        if section_raw:
            section_entity = json.loads(section_raw)
            section_attrs = {}
            for triple in section_entity.get('triples', []):
                attr = triple.get('attribute', '')
                val = triple.get('value', {})
                section_attrs[attr] = val.get('value', '') if isinstance(val, dict) else str(val)
            
            title = next((v for v in section_attrs.values() if v and 5 < len(str(v)) < 100 and not uuid_pattern.match(str(v))), "Unknown")
            content = max([v for v in section_attrs.values() if v and len(str(v)) > 100], key=len, default="")
            
            sections.append({
                "section_id": sid,
                "title": str(title),
                "content_preview": str(content)[:200] + "..." if content else ""
            })
    
    # Get Neo4j enrichment (with fallback to name-based lookup)
    ingredients = get_ingredients_for_set_id(set_id)
    if not ingredients:
        ingredients = get_ingredients_by_name(drug.get('name', ''))
    
    return DrugDetailV3(
        drug_id=drug_id,
        name=drug.get('name', ''),
        set_id=set_id,
        nda=drug.get('nda', 'N/A'),
        ndc=drug.get('ndc', 'N/A'),
        manufacturer=drug.get('manufacturer', 'Unknown'),
        ama_citation=drug.get('ama_citation', 'N/A'),
        sections=sections,
        section_count=len(sections),
        ingredients=[IngredientInfo(**i) for i in ingredients]
    )


@app.get("/api/drug/set/{set_id}")
async def get_drug_by_set_id(set_id: str):
    """Get drug by FDA set_id with full enrichment"""
    for entity_id, data_str in redis_client.hscan_iter("pharma:enhanced_drugs"):
        data = json.loads(data_str)
        if data.get('set_id') == set_id:
            return await get_drug_detail(entity_id)
    
    # Not in Redis, check Neo4j directly
    with neo4j_driver.session(database="neo4j") as session:
        result = session.run("""
            MATCH (e:Entity {fda_set_id: $set_id})
            RETURN e.name as name
            LIMIT 1
        """, set_id=set_id)
        
        record = result.single()
        if record:
            ingredients = get_ingredients_for_set_id(set_id)
            return {
                "set_id": set_id,
                "name": record['name'],
                "ingredients": ingredients,
                "in_redis": False
            }
    
    raise HTTPException(status_code=404, detail="Set ID not found")


@app.get("/api/ingredient/{rxcui}")
async def get_ingredient(rxcui: str):
    """Get ingredient details by RxCUI"""
    with neo4j_driver.session(database="neo4j") as session:
        result = session.run("""
            MATCH (i:Ingredient)
            WHERE toString(i.rxcui) = $rxcui OR i.rxcui = toInteger($rxcui)
            RETURN i.name as name, i.rxcui as rxcui,
                   i.pubchem_cid as cid, i.mesh_pharm as mesh
        """, rxcui=rxcui)
        
        record = result.single()
        if not record:
            raise HTTPException(status_code=404, detail="Ingredient not found")
        
        # Get FDA drugs containing this ingredient
        drugs_result = session.run("""
            MATCH (i:Ingredient)<-[:HAS_INGREDIENT]-(:RxNormConcept)<-[:CONSTITUTES]-(:ClinicalDrug)<-[:MAPS_TO_RXCUI]-(:NDC)<-[:HAS_NDC]-(e:Entity)
            WHERE toString(i.rxcui) = $rxcui OR i.rxcui = toInteger($rxcui)
            RETURN DISTINCT e.name as drug, e.fda_set_id as set_id
            LIMIT 10
        """, rxcui=rxcui)
        
        drugs = [dict(r) for r in drugs_result]
        
        return {
            "name": record['name'],
            "rxcui": str(record['rxcui']),
            "pubchem_cid": fmt(str(record['cid']) if record['cid'] else None),
            "mesh_classes": fmt(record['mesh'].split('|') if record['mesh'] else None),
            "fda_drugs": drugs
        }


@app.get("/api/mesh/{mesh_class}")
async def get_drugs_by_mesh(mesh_class: str):
    """Find all ingredients with a specific MeSH pharmacological class"""
    with neo4j_driver.session(database="neo4j") as session:
        result = session.run("""
            MATCH (i:Ingredient)
            WHERE i.mesh_pharm CONTAINS $mesh_class
            RETURN i.name as ingredient, toString(i.rxcui) as rxcui, i.mesh_pharm as mesh, i.pubchem_cid as cid
            ORDER BY i.name
            LIMIT 50
        """, mesh_class=mesh_class)
        
        ingredients = []
        for r in result:
            ingredients.append({
                "ingredient": r['ingredient'],
                "rxcui": r['rxcui'],
                "pubchem_cid": str(r['cid']) if r['cid'] else None,
                "mesh_classes": r['mesh'].split('|') if r['mesh'] else []
            })
        
        return {
            "mesh_class": mesh_class,
            "count": len(ingredients),
            "ingredients": ingredients
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
