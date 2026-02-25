"""Test API for PubChem endpoints - Port 8003 with CORS"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from neo4j import GraphDatabase
import uvicorn

app = FastAPI(title="Pharma KG - PubChem Test", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "Nani*48301")


@app.get("/")
async def root():
    return {"api": "PubChem Test", "port": 8003, "cors": "enabled"}


@app.get("/api/pubchem/stats")
async def stats():
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    with driver.session(database="neo4j") as s:
        r = s.run("""MATCH (i:Ingredient)
            RETURN count(i) as total,
            sum(CASE WHEN i.pubchem_cid IS NOT NULL THEN 1 ELSE 0 END) as cid,
            sum(CASE WHEN i.smiles IS NOT NULL THEN 1 ELSE 0 END) as smiles,
            sum(CASE WHEN i.inchikey IS NOT NULL THEN 1 ELSE 0 END) as inchikey,
            sum(CASE WHEN i.iupac_name IS NOT NULL THEN 1 ELSE 0 END) as iupac,
            sum(CASE WHEN i.sid IS NOT NULL THEN 1 ELSE 0 END) as sid,
            sum(CASE WHEN i.pmid IS NOT NULL THEN 1 ELSE 0 END) as pmid
        """).single()
    driver.close()
    return dict(r)


@app.get("/api/pubchem/{rxcui}")
async def get_pubchem(rxcui: str):
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    with driver.session(database="neo4j") as s:
        r = s.run("""MATCH (i:Ingredient {rxcui: $rxcui})
            RETURN i.rxcui as rxcui, i.name as name,
                   i.pubchem_cid as cid, i.sid as sid, i.smiles as smiles,
                   i.inchikey as inchikey, i.iupac_name as iupac,
                   i.pmid as pmid
        """, rxcui=rxcui).single()
    driver.close()
    if not r:
        raise HTTPException(404, detail=f"RxCUI {rxcui} not found")
    return dict(r)


@app.get("/api/drug/{name}/pubchem")
async def drug_pubchem(name: str):
    """Get PubChem data for a drug's ingredients"""
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    with driver.session(database="neo4j") as s:
        r = s.run("""
            MATCH (e:Entity)-[:HAS_NDC]->()-[:MAPS_TO_RXCUI]->()-[:CONSTITUTES]->()-[:HAS_INGREDIENT]->(i:Ingredient)
            WHERE toLower(e.name) CONTAINS toLower($name)
            RETURN DISTINCT i.rxcui as rxcui, i.name as name,
                   i.pubchem_cid as cid, i.sid as sid, i.smiles as smiles,
                   i.inchikey as inchikey, i.iupac_name as iupac,
                   i.pmid as pmid
            LIMIT 10
        """, name=name)
        ingredients = [dict(row) for row in r]
        
        if not ingredients:
            r = s.run("""
                MATCH (e:Entity)-[:HAS_INGREDIENT_NAME]->(i:Ingredient)
                WHERE toLower(e.name) CONTAINS toLower($name)
                RETURN DISTINCT i.rxcui as rxcui, i.name as name,
                       i.pubchem_cid as cid, i.sid as sid, i.smiles as smiles,
                       i.inchikey as inchikey, i.iupac_name as iupac,
                       i.pmid as pmid
                LIMIT 10
            """, name=name)
            ingredients = [dict(row) for row in r]
    driver.close()
    return {"drug": name, "ingredients": ingredients}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)
