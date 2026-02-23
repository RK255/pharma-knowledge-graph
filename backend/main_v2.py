"""
Pharmaceutical Knowledge Graph API
Production v2 - FDA Section Ordering + GRC-20 Backend
"""

import os
import json
import re
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import redis

# Redis Connection
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# FastAPI App
app = FastAPI(
    title="Pharmaceutical Knowledge Graph API",
    description="Production API v2 - FDA Section Ordering",
    version="2.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Search Index (in-memory for FAST autocomplete)
DRUG_SEARCH_INDEX: Dict[str, List[Dict[str, str]]] = {}

# UUID Pattern for Set ID detection
uuid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')

# =============================================================================
# FDA STANDARD SECTION ORDERING
# =============================================================================

FDA_SECTION_ORDER = {
    'INDICATIONS_AND_USAGE': 1,
    'DOSAGE_AND_ADMINISTRATION': 2,
    'DOSAGE_FORMS_AND_STRENGTHS': 3,
    'CONTRAINDICATIONS': 4,
    'WARNINGS_AND_PRECAUTIONS': 5,
    'ADVERSE_REACTIONS': 6,
    'DRUG_INTERACTIONS': 7,
    'USE_IN_SPECIFIC_POPULATIONS': 8,
    'DRUG_ABUSE_AND_DEPENDENCE': 9,
    'OVERDOSAGE': 10,
    'DESCRIPTION': 11,
    'CLINICAL_PHARMACOLOGY': 12,
    'NONCLINICAL_TOXICOLOGY': 13,
    'CLINICAL_STUDIES': 14,
    'REFERENCES': 15,
    'HOW_SUPPLIED': 16,
    'PATIENT_COUNSELING_INFORMATION': 17,
    'MECHANISM_OF_ACTION': 12.1,
    'PHARMACODYNAMICS': 12.2,
    'PHARMACOKINETICS': 12.3,
    'IMMUNOGENICITY': 12.6,
    'CARCINOGENESIS': 13.1,
    'PREGNANCY': 8.1,
    'LACTATION': 8.2,
    'PEDIATRIC_USE': 8.4,
    'GERIATRIC_USE': 8.5,
    'RENAL_IMPAIRMENT': 8.6,
    'HEPATIC_IMPAIRMENT': 8.7,
    'CLINICAL_TRIALS_EXPERIENCE': 6.1,
    'POSTMARKETING_EXPERIENCE': 6.3,
    'BOXED_WARNING': 0,
    'UNKNOWN': 99,
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
    else:
        type_order = FDA_SECTION_ORDER.get(section_type, 99)
        return (1, type_order, 0, title.lower())


def parse_section_triples(triples: list) -> dict:
    """
    Parse section triples into structured data.
    Triple order appears to be: [title, drug_ref, section_type, content, provenance_hash]
    """
    result = {
        'title': 'Unknown',
        'section_type': 'UNKNOWN',
        'content': '',
        'drug_id': '',
        'provenance_hash': ''
    }
    
    for i, triple in enumerate(triples):
        val = triple.get('value', '')
        if isinstance(val, dict):
            val = val.get('value', '')
        val_str = str(val)
        
        # Position-based parsing (based on observed data structure)
        if i == 0:
            # First triple is usually the title
            result['title'] = val_str
        elif i == 1:
            # Second triple is drug reference (Base58 entity ID)
            result['drug_id'] = val_str
        elif i == 2:
            # Third triple is section_type (e.g., "USE_IN_SPECIFIC_POPULATIONS")
            if val_str in FDA_SECTION_ORDER or val_str.isupper():
                result['section_type'] = val_str
            else:
                # Might be content if structure differs
                if len(val_str) > 100:
                    result['content'] = val_str
        elif i == 3:
            # Fourth triple is usually content
            if len(val_str) > 50:
                result['content'] = val_str
            elif val_str in FDA_SECTION_ORDER:
                result['section_type'] = val_str
        elif i == 4:
            # Fifth triple is provenance hash
            if len(val_str) == 16 and all(c in '0123456789abcdef' for c in val_str.lower()):
                result['provenance_hash'] = val_str
            elif len(val_str) > 100:
                result['content'] = val_str
        
        # Also try value-based detection for robustness
        if val_str in FDA_SECTION_ORDER:
            result['section_type'] = val_str
        elif len(val_str) > 200:
            result['content'] = val_str
        elif re.match(r'^\d+(\.\d+)?\s+\w+', val_str):
            # Looks like a numbered title (e.g., "8.2 Lactation")
            result['title'] = val_str
    
    return result


# =============================================================================
# INDEX BUILDING
# =============================================================================

def build_memory_index():
    """Build in-memory search index from Redis - groups drugs by name"""
    global DRUG_SEARCH_INDEX
    DRUG_SEARCH_INDEX = {}
    if not redis_client:
        return
    
    print("Building in-memory search index...")
    
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
        except Exception as e:
            continue
    
    for name in DRUG_SEARCH_INDEX:
        DRUG_SEARCH_INDEX[name].sort(key=lambda x: x.get('manufacturer', ''))
    
    total_variants = sum(len(v) for v in DRUG_SEARCH_INDEX.values())
    print(f"✅ Search index built: {len(DRUG_SEARCH_INDEX)} unique drugs, {total_variants} total variants")


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    return FileResponse("../pharma-frontend/build/index.html")


@app.get("/api/health")
async def health_check():
    if not redis_client:
        return {"status": "unhealthy", "error": "Redis not connected"}
    
    try:
        redis_client.ping()
        drug_count = redis_client.hlen("pharma:enhanced_drugs")
        entity_count = redis_client.hlen("pharma:entities")
        
        return {
            "status": "healthy",
            "redis": "connected",
            "stats": {
                "drugs": drug_count,
                "entities": entity_count,
                "search_index": len(DRUG_SEARCH_INDEX)
            }
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.get("/api/stats")
async def get_stats():
    if not redis_client:
        raise HTTPException(status_code=500, detail="Redis not available")
    
    try:
        drug_count = redis_client.hlen("pharma:enhanced_drugs")
        entity_count = redis_client.hlen("pharma:entities")
        
        return {
            "total_drugs": drug_count,
            "total_entities": entity_count,
            "database": "Redis",
            "compliance": "GRC-20",
            "search_index_size": len(DRUG_SEARCH_INDEX)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/search/suggestions")
async def get_suggestions(q: str = Query(..., min_length=1)):
    """Fast autocomplete using in-memory index"""
    if not DRUG_SEARCH_INDEX:
        raise HTTPException(status_code=503, detail="Search index not loaded")
    
    query = q.lower().strip()
    suggestions = []
    
    for drug_name, variants in DRUG_SEARCH_INDEX.items():
        if drug_name.startswith(query):
            if variants:
                suggestions.append({
                    "name": variants[0].get("name", drug_name.title()),
                    "manufacturer": variants[0].get("manufacturer", "Unknown"),
                    "variant_count": len(variants)
                })
        
        if len(suggestions) >= 10:
            break
    
    return {"suggestions": suggestions}


@app.get("/api/drug-variants/{drug_name}")
async def get_drug_variants(drug_name: str):
    """Get all manufacturer variants for a drug name"""
    drug_name_lower = drug_name.lower().strip()
    
    if drug_name_lower not in DRUG_SEARCH_INDEX:
        raise HTTPException(status_code=404, detail=f"No variants found for '{drug_name}'")
    
    variants = []
    for v in DRUG_SEARCH_INDEX[drug_name_lower]:
        section_count = redis_client.scard(f"pharma:drug:{v['id']}:sections")
        variants.append({
            "id": v["id"],
            "name": v["name"],
            "manufacturer": v.get("manufacturer", "Unknown"),
            "set_id": v.get("set_id", "Unknown"),
            "nda": v.get("nda", "N/A"),
            "section_count": section_count
        })
    
    return {"drug_name": drug_name, "variant_count": len(variants), "variants": variants}


@app.get("/drug/{drug_id}")
async def get_drug(drug_id: str):
    """Get detailed drug information with FDA-ordered sections"""
    enhanced_raw = redis_client.hget("pharma:enhanced_drugs", drug_id)
    if not enhanced_raw:
        raise HTTPException(status_code=404, detail="Drug not found")
    
    enhanced = json.loads(enhanced_raw)
    
    # Get section IDs from the drug's section set
    section_ids = list(redis_client.smembers(f"pharma:drug:{drug_id}:sections"))
    
    # Build sections list
    sections = []
    for sid in section_ids:
        section_raw = redis_client.hget("pharma:entities", sid)
        if section_raw:
            try:
                section = json.loads(section_raw)
                triples = section.get('triples', [])
                parsed = parse_section_triples(triples)
                
                sections.append({
                    "section_id": sid,
                    "title": parsed['title'],
                    "section_type": parsed['section_type'],
                    "content_preview": parsed['content'][:200] + "..." if len(parsed['content']) > 200 else parsed['content']
                })
            except Exception as e:
                print(f"Error parsing section {sid}: {e}")
                pass
    
    # Sort sections using FDA order
    sections.sort(key=get_section_sort_key)
    
    return {
        "id": drug_id,
        "name": enhanced.get("name", "Unknown"),
        "set_id": enhanced.get("set_id", "Unknown"),
        "manufacturer": enhanced.get("manufacturer", "Unknown"),
        "nda": enhanced.get("nda", "N/A"),
        "ndc": enhanced.get("ndc", "N/A"),
        "ama_citation": enhanced.get("ama_citation", "N/A"),
        "drug_id": enhanced.get("drug_id", drug_id),
        "section_count": len(sections),
        "sections": sections
    }


@app.get("/section/{section_id}")
async def get_section(section_id: str):
    """Get section content"""
    section_raw = redis_client.hget("pharma:entities", section_id)
    if not section_raw:
        raise HTTPException(status_code=404, detail="Section not found")
    
    section = json.loads(section_raw)
    triples = section.get('triples', [])
    parsed = parse_section_triples(triples)
    
    return {
        "section_id": section_id,
        "title": parsed['title'],
        "section_type": parsed['section_type'],
        "content": parsed['content'],
        "drug_id": parsed['drug_id'],
        "provenance_hash": parsed['provenance_hash']
    }


@app.get("/api/grc20/structure/{drug_id}")
async def get_grc20_structure(drug_id: str):
    """Get GRC-20 compliant structure for a drug entity"""
    entity_raw = redis_client.hget("pharma:entities", drug_id)
    if not entity_raw:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    entity = json.loads(entity_raw)
    
    section_ids = list(redis_client.smembers(f"pharma:drug:{drug_id}:sections"))
    
    enhanced_raw = redis_client.hget("pharma:enhanced_drugs", drug_id)
    enhanced = json.loads(enhanced_raw) if enhanced_raw else {}
    
    # Build sections with sorting
    sections_for_sort = []
    for sid in section_ids:
        section_raw = redis_client.hget("pharma:entities", sid)
        if section_raw:
            try:
                section = json.loads(section_raw)
                triples = section.get('triples', [])
                parsed = parse_section_triples(triples)
                
                sections_for_sort.append({
                    "id": sid,
                    "title": parsed['title'],
                    "section_type": parsed['section_type']
                })
            except:
                pass
    
    sections_for_sort.sort(key=get_section_sort_key)
    section_titles = [{"id": s["id"], "title": s["title"]} for s in sections_for_sort]
    
    sample_section = None
    sample_title = "Unknown"
    if sections_for_sort:
        first_section = sections_for_sort[0]
        sample_title = first_section["title"]
        section_raw = redis_client.hget("pharma:entities", first_section["id"])
        if section_raw:
            sample_section = json.loads(section_raw)
    
    def infer_attribute_label(value: str) -> str:
        value_str = str(value)
        
        if uuid_pattern.match(value_str):
            return "set_id"
        
        if len(value_str) == 22 and all(
            c in '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz' 
            for c in value_str
        ):
            return "entity_reference"
        
        if len(value_str) == 16 and all(c in '0123456789abcdef' for c in value_str.lower()):
            return "provenance_hash"
        
        value_lower = value_str.lower()
        if any(word in value_lower for word in ['injection', 'tablet', 'capsule', 'oral', 'mg', 'ml', 'is an', 'are']):
            return "description"
        
        if len(value_str) < 60 and not any(c in value_str for c in ['\n', '.']):
            return "name"
        
        if len(value_str) > 100:
            return "content"
        
        if value_str.isdigit():
            return "number"
        
        return "attribute"
    
    def format_triples(entity_data: dict) -> list:
        triples = []
        seen = set()
        
        for triple in entity_data.get('triples', []):
            attr = triple.get('attribute', '')
            val = triple.get('value', {})
            
            if isinstance(val, dict):
                val_str = val.get('value', '')
            else:
                val_str = str(val)
            
            key = f"{attr}:{val_str[:100]}"
            if key in seen:
                continue
            seen.add(key)
            
            triples.append({
                "attribute_id": attr,
                "attribute_label": infer_attribute_label(val_str),
                "value": val_str[:150] + "..." if len(val_str) > 150 else val_str,
                "value_full_length": len(val_str),
                "value_type": "entity_reference" if isinstance(triple.get('value'), dict) else "string"
            })
        
        return triples
    
    formatted_triples = format_triples(entity)
    
    return {
        "drug_entity": {
            "id": drug_id,
            "triple_count": len(entity.get('triples', [])),
            "unique_triple_count": len(formatted_triples),
            "triples": formatted_triples,
            "context": {
                "drug_name": enhanced.get('name', 'Unknown').title(),
                "manufacturer": enhanced.get('manufacturer', 'Unknown'),
                "set_id": enhanced.get('set_id', 'Unknown')
            }
        },
        "relationship": {
            "type": "has_section",
            "total_sections": len(section_ids),
            "sample_section_ids": [s["id"] for s in sections_for_sort[:5]],
            "section_titles": section_titles[:20]
        },
        "sample_section": {
            "id": sections_for_sort[0]["id"] if sections_for_sort else None,
            "title": sample_title,
            "triple_count": len(sample_section.get('triples', [])) if sample_section else 0,
            "triples": format_triples(sample_section) if sample_section else []
        } if sample_section else None
    }


@app.get("/api/search")
async def search_drugs(q: str, limit: int = 20):
    """Search drugs by name or manufacturer"""
    if not DRUG_SEARCH_INDEX:
        raise HTTPException(status_code=503, detail="Search index not loaded")
    
    query = q.lower().strip()
    results = []
    
    for drug_name, variants in DRUG_SEARCH_INDEX.items():
        if query in drug_name:
            for v in variants:
                section_count = redis_client.scard(f"pharma:drug:{v['id']}:sections")
                results.append({
                    "id": v["id"],
                    "name": v["name"],
                    "manufacturer": v.get("manufacturer", "Unknown"),
                    "set_id": v.get("set_id", "Unknown"),
                    "section_count": section_count,
                    "relevance": 2 if drug_name.startswith(query) else 1
                })
    
    results.sort(key=lambda x: (-x["relevance"], x["name"]))
    
    return {
        "results": results[:limit],
        "total": len(results),
        "query": q
    }


@app.get("/api/drugs")
async def list_drugs(limit: int = 50, offset: int = 0):
    """List drugs with pagination"""
    drugs = []
    all_names = sorted(DRUG_SEARCH_INDEX.keys())
    
    for name in all_names[offset:offset+limit]:
        variants = DRUG_SEARCH_INDEX[name]
        if variants:
            v = variants[0]
            section_count = redis_client.scard(f"pharma:drug:{v['id']}:sections")
            drugs.append({
                "id": v["id"],
                "name": v["name"],
                "manufacturer": v.get("manufacturer", "Unknown"),
                "section_count": section_count
            })
    
    return {
        "drugs": drugs,
        "total": len(DRUG_SEARCH_INDEX),
        "offset": offset,
        "limit": limit
    }


@app.get("/api/section-types")
async def get_section_types():
    """Get all section types with counts"""
    type_counts = {}
    
    # Sample some sections to get type counts
    for entity_id, entity_json in redis_client.hscan_iter("pharma:entities", count=500):
        try:
            entity = json.loads(entity_json)
            triples = entity.get('triples', [])
            parsed = parse_section_triples(triples)
            section_type = parsed.get('section_type', 'UNKNOWN')
            if section_type != 'UNKNOWN':
                type_counts[section_type] = type_counts.get(section_type, 0) + 1
        except:
            pass
    
    sorted_types = sorted(
        type_counts.items(),
        key=lambda x: (FDA_SECTION_ORDER.get(x[0], 99), x[0])
    )
    
    return {
        "section_types": [{"type": t, "count": c, "order": FDA_SECTION_ORDER.get(t, 99)} for t, c in sorted_types],
        "total_types": len(type_counts)
    }


# Static files for React
try:
    app.mount("/static", StaticFiles(directory="../pharma-frontend/build/static"), name="static")
except:
    pass


@app.get("/{path:path}")
async def catch_all(path: str):
    build_path = "../pharma-frontend/build/index.html"
    if os.path.exists(build_path):
        return FileResponse(build_path)
    return {"error": "Frontend not built"}


# =============================================================================
# STARTUP
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Build search index on startup"""
    build_memory_index()


if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("  Pharmaceutical Knowledge Graph API v2.0")
    print("  FDA Section Ordering + In-Memory Search Index")
    print("="*60 + "\n")
    
    # Build index before starting
    build_memory_index()
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
