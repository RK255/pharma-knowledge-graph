#!/usr/bin/env python3
"""
PubChem Properties API Endpoint

Endpoints:
- GET /api/pubchem/{rxcui} - Get PubChem properties for ingredient
- GET /api/pubchem/search?smiles=... - Search by SMILES
- GET /api/pubchem/stats - Coverage statistics
"""

from fastapi import APIRouter, HTTPException, Query
from neo4j import GraphDatabase
from typing import Optional, List
from pydantic import BaseModel

router = APIRouter(prefix="/api/pubchem", tags=["PubChem"])

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "Nani*48301")


class PubChemProperties(BaseModel):
    rxcui: str
    name: str
    pubchem_cid: Optional[str] = None
    smiles: Optional[str] = None
    inchikey: Optional[str] = None
    iupac_name: Optional[str] = None
    sid: Optional[str] = None
    pubchem_date: Optional[str] = None
    pmid: Optional[List[str]] = None
    mesh_pharm: Optional[List[str]] = None


class PubChemStats(BaseModel):
    total_ingredients: int
    with_cid: int
    with_smiles: int
    with_inchikey: int
    with_iupac: int
    with_sid: int
    with_date: int
    with_pmid: int


@router.get("/stats", response_model=PubChemStats)
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
    
    return PubChemStats(
        total_ingredients=r['total'],
        with_cid=r['with_cid'],
        with_smiles=r['with_smiles'],
        with_inchikey=r['with_inchikey'],
        with_iupac=r['with_iupac'],
        with_sid=r['with_sid'],
        with_date=r['with_date'],
        with_pmid=r['with_pmid']
    )


@router.get("/{rxcui}", response_model=PubChemProperties)
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
                   i.pmid as pmid, i.mesh_pharm as mesh_pharm
        """, rxcui=rxcui)
        
        r = result.single()
    
    driver.close()
    
    if not r:
        raise HTTPException(status_code=404, detail=f"Ingredient {rxcui} not found")
    
    return PubChemProperties(
        rxcui=r['rxcui'],
        name=r['name'],
        pubchem_cid=r['pubchem_cid'],
        smiles=r['smiles'],
        inchikey=r['inchikey'],
        iupac_name=r['iupac_name'],
        sid=r['sid'],
        pubchem_date=r['pubchem_date'],
        pmid=r['pmid'].split('|') if r['pmid'] else None,
        mesh_pharm=r['mesh_pharm'].split('|') if r['mesh_pharm'] else None
    )


@router.get("/search/smiles")
async def search_by_smiles(smiles: str = Query(..., description="SMILES string to search")):
    """Search ingredients by SMILES pattern (partial match)."""
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


@router.get("/search/inchikey")
async def search_by_inchikey(inchikey: str = Query(..., description="InChIKey to search")):
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
