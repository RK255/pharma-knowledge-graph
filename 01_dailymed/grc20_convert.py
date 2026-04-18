#!/usr/bin/env python3
"""
GRC-20 DailyMed Converter
Converts DailyMed data to proper GRC-20 format
"""

import json
import os
import sys
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

# Import from schema and utils
sys.path.insert(0, str(Path(__file__).parent.parent / "00_schema"))
from pharma_schema import PharmaSchema, SECTION_RELATION_IDS

sys.path.insert(0, str(Path(__file__).parent))
from grc20_utils import generate_uuid, GRC20_VALUE_TYPES

# Initialize schema
schema = PharmaSchema()

# Property names we use from schema
PROPERTIES = {
    "name": schema.prop("name"),
    "description": schema.prop("description"),
    "content": schema.prop("content"),
    "section_type": schema.prop("section_type"),
    "loinc_code": schema.prop("loinc_code") if "loinc_code" in schema.properties else None,
    "effective_time": schema.prop("effective_time"),
    "ndc_code": schema.prop("ndc_code"),
    "rxcui": schema.prop("rxcui"),
    "fda_set_id": schema.prop("fda_set_id") if "fda_set_id" in schema.properties else None,
    "source": schema.prop("source"),
    "citation": schema.prop("citation"),
    "date_accessed": schema.prop("date_accessed"),
    "source_url": schema.prop("source_url"),
    "provenance_type": schema.prop("provenance_type"),
}

# Entity type IDs from schema
ENTITY_TYPES = {
    "PackageInsert": schema.type_id("PackageInsert"),
    "Section": schema.type_id("Section"),
    "Manufacturer": schema.type_id("Manufacturer"),
    "Provenance": schema.type_id("Provenance"),
    "NDC": schema.type_id("NDC"),
}

# Core relations from schema
RELATIONS = {
    "has_section": schema.relations.get("has_section"),
    "section_of": schema.relations.get("section_of"),
    "manufactured_by": schema.relations.get("manufactured_by"),
    "manufactures": schema.relations.get("manufactures"),
    "has_provenance": schema.relations.get("has_provenance"),
    "maps_to_rxcui": schema.relations.get("maps_to_rxcui"),
}

# Build section type to relation mapping from schema
SECTION_TYPE_TO_RELATION = {}
for rel_name, rel_id in SECTION_RELATION_IDS.items():
    # Map "has_adverse_reactions_section" -> "ADVERSE_REACTIONS"
    if rel_name.startswith("has_") and rel_name.endswith("_section"):
        section_type = rel_name[4:-8].upper()  # Remove "has_" and "_section"
        SECTION_TYPE_TO_RELATION[section_type] = {
            "forward": rel_id,
            "forward_name": rel_name,
            "inverse": SECTION_RELATION_IDS.get(rel_name.replace("has_", "") + "_of"),
            "inverse_name": rel_name.replace("has_", "") + "_of"
        }

# Manufacturer deduplication
MANUFACTURER_LOOKUP = {}

def create_value(property_name: str, value) -> dict:
    """Create a GRC-20 value for an entity's values array."""
    prop_id = PROPERTIES.get(property_name)
    if not prop_id or value is None:
        return None
    return {
        "property": prop_id,
        "value": str(value) if value is not None else ""
    }

def create_entity(entity_id: str, entity_type: str, name: str, values: list = None) -> dict:
    """Create a GRC-20 entity with proper structure."""
    type_id = ENTITY_TYPES.get(entity_type)
    if not type_id:
        print(f"WARNING: Unknown entity type: {entity_type}")
        return None
    
    entity = {
        "id": entity_id,
        "name": name,
        "types": [type_id],
        "values": values or []
    }
    return entity

def create_relation(relation_id: str, relation_type: str, from_id: str, to_id: str, position: str = None) -> dict:
    """Create a GRC-20 relation with proper structure."""
    type_id = RELATIONS.get(relation_type)
    if not type_id:
        print(f"WARNING: Unknown relation type: {relation_type}")
        return None
    
    relation = {
        "id": relation_id,
        "type": type_id,
        "from": from_id,
        "to": to_id
    }
    
    if position:
        relation["position"] = position
    
    return relation

def get_or_create_manufacturer(manufacturer_name: str) -> str:
    """Get or create a manufacturer entity, deduplicating by name."""
    if not manufacturer_name:
        return None
    
    normalized_name = manufacturer_name.strip().lower()
    
    if normalized_name in MANUFACTURER_LOOKUP:
        return MANUFACTURER_LOOKUP[normalized_name]
    
    entity_id = generate_uuid(seed=f"manufacturer:{normalized_name}")
    MANUFACTURER_LOOKUP[normalized_name] = entity_id
    
    return entity_id

def convert_document_to_grc20(doc: dict, provenance_id: str = None) -> tuple:
    """Convert a single DailyMed document to GRC-20 entities and relations.
    
    Returns:
        Tuple of (entities, relations) lists
    """
    entities = []
    relations = []
    
    # Extract document metadata
    set_id = doc.get("fda_set_id", "")
    title = doc.get("title", "")
    manufacturer = doc.get("manufacturer", "")
    effective_date = doc.get("effective_time", "")
    ndcs = doc.get("ndc_codes", [])
    application_number = doc.get("application_number", "")
    application_type = doc.get("application_type", "")
    sections = doc.get("sections", [])
    
    # Create PackageInsert entity
    package_insert_id = generate_uuid(seed=f"dailymed:{set_id}")
    
    values = []
    if title:
        values.append(create_value("name", title))
    if set_id:
        values.append(create_value("fda_set_id", set_id))
    if effective_date:
        values.append(create_value("effective_time", effective_date))
    
    package_insert = create_entity(
        entity_id=package_insert_id,
        entity_type="PackageInsert",
        name=title or f"Package Insert {set_id}",
        values=values
    )
    
    if package_insert:
        entities.append(package_insert)
    
    # Add provenance relation
    if provenance_id and RELATIONS.get("has_provenance"):
        rel = create_relation(
            relation_id=generate_uuid(seed=f"rel:prov:{package_insert_id}"),
            relation_type="has_provenance",
            from_id=package_insert_id,
            to_id=provenance_id
        )
        if rel:
            relations.append(rel)
    
    # Create Manufacturer entity and relation
    if manufacturer:
        manufacturer_id = get_or_create_manufacturer(manufacturer)
        if manufacturer_id and manufacturer_id not in [e["id"] for e in entities]:
            mfr_values = [create_value("name", manufacturer)]
            mfr_entity = create_entity(
                entity_id=manufacturer_id,
                entity_type="Manufacturer",
                name=manufacturer,
                values=mfr_values
            )
            if mfr_entity:
                entities.append(mfr_entity)
            
            # Add provenance relation
            if provenance_id:
                prov_rel = create_relation(
                    relation_id=generate_uuid(seed=f"prov:mfr:{manufacturer_id}"),
                    relation_type="has_provenance",
                    from_id=manufacturer_id,
                    to_id=provenance_id
                )
                if prov_rel:
                    relations.append(prov_rel)
        
        # Create manufactured_by relation
        if manufacturer_id and RELATIONS.get("manufactured_by"):
            rel = create_relation(
                relation_id=generate_uuid(seed=f"rel:mfr:{package_insert_id}:{manufacturer_id}"),
                relation_type="manufactured_by",
                from_id=package_insert_id,
                to_id=manufacturer_id
            )
            if rel:
                relations.append(rel)
    
    # Create NDC entities and relations
    for idx, ndc_code in enumerate(ndcs):
        if not ndc_code:
            continue
        
        ndc_id = generate_uuid(seed=f"ndc:{ndc_code}")
        ndc_values = [create_value("name", ndc_code)]
        ndc_code_val = create_value("ndc_code", ndc_code)
        if ndc_code_val:
            ndc_values.append(ndc_code_val)
        
        ndc_entity = create_entity(
            entity_id=ndc_id,
            entity_type="NDC",
            name=ndc_code,
            values=ndc_values
        )
        if ndc_entity:
            entities.append(ndc_entity)
        
        # Add provenance relation for NDC
        if provenance_id:
            prov_rel = create_relation(
                relation_id=generate_uuid(seed=f"prov:ndc:{ndc_code}"),
                relation_type="has_provenance",
                from_id=ndc_id,
                to_id=provenance_id
            )
            if prov_rel:
                relations.append(prov_rel)
        
        # Create relation from package insert to NDC
        # Using has_section as placeholder - could add proper has_ndc relation
        if RELATIONS.get("has_section"):
            rel = create_relation(
                relation_id=generate_uuid(seed=f"rel:ndc:{package_insert_id}:{ndc_code}"),
                relation_type="has_section",
                from_id=package_insert_id,
                to_id=ndc_id,
                position=str(idx)
            )
            if rel:
                relations.append(rel)
    
    # Create Section entities with typed relations
    for idx, section in enumerate(sections):
        section_type = section.get("section_type", "")
        section_title = section.get("title", "")
        section_content = section.get("content", "")
        section_loinc = section.get("loinc_code", "")
        section_unique_id = section.get("section_unique_id", "")
        
        if not section_type:
            continue
        
        # Use section_unique_id if available, otherwise generate from set_id + section_type
        if section_unique_id:
            section_id = section_unique_id
        else:
            section_id = generate_uuid(seed=f"section:{set_id}:{section_type}:{idx}")
        
        # Build section values
        section_values = []
        if section_title:
            section_values.append(create_value("name", section_title))
        if section_type:
            section_values.append(create_value("section_type", section_type))
        if section_loinc:
            section_values.append(create_value("loinc_code", section_loinc))
        if section_content:
            # Limit content size to prevent huge entities
            content_val = section_content[:50000] if len(section_content) > 50000 else section_content
            section_values.append(create_value("content", content_val))
        
        section_entity = create_entity(
            entity_id=section_id,
            entity_type="Section",
            name=section_title or section_type,
            values=section_values
        )
        
        if section_entity:
            entities.append(section_entity)
        
        # Add provenance relation
        if provenance_id:
            prov_rel = create_relation(
                relation_id=generate_uuid(seed=f"prov:sec:{section_id}"),
                relation_type="has_provenance",
                from_id=section_id,
                to_id=provenance_id
            )
            if prov_rel:
                relations.append(prov_rel)
        
        # Create section relation using typed relation if available
        relation_mapping = SECTION_TYPE_TO_RELATION.get(section_type, {})
        
        if relation_mapping:
            # Use typed relation (e.g., has_adverse_reactions_section)
            rel_id = relation_mapping["forward"]
            rel = {
                "id": generate_uuid(seed=f"rel:sec:{package_insert_id}:{section_type}"),
                "type": rel_id,
                "from": package_insert_id,
                "to": section_id,
                "position": str(idx)
            }
            relations.append(rel)
        elif RELATIONS.get("has_section"):
            # Fallback to generic has_section
            rel = create_relation(
                relation_id=generate_uuid(seed=f"rel:sec:{package_insert_id}:{section_type}"),
                relation_type="has_section",
                from_id=package_insert_id,
                to_id=section_id,
                position=str(idx)
            )
            if rel:
                relations.append(rel)
    
    return entities, relations

def convert_dataset_to_grc20(input_path: str, output_path: str, progress=None) -> dict:
    """Convert entire DailyMed dataset to GRC-20 format.
    
    Args:
        input_path: Path to parsed DailyMed JSON
        output_path: Path for output JSON
        progress: Optional progress callback
    
    Returns:
        Tuple of (entities, relations, stats)
    """
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Loading parsed data from {input_path}")
    
    with open(input_path, 'r') as f:
        documents = json.load(f)
    
    print(f"Loaded {len(documents)} documents")
    
    # Create provenance entity
    provenance_entity = schema.create_provenance_entity("DailyMed")
    provenance_id = provenance_entity["id"]
    print(f"  DailyMed provenance ID: {provenance_id}")
    
    all_entities = [provenance_entity]
    all_relations = []
    
    stats = {
        "total_documents": len(documents),
        "entities_by_type": {"Provenance": 1},
        "relations_by_type": {}
    }
    
    # Process each document
    for i, doc in enumerate(documents):
        if progress and i % 100 == 0:
            progress.report(i / len(documents), f"Converting document {i+1}/{len(documents)}")
        
        entities, relations = convert_document_to_grc20(doc, provenance_id)
        
        for entity in entities:
            all_entities.append(entity)
            # Get type name
            type_id = entity.get("types", [None])[0]
            type_name = "Unknown"
            for name, tid in ENTITY_TYPES.items():
                if tid == type_id:
                    type_name = name
                    break
            stats["entities_by_type"][type_name] = stats["entities_by_type"].get(type_name, 0) + 1
        
        for relation in relations:
            all_relations.append(relation)
            # Get relation type name
            type_id = relation.get("type", "Unknown")
            type_name = "Unknown"
            for name, tid in RELATIONS.items():
                if tid == type_id:
                    type_name = name
                    break
            # Also check section relations
            if type_name == "Unknown":
                for name, tid in SECTION_RELATION_IDS.items():
                    if tid == type_id:
                        type_name = name
                        break
            stats["relations_by_type"][type_name] = stats["relations_by_type"].get(type_name, 0) + 1
    
    stats["total_entities"] = len(all_entities)
    stats["total_relations"] = len(all_relations)
    
    # Write outputs
    entities_path = output_dir / "dailymed_entities.jsonl"
    relations_path = output_dir / "dailymed_relations.jsonl"
    
    with open(entities_path, 'w') as f:
        for entity in all_entities:
            f.write(json.dumps(entity) + '\n')
    
    with open(relations_path, 'w') as f:
        for relation in all_relations:
            f.write(json.dumps(relation) + '\n')
    
    print(f"Wrote {len(all_entities)} entities to {entities_path}")
    print(f"Wrote {len(all_relations)} relations to {relations_path}")
    
    return all_entities, all_relations, stats

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Convert DailyMed data to GRC-20 format")
    parser.add_argument("--input", required=True, help="Input JSON file path")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    
    args = parser.parse_args()
    
    entities, relations, stats = convert_dataset_to_grc20(args.input, args.output)
    
    print("\nConversion complete!")
    print(f"  Total entities: {len(entities)}")
    print(f"  Total relations: {len(relations)}")
    print("\nEntities by type:")
    for type_name, count in sorted(stats["entities_by_type"].items()):
        print(f"  {type_name}: {count}")
    print("\nRelations by type:")
    for rel_name, count in sorted(stats["relations_by_type"].items()):
        print(f"  {rel_name}: {count}")
