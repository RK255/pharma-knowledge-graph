# Pharmaceutical Knowledge Graph

A production-grade pharmaceutical knowledge graph with 100% data provenance, 
expert-curated clinical weights, and real-time graph database queries.

## Architecture
│ pipeline/ Data ingestion stages (01-10) │
│ backend/ FastAPI + Neo4j + Redis │
│ frontend/ React + TypeScript + Tailwind │
│ tools/ Utility scripts │
## Components

### Pipeline (`pipeline/`)

| Stage | Directory | Description |
|-------|-----------|-------------|
| 01 | 01_dailymed | Parse FDA SPL XML files |
| 02 | 02_rxnorm | Load RxNorm terminology |
| 03 | 03_ndc_bridge | Bridge NDC to RxNorm |
| 04 | 04_pubchem | Enrich with PubChem data |
| 05 | 05_enrichment | Additional enrichment |
| 06 | 06_loaders | Load data into Neo4j/Redis |
| 07 | 07_api | API endpoints |
| 08 | 08_clinical_weights | Expert-curated weights |
| 09 | 09_drug_interactions | Drug interaction extraction |
| 10 | 10_pharmacological_classes | Drug-class relationships |

### Backend (`backend/`)

| File | Purpose |
|------|---------|
| `main_v3_hybrid_v2.py` | FastAPI server (port 8002) |
| `graph_weights_admin.py` | Clinical weights management |
| `graph_clinical_knowledge.py` | Knowledge graph queries |
| `llm_chat.py` | LLM integration for queries |
| `admin_routes_graph.py` | Admin API routes |

### Frontend (`frontend/`)

React + TypeScript UI with:
- Drug search with autocomplete
- Detailed drug information views
- Provenance visualization
- Clinical weight management

## Quick Start

```bash
# Start Neo4j
docker start neo4j-server

# Start Redis
docker start redis-server

# Start backend
cd backend
python main_v3_hybrid_v2.py

# Start frontend
cd frontend
npm start

Data Sources

    FDA SPL (DailyMed): 107K drug labels
    RxNorm: Drug terminology
    PubChem: Chemical structures
    NDC Directory: Product codes

Stats

    82,948 drugs indexed
    1,318 ingredients classified
    400 pharmacological classes
    100% data provenance

Troubleshooting
Neo4j Permission Issues

If you encounter permission errors with Neo4j:
bash

# Create shared group
sudo groupadd docker_shared
sudo usermod -a -G docker_shared \$USER

# Fix permissions
sudo chown -R \$USER:docker_shared ../data/
sudo chmod -R 775 ../data/
sudo chmod -R g+s ../data/

# Log out and back in for group changes to take effect

License

Private repository - All rights reserved
