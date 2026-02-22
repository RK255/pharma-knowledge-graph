"""
Pharmaceutical Knowledge Graph API
Production v1 - GRC-20 Backend
"""

import os
import json
import re
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import redis

# Configuration
DATA_FILE_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/development/output/grc20_pharmaceutical_data_v10.json"
ENHANCED_DATA_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/development/output/enhanced_chunked_documents.json"

# Redis Connection
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# FastAPI App
app = FastAPI(
    title="Pharmaceutical Knowledge Graph API",
    description="Production API for FDA drug data with full provenance tracking",
    version="1.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Search Index (in-memory for performance)
DRUG_SEARCH_INDEX: Dict[str, Dict[str, str]] = {}

# UUID Pattern for Set ID detection
uuid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')

# Pydantic Models
class ProvenanceData(BaseModel):
    fda_document_id: str
    drug_name: str
    set_id: str
    section_type: str
    title: str
    citation: str
    type: str

class SectionSummary(BaseModel):
    section_id: str
    section_type: str
    title: str
    content_preview: str

class SectionDetail(BaseModel):
    section_id: str
    section_type: str
    title: str
    content: str
    provenance: ProvenanceData

class DrugDetail(BaseModel):
    drug_id: str
    name: str
    set_id: str
    nda: str
    ndc: str
    manufacturer: str
    ama_citation: str
    sections: List[SectionSummary]
    section_count: int

class SearchSuggestion(BaseModel):
    id: str
    name: str
    set_id: str

class StatsResponse(BaseModel):
    total_drugs: int
    total_sections: int
    total_links: int
    enhanced_matched: int
    search_index_size: int


def build_memory_index():
    """Build in-memory search index from Redis"""
    global DRUG_SEARCH_INDEX
    DRUG_SEARCH_INDEX = {}
    if not redis_client:
        return
    
    print("Building in-memory search index...")
    count = 0
    for entity_id, data_str in redis_client.hscan_iter("pharma:enhanced_drugs"):
        try:
            data = json.loads(data_str)
            name = data.get('name')
            if name:
                if name not in DRUG_SEARCH_INDEX:
                    DRUG_SEARCH_INDEX[name] = {
                        "id": entity_id,
                        "name": name.title(),
                        "set_id": data.get('set_id', '')
                    }
                    count += 1
        except Exception as e:
            print(f"Error indexing {entity_id}: {e}")
            continue
            
    print(f"✅ Search index built with {count} drugs")

def load_data_to_redis():
    """Load GRC-20 data into Redis with proper Drug/Section/Relationship handling"""
    global DRUG_SEARCH_INDEX
    
    if not redis_client:
        return False
    
    if redis_client.exists("pharma:loaded"):
        print("✅ Data already in Redis. Loading search index into memory...")
        build_memory_index()
        return True

    # Load Enhanced Metadata
    enhanced_metadata = {}
    if os.path.exists(ENHANCED_DATA_PATH):
        print(f"Loading Enhanced Metadata from {ENHANCED_DATA_PATH}...")
        try:
            with open(ENHANCED_DATA_PATH, 'r', encoding='utf-8') as f:
                enhanced_docs = json.load(f)
                for doc in enhanced_docs:
                    sid = doc.get('fda_set_id')
                    if sid:
                        app_num = doc.get('application_number')
                        app_str = str(app_num) if app_num else "N/A"
                        ndc = doc.get('ndc_codes', [])
                        ndc_str = ", ".join(ndc) if isinstance(ndc, list) else str(ndc)
                        enhanced_metadata[sid] = {
                            'nda': app_str,
                            'ndc': ndc_str,
                            'ama_citation': doc.get('ama_citation', 'N/A'),
                            'manufacturer': doc.get('manufacturer', 'Unknown')
                        }
            print(f"Loaded {len(enhanced_metadata)} enhanced metadata records.")
        except Exception as e:
            print(f"Error loading enhanced metadata: {e}")

    # Load GRC-20 Entities
    print(f"Loading GRC-20 data from {DATA_FILE_PATH}...")
    if not os.path.exists(DATA_FILE_PATH):
        print(f"❌ ERROR: Data file not found at {DATA_FILE_PATH}")
        return False

    with open(DATA_FILE_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    entities = data.get('entities', [])
    total_entities = len(entities)
    print(f"Processing {total_entities} entities...")

    # PHASE 1: Build ID Maps
    print("Phase 1: Building ID maps...")
    
    # Map entity_id -> entity for fast lookup
    entity_map = {}
    
    # Identify Drugs (entities with UUID Set ID)
    all_drug_ids = set()
    
    # Identify Relationship entities and their targets
    relationship_targets = {}  # drug_id -> [section_ids]
    
    # Identify potential sections (entities that are targets of relationships)
    potential_section_ids = set()
    
    name_attr_id = None
    
    for i, entity in enumerate(entities):
        entity_id = entity.get('id')
        if not entity_id: continue
        
        entity_map[entity_id] = entity
        
        # Extract attributes
        attrs = {}
        for triple in entity.get('triples', []):
            attr = triple.get('attribute')
            val = triple.get('value')
            if isinstance(val, dict): val = val.get('value', '')
            attrs[attr] = val
            
            if not name_attr_id and isinstance(val, str) and len(val) > 0 and len(val) < 100:
                name_attr_id = attr
        
        # Check if this is a Drug (has UUID)
        for v in attrs.values():
            if isinstance(v, str) and uuid_pattern.match(v):
                all_drug_ids.add(entity_id)
                break
        
        # Check if this is a Relationship entity
        source = attrs.get('source')
        target = attrs.get('target')
        rel_type = attrs.get('relationship_type')
        
        if source and target and rel_type:
            # This is a relationship entity
            if rel_type == 'has_section' or 'section' in rel_type.lower():
                if source in all_drug_ids or target in all_drug_ids:
                    # The target is a section, the source is a drug
                    potential_section_ids.add(target)
                    if source not in relationship_targets:
                        relationship_targets[source] = []
                    relationship_targets[source].append(target)

        if (i + 1) % 100000 == 0:
            print(f"Phase 1 Scanned {i+1}/{total_entities}... (Drugs: {len(all_drug_ids)}, Sections: {len(potential_section_ids)})")

    print(f"Phase 1 Complete. Found {len(all_drug_ids)} Drugs, {len(potential_section_ids)} Sections")

    # PHASE 2: Store Everything
    print("Phase 2: Storing entities...")
    
    pipeline = redis_client.pipeline()
    drug_count = 0
    section_count = 0
    link_count = 0
    matched_count = 0
    missed_count = 0
    
    for i, (entity_id, entity) in enumerate(entity_map.items()):
        attrs = {}
        for triple in entity.get('triples', []):
            attr = triple.get('attribute')
            val = triple.get('value')
            if isinstance(val, dict): val = val.get('value', '')
            attrs[attr] = val

        # Store Drug
        if entity_id in all_drug_ids:
            pipeline.hset("pharma:entities", entity_id, json.dumps(entity))
            pipeline.sadd("pharma:drugs", entity_id)
            drug_count += 1
            
            # Enrichment
            drug_name = attrs.get(name_attr_id, '').lower().strip()
            set_id = None
            for v in attrs.values():
                if isinstance(v, str) and uuid_pattern.match(v):
                    set_id = v
                    break
            
            extra = enhanced_metadata.get(set_id, {}) if set_id else {}
            if extra: matched_count += 1
            else: missed_count += 1
            
            pipeline.hset("pharma:enhanced_drugs", entity_id, json.dumps({
                "name": drug_name,
                "set_id": set_id or "",
                "entity_id": entity_id,
                "nda": extra.get('nda', 'N/A'),
                "ndc": extra.get('ndc', 'N/A'),
                "ama_citation": extra.get('ama_citation', 'N/A'),
                "manufacturer": extra.get('manufacturer', 'Unknown')
            }))
            
            # Create links to sections
            if entity_id in relationship_targets:
                for section_id in relationship_targets[entity_id]:
                    pipeline.sadd(f"pharma:drug:{entity_id}:sections", section_id)
                    link_count += 1

        # Store Section
        elif entity_id in potential_section_ids:
            pipeline.hset("pharma:entities", entity_id, json.dumps(entity))
            pipeline.sadd("pharma:sections", entity_id)
            section_count += 1

        if (i + 1) % 10000 == 0:
            pipeline.execute()
            pipeline = redis_client.pipeline()
            print(f"Phase 2 Processed {i+1}/{len(entity_map)}... Drugs: {drug_count}, Sections: {section_count}")

    pipeline.execute()
    
    redis_client.set("pharma:loaded", "true")
    print(f"--- SUMMARY ---")
    print(f"Metadata Matched: {matched_count}")
    print(f"Metadata Missed: {missed_count}")
    print(f"✅ Loaded {drug_count} drugs, {section_count} sections.")
    print(f"✅ Created {link_count} links.")
    
    build_memory_index()
    return True

# Startup Event
@app.on_event("startup")
async def startup_event():
    """Load data on startup"""
    print("Starting Pharmaceutical Knowledge Graph API...")
    load_data_to_redis()
    print("API Ready!")


# API Endpoints

@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "name": "Pharmaceutical Knowledge Graph API",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "search": "/api/search/suggestions?q={query}",
            "drug": "/drug/{drug_id}",
            "section": "/section/{section_id}",
            "stats": "/api/stats"
        }
    }


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    """Get database statistics"""
    if not redis_client:
        raise HTTPException(status_code=500, detail="Redis not available")
    
    total_drugs = redis_client.scard("pharma:drugs")
    total_sections = redis_client.scard("pharma:sections")
    
    # Count links
    total_links = 0
    for key in redis_client.scan_iter("pharma:drug:*:sections"):
        total_links += redis_client.scard(key)
    
    return StatsResponse(
        total_drugs=total_drugs,
        total_sections=total_sections,
        total_links=total_links,
        enhanced_matched=redis_client.hlen("pharma:enhanced_drugs"),
        search_index_size=len(DRUG_SEARCH_INDEX)
    )


@app.get("/api/search/suggestions")
async def search_suggestions(q: str = Query(..., min_length=2)):
    """Get search suggestions for drug names"""
    q_lower = q.lower()
    suggestions = []
    
    for name, data in DRUG_SEARCH_INDEX.items():
        if q_lower in name:
            suggestions.append({
                "id": data["id"],
                "name": data["name"],
                "set_id": data["set_id"]
            })
            if len(suggestions) >= 10:
                break
    
    return {"suggestions": suggestions}


@app.get("/drug/{drug_id}", response_model=DrugDetail)
async def get_drug_details(drug_id: str):
    """Get full details for a drug including all sections"""
    if not redis_client:
        raise HTTPException(status_code=500, detail="Redis not available")
    
    # Get enhanced drug data
    drug_data = redis_client.hget("pharma:enhanced_drugs", drug_id)
    if not drug_data:
        raise HTTPException(status_code=404, detail="Drug not found")
    
    drug = json.loads(drug_data)
    
    # Get section IDs
    section_ids = redis_client.smembers(f"pharma:drug:{drug_id}:sections")
    
    # Get section summaries
    sections = []
    for sid in section_ids:
        section_raw = redis_client.hget("pharma:entities", sid)
        if section_raw:
            section_entity = json.loads(section_raw)
            
            # Extract attributes
            section_attrs = {}
            for triple in section_entity.get('triples', []):
                attr = triple.get('attribute', '')
                val = triple.get('value', {})
                section_attrs[attr] = val.get('value', '') if isinstance(val, dict) else str(val)
            
            # Find title (shortest meaningful value)
            title = "Unknown"
            for v in section_attrs.values():
                if v and 5 < len(str(v)) < 100 and not uuid_pattern.match(str(v)):
                    title = str(v)
                    break
            
            # Find content preview
            content_preview = ""
            content_values = [v for v in section_attrs.values() if v and len(str(v)) > 100]
            if content_values:
                content_preview = str(max(content_values, key=len))[:200] + "..."
            
            # Determine section type from title
            section_type = "UNKNOWN"
            title_lower = title.lower()
            section_keywords = {
                'indications': 'INDICATIONS_AND_USAGE',
                'dosage': 'DOSAGE_AND_ADMINISTRATION',
                'contraindications': 'CONTRAINDICATIONS',
                'warnings': 'WARNINGS_AND_PRECAUTIONS',
                'adverse': 'ADVERSE_REACTIONS',
                'interactions': 'DRUG_INTERACTIONS',
                'pregnancy': 'USE_IN_SPECIFIC_POPULATIONS',
                'pediatric': 'USE_IN_SPECIFIC_POPULATIONS',
                'geriatric': 'USE_IN_SPECIFIC_POPULATIONS',
                'overdosage': 'OVERDOSAGE',
                'description': 'DESCRIPTION',
                'clinical pharmacology': 'CLINICAL_PHARMACOLOGY',
                'mechanism': 'CLINICAL_PHARMACOLOGY',
                'pharmacokinetics': 'CLINICAL_PHARMACOLOGY',
                'nonclinical': 'NONCLINICAL_TOXICOLOGY',
                'carcinogenesis': 'NONCLINICAL_TOXICOLOGY',
                'clinical studies': 'CLINICAL_STUDIES',
                'supplied': 'HOW_SUPPLIED',
                'patient counseling': 'PATIENT_COUNSELING_INFORMATION',
                'boxed': 'BOXED_WARNING',
                'warning:': 'BOXED_WARNING'
            }
            
            for keyword, stype in section_keywords.items():
                if keyword in title_lower:
                    section_type = stype
                    break
            
            sections.append(SectionSummary(
                section_id=sid,
                section_type=section_type,
                title=title,
                content_preview=content_preview
            ))
    
    # Sort sections
    def section_sort_key(s):
        type_order = {
            'BOXED_WARNING': 0,
            'INDICATIONS_AND_USAGE': 1,
            'DOSAGE_AND_ADMINISTRATION': 2,
            'DOSAGE_FORMS_AND_STRENGTHS': 3,
            'CONTRAINDICATIONS': 4,
            'WARNINGS_AND_PRECAUTIONS': 5,
            'ADVERSE_REACTIONS': 6,
            'DRUG_INTERACTIONS': 7,
            'USE_IN_SPECIFIC_POPULATIONS': 8,
            'OVERDOSAGE': 9,
            'DESCRIPTION': 10,
            'CLINICAL_PHARMACOLOGY': 11,
            'NONCLINICAL_TOXICOLOGY': 12,
            'CLINICAL_STUDIES': 13,
            'HOW_SUPPLIED': 14,
            'PATIENT_COUNSELING_INFORMATION': 15
        }
        return type_order.get(s.section_type, 99)
    
    sections.sort(key=section_sort_key)
    
    return DrugDetail(
        drug_id=drug_id,
        name=drug.get('name', 'Unknown').title(),
        set_id=drug.get('set_id', 'N/A'),
        nda=drug.get('nda', 'N/A'),
        ndc=drug.get('ndc', 'N/A'),
        manufacturer=drug.get('manufacturer', 'Unknown'),
        ama_citation=drug.get('ama_citation', 'N/A'),
        sections=sections,
        section_count=len(sections)
    )


@app.get("/debug/section/{section_id}")
async def debug_section(section_id: str):
    """Debug endpoint to see raw section attributes"""
    if not redis_client:
        raise HTTPException(status_code=500, detail="Redis not available")
    
    section_raw = redis_client.hget("pharma:entities", section_id)
    if not section_raw:
        raise HTTPException(status_code=404, detail="Section not found")
    
    section_entity = json.loads(section_raw)
    
    # Extract all attributes with their IDs
    attrs = {}
    for triple in section_entity.get('triples', []):
        attr = triple.get('attribute', 'unknown')
        val = triple.get('value', {})
        if isinstance(val, dict):
            attrs[attr] = val.get('value', '')
        else:
            attrs[attr] = str(val)
    
    return {
        "section_id": section_id,
        "attributes": attrs,
        "raw_triples": section_entity.get('triples', [])
    }


@app.get("/section/{section_id}", response_model=SectionDetail)
async def get_section_details(section_id: str):
    """Get full details of a specific section"""
    if not redis_client:
        raise HTTPException(status_code=500, detail="Redis not available")
    
    section_raw = redis_client.hget("pharma:entities", section_id)
    if not section_raw:
        raise HTTPException(status_code=404, detail="Section not found")
    
    section_entity = json.loads(section_raw)
    
    # Extract all attributes
    section_attrs = {}
    for triple in section_entity.get('triples', []):
        attr = triple.get('attribute', '')
        val = triple.get('value', {})
        section_attrs[attr] = val.get('value', '') if isinstance(val, dict) else str(val)

    # Find content (longest value)
    content = "No content available"
    content_values = [v for v in section_attrs.values() if v and len(str(v)) > 100]
    if content_values:
        content = max(content_values, key=len)

    # Find title (shortest meaningful value that isn't an ID)
    title = "Unknown Title"
    title_candidates = [v for v in section_attrs.values() if v and 5 < len(str(v)) < 100]
    if title_candidates:
        for v in title_candidates:
            if not uuid_pattern.match(str(v)) and not str(v).isdigit():
                title = str(v)
                break

    # Determine section type from title
    section_type = "UNKNOWN"
    title_lower = title.lower()
    section_keywords = {
        'indications': 'INDICATIONS_AND_USAGE',
        'dosage': 'DOSAGE_AND_ADMINISTRATION',
        'contraindications': 'CONTRAINDICATIONS',
        'warnings': 'WARNINGS_AND_PRECAUTIONS',
        'adverse': 'ADVERSE_REACTIONS',
        'interactions': 'DRUG_INTERACTIONS',
        'pregnancy': 'USE_IN_SPECIFIC_POPULATIONS',
        'pediatric': 'USE_IN_SPECIFIC_POPULATIONS',
        'geriatric': 'USE_IN_SPECIFIC_POPULATIONS',
        'overdosage': 'OVERDOSAGE',
        'description': 'DESCRIPTION',
        'clinical pharmacology': 'CLINICAL_PHARMACOLOGY',
        'mechanism': 'CLINICAL_PHARMACOLOGY',
        'pharmacokinetics': 'CLINICAL_PHARMACOLOGY',
        'nonclinical': 'NONCLINICAL_TOXICOLOGY',
        'carcinogenesis': 'NONCLINICAL_TOXICOLOGY',
        'clinical studies': 'CLINICAL_STUDIES',
        'supplied': 'HOW_SUPPLIED',
        'patient counseling': 'PATIENT_COUNSELING_INFORMATION',
        'boxed': 'BOXED_WARNING',
        'warning:': 'BOXED_WARNING'
    }
    
    for keyword, stype in section_keywords.items():
        if keyword in title_lower:
            section_type = stype
            break

    # Get provenance hash
    prov_hash = section_id[:16]
    for attr_id, val in section_attrs.items():
        if isinstance(val, str) and uuid_pattern.match(val) and val != section_id:
            prov_hash = val[:16]
            break

    return SectionDetail(
        section_id=section_id,
        section_type=section_type,
        title=title,
        content=content,
        provenance=ProvenanceData(
            fda_document_id=section_id,
            drug_name="",
            set_id="",
            section_type=section_type,
            title=title,
            citation=f"Hash: {prov_hash}",
            type="section"
        )
    )


# Health Check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "redis": "connected" if redis_client else "disconnected"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
