import os
import json
import redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from typing import List, Dict, Optional
import uvicorn

# --- Configuration ---
DATA_FILE_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/development/output/grc20_pharmaceutical_data_v10.json"
ENHANCED_DATA_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/development/output/enhanced_chunked_documents.json"

# --- GRC-20 IDs ---
# Attributes
ATTRIBUTES = {
    "name": "LuBWqZAu6pz54eiJS5mLv8",
    "type": "Jfmby78N4BCseZinBmdVov",
    "description": "LA1DqP5v6QAdsgLPXGF3YA",
    "content": "LA1DqP5v6QAdsgLPXGF3YA",  # Usually same as description for sections
    "fda_set_id": "7gzF671tq5JTZ13naG4tnr", # Example ID, verify if needed
    "provenance_hash": "WQfdWjboZWFuTseDhG5Cw1",
    "section_type": "AdBRTCMrQjrnFvejKSUM5x"
}

# Types
TYPE_IDS = {
    "drug": "CzNrWVPayq5EB1HXncQFD5",
    "section": "6YqL5N3vRjFyHc9XzKwE2M", # Example, verify from your data
    "type": "Jfmby78N4BCseZinBmdVov"
}

# Reverse mapping for human-readable keys
ID_TO_NAME = {v: k for k, v in ATTRIBUTES.items()}
VALUE_MAP = {
    TYPE_IDS.get("drug"): "Drug",
    TYPE_IDS.get("section"): "Section"
}

# Section Ordering (FDA Standard)
SECTION_ORDER = {
    'BOXED_WARNINGS': 0,
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
    'REFERENCES': 14,
    'HOW_SUPPLIED': 15,
    'PATIENT_COUNSELING_INFORMATION': 16,
    'SPL': 17,
    'UNKNOWN': 99
}

# --- Redis Setup ---
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Check connection
try:
    redis_client.ping()
    print("✅ Connected to Redis")
except redis.ConnectionError:
    print("❌ Redis not running. Please start Redis.")
    redis_client = None

# --- Models ---
class DrugSection(BaseModel):
    section_type: str
    title: str
    content_preview: str
    provenance_hash: str
    section_id: str

class ProvenanceData(BaseModel):
    fda_document_id: str
    drug_name: str = ""
    set_id: str = ""
    section_type: str = ""
    title: str = ""
    citation: str = ""
    type: str = "section"

class SectionDetail(BaseModel):
    section_id: str
    section_type: str
    title: str
    content: str
    provenance: ProvenanceData

class DrugResponse(BaseModel):
    status: str
    drug_name: str
    set_id: str
    total_sections: int
    sections: List[DrugSection]
    metadata: Dict[str, str] = {}

class SuggestionResponse(BaseModel):
    suggestions: List[Dict[str, str]]

# --- In-Memory Search Index ---
DRUG_SEARCH_INDEX = {}

def build_memory_index():
    global DRUG_SEARCH_INDEX
    DRUG_SEARCH_INDEX = {}
    if not redis_client: return
    
    print("Building in-memory search index...")
    count = 0
    # Iterate over the enhanced_drugs hash for faster loading
    for entity_id, data_str in redis_client.hscan_iter("pharma:enhanced_drugs"):
        try:
            data = json.loads(data_str)
            name = data.get('name')
            if name:
                # Simple index: lowercase name -> entity_id
                # Stores the first match (or you could handle duplicates here)
                if name not in DRUG_SEARCH_INDEX:
                    DRUG_SEARCH_INDEX[name] = {
                        "id": entity_id,
                        "name": name.title(),
                        "set_id": data.get('set_id', '')
                    }
                    count += 1
        except Exception as e:
            continue
            
    print(f"✅ Search index built with {count} drugs")


# --- Data Loader ---
def load_data_to_redis():
    global DRUG_SEARCH_INDEX
    
    if not redis_client:
        return False
    
    if redis_client.exists("pharma:loaded"):
        print("✅ Data already in Redis. Loading search index into memory...")
        build_memory_index()
        return True

    # --- Helper: Strict UUID Check ---
    import re
    uuid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')

    # 1. Load Enhanced Metadata
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

    # 2. Load GRC-20 Entities
    print(f"Loading GRC-20 data from {DATA_FILE_PATH}...")
    if not os.path.exists(DATA_FILE_PATH):
        print(f"❌ ERROR: Data file not found at {DATA_FILE_PATH}")
        return False

    with open(DATA_FILE_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    entities = data.get('entities', [])
    total_entities = len(entities)
    print(f"Processing {total_entities} entities...")

    # --- PHASE 1: IDENTIFY DRUG NODES ---
    print("Phase 1: Identifying Drug Nodes...")
    
    all_drug_ids = set()
    name_attr_id = None
    
    for i, entity in enumerate(entities):
        entity_id = entity.get('id')
        if not entity_id: continue
        
        # Check attributes for a UUID (Set ID)
        for triple in entity.get('triples', []):
            val = triple.get('value')
            if isinstance(val, dict): val = val.get('value', '')
            if isinstance(val, str) and uuid_pattern.match(val):
                all_drug_ids.add(entity_id) # Store the ENTITY ID
                break
            
            # Detect name attribute
            if not name_attr_id and isinstance(val, str) and len(val) > 0 and len(val) < 100:
                name_attr_id = triple.get('attribute')

        if (i + 1) % 100000 == 0:
            print(f"Phase 1 Scanned {i+1}/{total_entities}... (Found {len(all_drug_ids)} Drugs)")

    print(f"Phase 1 Complete. Found {len(all_drug_ids)} Drug Nodes.")

    # --- PHASE 2: STORE DRUGS & IDENTIFY SECTIONS ---
    # If an entity points to a Drug, IT IS A SECTION.
    print("Phase 2: Storing Drugs and Discovering Sections...")
    
    pipeline = redis_client.pipeline()
    drug_count = 0
    section_count = 0
    link_count = 0
    matched_count = 0
    missed_count = 0
    
    for i, entity in enumerate(entities):
        entity_id = entity.get('id')
        if not entity_id: continue
        
        # Extract attributes
        attrs = {}
        for triple in entity.get('triples', []):
            attr = triple.get('attribute')
            val = triple.get('value')
            if isinstance(val, dict): val = val.get('value', '')
            attrs[attr] = val

        # 1. Handle Drug Nodes
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

        # 2. Handle Sections (Entities that point to Drugs)
        else:
            # Check if this entity points to a Drug
            found_drug_id = None
            
            for v in attrs.values():
                if isinstance(v, str) and v in all_drug_ids:
                    found_drug_id = v
                    break
            
            if found_drug_id:
                # THIS ENTITY IS A SECTION
                pipeline.hset("pharma:entities", entity_id, json.dumps(entity))
                pipeline.sadd("pharma:sections", entity_id)
                section_count += 1
                
                # Create Link
                redis_key = f"pharma:drug:{found_drug_id}:sections"
                pipeline.sadd(redis_key, entity_id)
                link_count += 1

        if (i + 1) % 5000 == 0:
            pipeline.execute()
            pipeline = redis_client.pipeline()
            print(f"Phase 2 Processed {i+1}/{total_entities}... Drugs: {drug_count}, Sections: {section_count}")

    pipeline.execute()
    
    redis_client.set("pharma:loaded", "true")
    print(f"--- SUMMARY ---")
    print(f"Metadata Matched: {matched_count}")
    print(f"Metadata Missed: {missed_count}")
    print(f"✅ Loaded {drug_count} drugs, {section_count} sections.")
    print(f"✅ Created {link_count} links.")
    
    build_memory_index()
    return True

# --- App Setup ---
app = FastAPI(title="Pharma Knowledge Graph API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    load_data_to_redis()

# --- Endpoints ---

@app.get("/health")
async def health_check():
    return {"status": "healthy", "redis": "connected" if redis_client else "disconnected"}

@app.get("/api/search/suggestions", response_model=SuggestionResponse)
async def get_suggestions(q: str):
    if not redis_client:
        raise HTTPException(status_code=500, detail="Redis not available")
    
    q = q.lower().strip()
    suggestions = []
    
    for name, data in DRUG_SEARCH_INDEX.items():
        if name.startswith(q):
            suggestions.append(data)
            if len(suggestions) >= 10:
                break
                
    return {"suggestions": suggestions}

@app.get("/drug/{entity_id}", response_model=DrugResponse)
async def get_drug_details(entity_id: str):
    if not redis_client:
        raise HTTPException(status_code=500, detail="Redis not available")
    
    # 1. Get Drug Info
    drug_data_raw = redis_client.hget("pharma:enhanced_drugs", entity_id)
    
    if not drug_data_raw:
         raise HTTPException(status_code=404, detail="Drug not found")
    
    drug_info = json.loads(drug_data_raw)
    drug_name = drug_info.get('name', '')
    set_id = drug_info.get('set_id', '')
    
    # DEBUG PRINT
    print(f"--- DEBUG: Fetching sections for Drug: '{drug_name}' (Entity: {entity_id})")
    
    # 2. Get Sections (KEY FIX: Use entity_id, not drug_name)
    sections = []
    redis_key = f"pharma:drug:{entity_id}:sections"
    section_ids = redis_client.smembers(redis_key)
    print(f"--- DEBUG: Found {len(section_ids)} section IDs")

    for section_id in section_ids:
        section_raw = redis_client.hget("pharma:entities", section_id)
        if section_raw:
            section_entity = json.loads(section_raw)
            
            # Extract attributes
            section_attrs = {}
            for triple in section_entity.get('triples', []):
                attr = triple.get('attribute', '')
                val = triple.get('value', {})
                section_attrs[attr] = val.get('value', '') if isinstance(val, dict) else str(val)
            
            # Get content preview
            content_preview = section_attrs.get(ATTRIBUTES.get('content'), '')
            if not content_preview:
                 all_vals = list(section_attrs.values())
                 if all_vals:
                     content_preview = max(all_vals, key=len)

            # Get section type for sorting
            section_type = section_attrs.get(ATTRIBUTES.get('section_type'), 'UNKNOWN')
            
            sections.append({
                "section_type": section_type,
                "title": section_attrs.get(ATTRIBUTES.get('name'), 'No Title'),
                "content_preview": str(content_preview)[:200],
                "provenance_hash": section_attrs.get(ATTRIBUTES.get('provenance_hash'), section_id)[:16],
                "section_id": section_id,
                "sort_order": SECTION_ORDER.get(section_type, 99)
            })

    # Sort sections by FDA standard order
    sections.sort(key=lambda x: x['sort_order'])
    
    # 3. Prepare Metadata (Human Readable)
    # Fetch full entity to get all attributes for metadata display
    entity_raw = redis_client.hget("pharma:entities", entity_id)
    drug_attrs = {}
    if entity_raw:
        drug_entity = json.loads(entity_raw)
        for triple in drug_entity.get('triples', []):
            attr = triple.get('attribute', '')
            val = triple.get('value', {})
            drug_attrs[attr] = val.get('value', '') if isinstance(val, dict) else str(val)

    readable_metadata = {}
    for key, value in drug_attrs.items():
        readable_key = ID_TO_NAME.get(key, key)
        readable_value = VALUE_MAP.get(value, value)
        if readable_key == 'type' and readable_value == 'Drug Entity':
            continue
        readable_metadata[readable_key] = readable_value

    # Add Enriched Data
    readable_metadata['NDA/ANDA'] = drug_info.get('nda', 'N/A')
    readable_metadata['NDC Codes'] = drug_info.get('ndc', 'N/A')
    readable_metadata['Manufacturer'] = drug_info.get('manufacturer', 'Unknown')
    readable_metadata['AMA Citation'] = drug_info.get('ama_citation', 'N/A')

    return DrugResponse(
        status="found",
        drug_name=drug_name,
        set_id=set_id,
        total_sections=len(sections),
        sections=[DrugSection(**s) for s in sections],
        metadata=readable_metadata
    )

@app.get("/section/{section_id}", response_model=SectionDetail)
async def get_section_details(section_id: str):
    """Get full details of a specific section"""
    if not redis_client:
        raise HTTPException(status_code=500, detail="Redis not available")
    
    section_raw = redis_client.hget("pharma:entities", section_id)
    if not section_raw:
        raise HTTPException(status_code=404, detail="Section not found")
    
    section_entity = json.loads(section_raw)
    
    # 1. Extract all attributes first
    section_attrs = {}
    for triple in section_entity.get('triples', []):
        attr = triple.get('attribute', '')
        val = triple.get('value', {})
        section_attrs[attr] = val.get('value', '') if isinstance(val, dict) else str(val)

    # 2. SMART CONTENT DETECTION
    # Find the longest value in the attributes (this is usually the main content)
    content = "No content available"
    if section_attrs:
        # Filter out empty strings just in case
        valid_values = [v for v in section_attrs.values() if v]
        if valid_values:
            content = max(valid_values, key=len)

    # 3. SMART TITLE DETECTION
    title = section_attrs.get(ATTRIBUTES.get('name'), '')
    if not title:
        # Fallback: Find a short string that isn't the content
        for v in section_attrs.values():
            if len(v) < 100 and len(v) > 0 and v != content:
                title = v
                break
    
    if not title:
        title = "Unknown Title"
        
    # 4. Get Provenance Hash
    prov_hash = section_attrs.get(ATTRIBUTES.get('provenance_hash'), section_attrs.get('WQfdWjboZWFuTseDhG5Cw1', section_id))

    return SectionDetail(
        section_id=section_id,
        section_type=section_attrs.get(ATTRIBUTES.get('section_type'), 'UNKNOWN'),
        title=title,
        content=content,
        provenance=ProvenanceData(
            fda_document_id=section_id,
            drug_name="",
            set_id=section_attrs.get(ATTRIBUTES.get('fda_set_id'), 'N/A'),
            section_type=section_attrs.get(ATTRIBUTES.get('section_type'), 'UNKNOWN'),
            title=title,
            citation=f"Hash: {prov_hash}",
            type="section"
        )
    )

@app.get("/stats")
async def get_stats():
    if not redis_client:
        raise HTTPException(status_code=500, detail="Redis not available")
    
    return {
        "drug_count": redis_client.get("pharma:stats:drug_count") or 0,
        "section_count": redis_client.get("pharma:stats:section_count") or 0,
        "index_size": len(DRUG_SEARCH_INDEX)
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
