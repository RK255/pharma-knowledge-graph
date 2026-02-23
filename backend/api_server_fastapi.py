# api_server_fastapi.py
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import redis
import json
import os
from contextlib import asynccontextmanager

# --- Pydantic Models for Request/Response Validation ---
# This is the "magic" of FastAPI/Pydantic. It defines your data contract.
class SectionResult(BaseModel):
    drug_name: str
    section_title: str
    provenance_hash: str

class SectionSearchResponse(BaseModel):
    status: str = Field(default="found", description="The status of the search request.")
    query_section_type: str = Field(..., description="The section type that was searched for.")
    total_results: int = Field(..., description="The number of drugs found with this section type.")
    results: List[SectionResult]

class ProvenanceData(BaseModel):
    fda_document_id: str
    drug_name: str
    set_id: str
    section_type: str
    title: str
    citation: str
    type: str # "section" or "chunk"

class ProvenanceLookupResponse(BaseModel):
    status: str = Field(default="found", description="The status of the lookup request.")
    provenance_hash: str = Field(..., description=" The 16-character hash that was looked up.")
    data: ProvenanceData

class NotFoundResponse(BaseModel):
    status: str = Field(default="not_found", description="The status of the lookup request.")
    error: str = Field(..., description="A message indicating the hash was not found.")

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    provenance_entries: int
    indexed_drugs: int

class DrugSection(BaseModel):
    section_type: str
    title: str
    content_preview: str = Field(..., description="First 200 characters of the title.")
    provenance_hash: str

class DrugResponse(BaseModel):
    status: str = Field(default="found", description="The status of the lookup request.")
    drug_name: str = Field(..., description="The name of the drug that was searched for.")
    total_sections: int = Field(..., description="The total number of sections found for this drug.")
    sections: List[DrugSection]

class SearchResult(BaseModel):
    drug_name: str
    relevance_score: int = Field(..., description="A simple score based on match type (1=exact, 2=partial).")

class SearchResponse(BaseModel):
    status: str = Field(default="found", description="The status of the search request.")
    query: str = Field(..., description="The search term that was used.")
    total_results: int = Field(..., description="The number of drugs found.")
    results: List[SearchResult]

# --- In-memory data store ---
# This will hold the drug data for fast searching
drug_data_index: Dict[str, List[Dict[str, Any]]] = {}

# --- Lifespan event handler to load data on startup ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Load the main JSON file into memory on startup for fast searching.
    This creates an index from drug name to a list of its sections.
    """
    global drug_data_index
    print("Startup: Loading drug data index...")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, "output")
    input_path = os.path.join(output_dir, "enhanced_chunked_documents.json")
    
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            documents = json.load(f)
        
        for doc in documents:
            drug_name = doc.get('title', '').lower()
            if not drug_name:
                continue
            
            if drug_name not in drug_data_index:
                drug_data_index[drug_name] = []
            
            for section in doc.get('sections', []):
                # Create a lightweight object for our index
                drug_data_index[drug_name].append({
                    "section_type": section.get("section_type"),
                    "title": section.get("title"),
                    "content": section.get("content"),
                    "provenance_hash": section.get("provenance_hash")
                })
        
        print(f"Startup: Successfully loaded index for {len(drug_data_index)} drugs.")
        yield
    except FileNotFoundError:
        print(f"CRITICAL ERROR: Could not find {input_path}. The drug search endpoint will not work.")
        yield
    except Exception as e:
        print(f"CRITICAL ERROR during startup: {e}")
        yield
    
    print("Shutdown: Application stopping.")


# --- Initialize the FastAPI app ---
app = FastAPI(
    title="Pharmaceutical Knowledge Graph API",
    description="A high-performance API for accessing verifiable pharmaceutical information with complete provenance tracking.",
    version="1.0.0",
    lifespan=lifespan
)

# --- Redis Connection (Singleton pattern for production) ---
redis_connection = None

def get_redis_connection():
    global redis_connection
    if redis_connection is None:
        REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
        REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
        REDIS_DB = int(os.environ.get('REDIS_DB', 0))
        try:
            redis_connection = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
            redis_connection.ping()
        except redis.exceptions.ConnectionError as e:
            print(f"FATAL: Could not connect to Redis at {REDIS_HOST}:{REDIS_PORT}.")
            raise e
    return redis_connection

# --- API Endpoints ---

@app.get("/", response_model=HealthResponse, tags=["General"])
async def health_check():
    """
    Provides a health check and basic information about the API service.
    """
    r = get_redis_connection()
    entry_count = r.dbsize()
    return HealthResponse(
        status="ok",
        service="Pharmaceutical Knowledge Graph API",
        version="1.0.0",
        provenance_entries=entry_count,
        indexed_drugs=len(drug_data_index)
    )

@app.get("/lookup/{provenance_hash}", response_model=ProvenanceLookupResponse, tags=["Provenance Lookup"])
async def lookup_hash(provenance_hash: str):
    """
    Look up a provenance hash in Redis and return the full data associated with it.

    - **provenance_hash**: The 16-character hash to retrieve.
    """
    r = get_redis_connection()
    data_json = r.get(provenance_hash)

    if data_json:
        data_dict = json.loads(data_json)
        # Pydantic automatically validates the data against the ProvenanceData model
        provenance_data = ProvenanceData(**data_dict)
        return ProvenanceLookupResponse(
            provenance_hash=provenance_hash,
            data=provenance_data
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hash '{provenance_hash}' not found in Redis."
        )

@app.get("/search", response_model=SearchResponse, tags=["Drug Search"])
async def search_drugs(query: str):
    """
    Search for drugs by name. This is a fuzzy search that will find partial matches
    and combination products. The search is case-insensitive.
    """
    query_lower = query.lower()
    found_results = []

    # Iterate through all drug names in our index
    for drug_name_in_index in drug_data_index.keys():
        # Check for an exact match first
        if query_lower == drug_name_in_index:
            found_results.append(SearchResult(drug_name=drug_name_in_index, relevance_score=1))
        # Check for a partial match (e.g., 'aspirin' is in 'butalbital, aspirin, and caffeine')
        elif query_lower in drug_name_in_index:
            found_results.append(SearchResult(drug_name=drug_name_in_index, relevance_score=2))

    if not found_results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No drugs found matching '{query}'."
        )
    
    # Sort results by relevance score
    found_results.sort(key=lambda x: x.relevance_score)

    return SearchResponse(
        query=query,
        total_results=len(found_results),
        results=found_results
    )

@app.get("/drug/{drug_name}", response_model=DrugResponse, tags=["Drug Search"])
async def get_drug_details(drug_name: str):
    """
    Find all sections for a given drug name and return them with full provenance.
    The search is case-insensitive. This endpoint is optimized for performance.
    """
    # Normalize the search key
    search_key = drug_name.lower()
    
    # Check our in-memory index
    if search_key not in drug_data_index:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drug '{drug_name}' not found in the index."
        )
    
    sections_from_index = drug_data_index[search_key]

@app.get("/section/{section_type}", response_model=SectionSearchResponse, tags=["Smart Query"])
async def find_section_type(section_type: str):
    """
    Find all drugs that contain a specific section type (e.g., BOXED_WARNING).
    This is a cross-drug analysis query.
    """
    results = []
    # Iterate through all drugs in our in-memory index
    for drug_name, sections in drug_data_index.items():
        # Iterate through the sections for each drug
        for section_info in sections:
            # Check if the section_type matches the query (case-insensitive)
            if section_info.get("section_type", "").lower() == section_type.lower():
                results.append(SectionResult(
                    drug_name=drug_name.title(), # Return a nicely formatted name
                    section_title=section_info.get("title", ""),
                    provenance_hash=section_info.get("provenance_hash")
                ))
                # We found a match for this drug, so we can stop searching its other sections
                break

    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No drugs found with section type '{section_type}'."
        )
    
    return SectionSearchResponse(
        query_section_type=section_type.upper(),
        total_results=len(results),
        results=results
    )
    
    # --- OPTIMIZATION: Collect all hashes first ---
    provenance_hashes = [section_info["provenance_hash"] for section_info in sections_from_index]
    
    # --- OPTIMIZATION: Use MGET for a single, fast Redis call ---
    r = get_redis_connection()
    # MGET returns a list of values in the same order as the keys
    # It returns None for keys that don't exist
    redis_results = r.mget(*provenance_hashes)

    final_sections = []
    # Iterate through the results to build the response
    for i, data_json in enumerate(redis_results):
        if data_json:
            data_dict = json.loads(data_json)
            provenance_data = ProvenanceData(**data_dict)
            
            final_sections.append(DrugSection(
                section_type=provenance_data.section_type,
                title=provenance_data.title,
                content_preview=provenance_data.title[:200],
                provenance_hash=provenance_hashes[i] # Get hash from our original list
            ))
        else:
            # This should not happen if the index is in sync with Redis
            print(f"Warning: Hash {provenance_hashes[i]} found in index but not in Redis.")
    
    return DrugResponse(
        drug_name=drug_name,
        total_sections=len(final_sections),
        sections=final_sections
    )

# --- Run the Server (for development) ---
if __name__ == "__main__":
    # Use Uvicorn to run the app
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
