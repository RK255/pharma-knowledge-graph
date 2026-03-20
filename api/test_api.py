"""
Test API with PubChem endpoints - Port 8002
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from neo4j import GraphDatabase
import uvicorn

app = FastAPI(title="Pharma KG Test API", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", os.getenv("NEO4J_PASSWORD", ""))


@app.get("/")
async def root():
    return {"message": "Pharma KG Test API", "version": "2.1.0", "port": 8002}


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
        "with_inchikey": r['with_inchikey'],
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
    
    return dict(r)


@app.get("/api/drug/{drug_id}/pubchem")
async def get_drug_pubchem(drug_id: str):
    """Get PubChem properties for a drug's ingredients."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    
    with driver.session(database="neo4j") as session:
        # Try NDC bridge first
        result = session.run("""
            MATCH (e:Entity)-[:HAS_NDC]->()-[:MAPS_TO_RXCUI]->()-[:CONSTITUTES]->()-[:HAS_INGREDIENT]->(i:Ingredient)
            WHERE e.fda_set_id = $drug_id OR e.name CONTAINS $drug_id
            RETURN DISTINCT i.rxcui as rxcui, i.name as name,
                   i.pubchem_cid as cid, i.smiles as smiles,
                   i.inchikey as inchikey, i.iupac_name as iupac
        """, drug_id=drug_id)
        
        ingredients = [dict(r) for r in result]
        
        # Fallback to name bridge
        if not ingredients:
            result = session.run("""
                MATCH (e:Entity)-[:HAS_INGREDIENT_NAME]->(i:Ingredient)
                WHERE e.fda_set_id = $drug_id OR e.name CONTAINS $drug_id
                RETURN DISTINCT i.rxcui as rxcui, i.name as name,
                       i.pubchem_cid as cid, i.smiles as smiles,
                       i.inchikey as inchikey, i.iupac_name as iupac
            """, drug_id=drug_id)
            ingredients = [dict(r) for r in result]
    
    driver.close()
    
    return {"drug_id": drug_id, "ingredients": ingredients, "count": len(ingredients)}


@app.get("/api/pubchem/search/smiles")
async def search_by_smiles(smiles: str = Query(...)):
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
