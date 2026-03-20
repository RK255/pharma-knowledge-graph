"""
Pharmaceutical Knowledge Graph API - Test Version with PubChem
Port: 8002
"""

import os
import json
import re
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from neo4j import GraphDatabase
import redis

# Import the main app and add pubchem router
import sys
sys.path.insert(0, '/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/production/07_api')

# Create new test app
app = FastAPI(
    title="Pharmaceutical Knowledge Graph API - TEST",
    description="Test API with PubChem endpoints",
    version="2.1.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Neo4j Connection
NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", os.getenv("NEO4J_PASSWORD", ""))

# Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Search Index
DRUG_SEARCH_INDEX: Dict[str, List[Dict[str, str]]] = {}
uuid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')

# Import routes from main
from main import app as prod_app

# Copy all routes
for route in prod_app.routes:
    if hasattr(route, 'path') and route.path not in ['/openapi.json', '/docs', '/redoc']:
        app.routes.append(route)

# =============================================================
# PUBCHEM ENDPOINTS - NEW
# =============================================================

@app.get("/api/pubchem/stats")
async def get_pubchem_stats():
    """Get PubChem property coverage statistics."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    
    with driver.session(database="neo4j") as session:
        result = session.run("""
            MATCH (i:Ingredient)
            RETURN 
                count(i) as total,
                sum(CASE WHEN i.pubchem_cid IS NOT NULL THEN 1 ELSE 0 END) as with_cid,
                sum(CASE WHEN i.smiles IS NOT NULL THEN 1 ELSE 0 END) as with_smiles,
                sum(CASE WHEN i.inchikey IS NOT NULL THEN 1 ELSE 0 END) as with_inchikey,
                sum(CASE WHEN i.iupac_name IS NOT NULL THEN 1 ELSE 0 END) as with_iupac,
                sum(CASE WHEN i.sid IS NOT NULL THEN 1 ELSE 0 END) as with_sid,
                sum(CASE WHEN i.pubchem_date IS NOT NULL THEN 1 ELSE 0 END) as with_date,
                sum(CASE WHEN i.pmid IS NOT NULL THEN 1 ELSE 0 END) as with_pmid
        """)
        r = result.single()
    
    driver.close()
    
    return {
        "total_ingredients": r['total'],
        "with_cid": r['with_cid'],
        "with_smiles": r['with_smiles'],
        "with_inchikey": r['inchikey'],
        "with_iupac": r['with_iupac'],
        "with_sid": r['with_sid'],
        "with_date": r['with_date'],
        "with_pmid": r['with_pmid']
    }


@app.get("/api/pubchem/{rxcui}")
async def get_pubchem_by_rxcui(rxcui: str):
    """Get PubChem properties for an ingredient by RxCUI."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    
    with driver.session(database="neo4j") as session:
        result = session.run("""
            MATCH (i:Ingredient {rxcui: $rxcui})
            RETURN i.rxcui as rxcui, i.name as name, 
                   i.pubchem_cid as pubchem_cid, i.smiles as smiles,
                   i.inchikey as inchikey, i.iupac_name as iupac_name,
                   i.sid as sid, i.pubchem_date as pubchem_date,
                   i.pmid as pmid
        """, rxcui=rxcui)
        
        r = result.single()
    
    driver.close()
    
    if not r:
        raise HTTPException(status_code=404, detail=f"Ingredient {rxcui} not found")
    
    return {
        "rxcui": r['rxcui'],
        "name": r['name'],
        "pubchem_cid": r['pubchem_cid'],
        "smiles": r['smiles'],
        "inchikey": r['inchikey'],
        "iupac_name": r['iupac_name'],
        "sid": r['sid'],
        "pubchem_date": r['pubchem_date'],
        "pmid": r['pmid']
    }


@app.get("/api/pubchem/search/smiles")
async def search_by_smiles(smiles: str = Query(..., description="SMILES string")):
    """Search ingredients by SMILES pattern."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    
    with driver.session(database="neo4j") as session:
        result = session.run("""
            MATCH (i:Ingredient)
            WHERE i.smiles CONTAINS $smiles
            RETURN i.rxcui as rxcui, i.name as name, i.smiles as smiles
            LIMIT 20
        """, smiles=smiles)
        
        matches = [dict(r) for r in result]
    
    driver.close()
    
    return {"query": smiles, "count": len(matches), "results": matches}


@app.get("/api/pubchem/search/inchikey")
async def search_by_inchikey(inchikey: str = Query(..., description="InChIKey")):
    """Search ingredients by InChIKey."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    
    with driver.session(database="neo4j") as session:
        result = session.run("""
            MATCH (i:Ingredient)
            WHERE i.inchikey CONTAINS $inchikey
            RETURN i.rxcui as rxcui, i.name as name, i.inchikey as inchikey
            LIMIT 20
        """, inchikey=inchikey)
        
        matches = [dict(r) for r in result]
    
    driver.close()
    
    return {"query": inchikey, "count": len(matches), "results": matches}


# =============================================================
# DRUG DETAIL WITH PUBCHEM - ENHANCED
# =============================================================

@app.get("/api/drug/{drug_id}/pubchem")
async def get_drug_pubchem(drug_id: str):
    """Get PubChem properties for a drug's ingredients."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    
    with driver.session(database="neo4j") as session:
        # Try to find ingredients via NDC bridge
        result = session.run("""
            MATCH (e:Entity)-[:HAS_NDC]->()-[:MAPS_TO_RXCUI]->()-[:CONSTITUTES]->()-[:HAS_INGREDIENT]->(i:Ingredient)
            WHERE e.fda_set_id = $drug_id OR e.name = $drug_id
            RETURN DISTINCT i.rxcui as rxcui, i.name as name,
                   i.pubchem_cid as cid, i.smiles as smiles,
                   i.inchikey as inchikey, i.iupac_name as iupac
        """, drug_id=drug_id)
        
        ingredients = [dict(r) for r in result]
        
        # Fallback to name bridge
        if not ingredients:
            result = session.run("""
                MATCH (e:Entity)-[:HAS_INGREDIENT_NAME]->(i:Ingredient)
                WHERE e.fda_set_id = $drug_id OR e.name = $drug_id
                RETURN DISTINCT i.rxcui as rxcui, i.name as name,
                       i.pubchem_cid as cid, i.smiles as smiles,
                       i.inchikey as inchikey, i.iupac_name as iupac
            """, drug_id=drug_id)
            ingredients = [dict(r) for r in result]
    
    driver.close()
    
    return {"drug_id": drug_id, "ingredients": ingredients}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
