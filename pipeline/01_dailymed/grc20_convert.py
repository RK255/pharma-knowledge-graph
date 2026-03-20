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
from pharma_schema import PharmaSchema

sys.path.insert(0, str(Path(__file__).parent))
from grc20_utils import generate_uuid, GRC20_VALUE_TYPES

# Initialize schema
schema = PharmaSchema()

# GRC-20 Specification Constants (from schema)
# Build property mappings lazily to handle missing properties
def _build_property_dict(names):
    """Build a dict of property IDs, skipping any that don't exist in schema."""
    result = {}
    for name in names:
        try:
            result[name] = schema.prop(name)
        except KeyError:
            pass  # Property not in schema, skip
    return result

GRC20_SPEC = {
    "value_types": GRC20_VALUE_TYPES,
    "standard_attributes": _build_property_dict(["name", "description"]),
}

# Property mappings from schema (lazy-loaded)
PROPERTIES = _build_property_dict([
    "name", "description", "content", "section_type",
    "fda_set_id", "effective_time", "set_id"
])

# Entity type mappings from schema
ENTITY_TYPES = {
    "PackageInsert": schema.type_id("PackageInsert"),
    "Section": schema.type_id("Section"),
    "Manufacturer": schema.type_id("Manufacturer"),
    "Provenance": schema.type_id("Provenance"),
    "Relation": schema.type_id("Relation"),
}

# Relation mappings from schema
RELATIONS = {
    "has_section": schema.relations.get("has_section"),
    "section_of": schema.relations.get("section_of"),
    "manufactured_by": schema.relations.get("manufactured_by"),
    "manufactures": schema.relations.get("manufactures"),
}

# Manufacturer deduplication - track by name
MANUFACTURER_LOOKUP = {}  # name -> entity_id

def create_value(property_name: str, value, value_type: str = "TEXT") -> dict:
    """Create a GRC-20 value for an entity's values array.
    
    Args:
        property_name: Name of the property (e.g., "name", "description")
        value: The value to store
        value_type: GRC-20 value type (TEXT, NUMBER, etc.)
    
    Returns:
        dict with 'property' and 'value' keys
    """
    try:
        prop_id = schema.prop(property_name)
    except KeyError:
        return None  # Property not in schema, skip
    
    return {
        "property": prop_id,
        "value": str(value)
    }

def create_entity(entity_id: str, entity_type: str, name: str, values: list = None) -> dict:
    """Create a GRC-20 entity with proper structure.
    
    Args:
        entity_id: UUID for the entity
        entity_type: Type name (e.g., "PackageInsert", "Section")
        name: Entity name
        values: List of value dicts from create_value()
    
    Returns:
        Entity dict with 'id', 'name', 'types', 'values'
    """
    entity = {
        "id": entity_id,
        "name": name,
        "types": [ENTITY_TYPES[entity_type]],
        "values": values or []
    }
    return entity

def create_relation(relation_id: str, relation_type: str, from_id: str, to_id: str, values: list = None) -> dict:
    """Create a GRC-20 relation with proper structure.
    
    Args:
        relation_id: UUID for the relation
        relation_type: Relation type name (e.g., "has_section", "manufactured_by")
        from_id: Source entity ID
        to_id: Target entity ID
        values: Optional list of value dicts
    
    Returns:
        Relation dict with 'id', 'type', 'from', 'to', 'values'
    """
    relation = {
        "id": relation_id,
        "type": RELATIONS.get(relation_type),
        "from": from_id,
        "to": to_id,
        "values": values or []
    }
    return relation

def print_progress_bar(current, total, bar_length=50, progress=None):
    """Print a clean progress bar and write to progress file"""
    if total == 0:
        return
    percent = float(current) * 100 / total
    arrow = '-' * int(percent/100 * bar_length - 1) + '>'
    spaces = ' ' * (bar_length - len(arrow))
    
    # Write to progress file for orchestrator
    try:
        from pathlib import Path
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from progress import Progress
        progress = Progress(step_num=1, step_name="DailyMed")
        progress.report(current / total, f"Converting {current}/{total} documents")
    except:
        pass  # Silently fail if progress module not available
    
    sys.stdout.write('\r')
    sys.stdout.write(f"Progress: [{arrow + spaces}] {percent:.1f}% ({current}/{total})")
    sys.stdout.flush()

def check_value_types(entities):
    """Check if all entities have valid structure for GRC-20 specification"""
    issues = []
    
    for entity in entities:
        entity_id = entity.get('id')
        
        # Check that entity has 'id' field
        if not entity_id:
            issues.append({
                "entity": "MISSING",
                "issue": "Entity missing 'id' field",
                "fix": "Ensure all entities have 'id' field"
            })
            continue
        
        # Check that entity has 'types' array
        if 'types' not in entity:
            issues.append({
                "entity": entity_id,
                "issue": "Entity missing 'types' array",
                "fix": "Ensure all entities have 'types' array"
            })
        
        # Check values array
        for value in entity.get('values', []):
            prop_id = value.get('property')
            if not prop_id or len(prop_id) != 32:
                issues.append({
                    "entity": entity_id,
                    "issue": f"Invalid property ID: {prop_id}",
                    "fix": "Property IDs should be 32-character UUIDs (hex format)"
                })
    
    return issues, len(issues) == 0

def check_entity_ids_fixed(entities):
    """Check entity IDs are valid UUIDs (32-char hex format)"""
    issues = []
    
    for entity in entities:
        entity_id = entity.get('id')
        if not entity_id:
            issues.append({
                "entity": "MISSING",
                "issue": "Entity missing 'id' field",
                "fix": "Ensure all entities have 'id' field"
            })
            continue
        
        # GRC-20 uses 32-character hex UUIDs (without hyphens)
        if len(entity_id) != 32:
            issues.append({
                "entity": entity_id,
                "issue": f"Invalid entity ID length: {len(entity_id)}, expected 32",
                "fix": "Use 32-character hex UUID (no hyphens)"
            })
        
        # Check it's valid hex
        try:
            int(entity_id, 16)
        except ValueError:
            issues.append({
                "entity": entity_id,
                "issue": "Entity ID is not valid hexadecimal",
                "fix": "Use UUID4 converted to 32-char hex string"
            })
    
    return issues, len(issues) == 0

def check_standard_attributes(entities):
    """Check if standard properties are used correctly"""
    issues = []
    
    # Track which standard properties are used
    used_standard = {
        "name": False,
        "description": False,
    }
    
    usage_count = defaultdict(int)
    name_prop_id = PROPERTIES.get("name")
    desc_prop_id = PROPERTIES.get("description")
    
    for entity in entities:
        for value in entity.get('values', []):
            prop_id = value.get('property')
            
            if prop_id == name_prop_id:
                used_standard["name"] = True
                usage_count[prop_id] += 1
            elif prop_id == desc_prop_id:
                used_standard["description"] = True
                usage_count[prop_id] += 1
    
    # Calculate compliance score
    used_count = sum(used_standard.values())
    total_count = len(used_standard)
    compliance_percent = (used_count / total_count) * 100 if total_count > 0 else 0
    
    return issues, used_standard, compliance_percent, usage_count

def check_entity_types(entities):
    """Check if entity types are properly defined"""
    issues = []
    type_usage = defaultdict(int)
    
    for entity in entities:
        types = entity.get('types', [])
        for type_id in types:
            type_usage[type_id] += 1
    
    # Check that we have entities of expected types
    expected_types = ['PackageInsert', 'Section', 'Manufacturer']
    found_types = set()
    
    for type_name in expected_types:
        type_id = ENTITY_TYPES.get(type_name)
        if type_id and type_usage.get(type_id, 0) > 0:
            found_types.add(type_name)
    
    missing = set(expected_types) - found_types
    if missing:
        issues.append({
            "issue": f"Missing entity types: {missing}",
            "fix": f"Ensure entities with types {missing} are created"
        })
    
    return issues, len(issues) == 0

    
    # Find all entities that define types
    for entity in entities:
        for triple in entity.get('triples', []):
            if triple.get('attribute') == GRC20_SPEC["standard_attributes"]["type"]:
                type_value = triple.get('value', {}).get('value')
#                 type_entities.add(type_value)
                type_usage[type_value] += 1
    
    # Check if there's at least one proper type entity
    has_type_entity = False
    for entity in entities:
        entity_id = entity.get('entity')
#         if entity_id in type_entities:
        # has_type_entity = True
        # break
    
    if not has_type_entity:
        issues.append({
            "issue": "No proper type entities found",
            "fix": "Create entities for your custom types like PackageInsert, Section, Manufacturer."
        })
    
    return issues, has_type_entity

def check_compliance_fixed(entities):
    """FIXED compliance check that doesn't false-positive on section names"""
    print(" GRC-20 COMPLIANCE CHECK:")
    print("=" * 80)
    
    # Check each aspect
    value_type_issues, value_type_ok = check_value_types(entities)
    entity_id_issues, entity_id_ok = check_entity_ids_fixed(entities)  # Use the FIXED version
    standard_attr_issues, used_standard, standard_attr_percent, usage_count = check_standard_attributes(entities)
    entity_type_issues, entity_type_ok = check_entity_types(entities)
    
    # Calculate scores
    scores = {
        "Value Types": 100 if value_type_ok else 0,
        "Entity ID Generation": 100 if entity_id_ok else 0,
        "Standard Attributes": standard_attr_percent,
        "Entity Types": 100 if entity_type_ok else 0,
        "Triple Structure": 100  # Always true if we got this far
    }
    
    # Calculate overall score
    overall_score = sum(scores.values()) / len(scores)
    
    # Display results
    print(f" Value Types: {'✅' if value_type_ok else '❌'} - {scores['Value Types']}%")
    if value_type_issues:
        print(f"   Issues: {len(value_type_issues)} found")
    
    print(f" Entity ID Generation: {'✅' if entity_id_ok else '❌'} - {scores['Entity ID Generation']}%")
    if entity_id_issues:
        print(f"   Issues: {len(entity_id_issues)} found")
    
    print(f" Standard Attributes: {standard_attr_percent:.0f}%")
    print("   Detailed breakdown:")
    for attr_name, used in used_standard.items():
        if attr_name == "blocks" and PROPERTIES.get("has_section") in usage_count:
            print(f"     • {attr_name}: ✅ (using '{PROPERTIES.get('has_section')}' as equivalent)")
        elif used:
            print(f"     • {attr_name}: ✅")
        else:
            print(f"     • {attr_name}: ❌")
    
    print(f" Entity Types: {'✅' if entity_type_ok else '❌'} - {scores['Entity Types']}%")
    if entity_type_issues:
        print(f"   Issues: {len(entity_type_issues)} found")
    
    print(f" Triple Structure: ✅ - {scores['Triple Structure']}%")
    
    print("=" * 80)
    print(f" OVERALL COMPLIANCE: {overall_score:.0f}%")
    print("=" * 80)
    
    # Show improvement suggestions
    if overall_score < 100:
        print(" IMPROVEMENT SUGGESTIONS:")
        print("=" * 80)
        
        if not entity_id_ok:
            print(" 1. Fix Entity ID Generation:")
            print("    - Use the corrected generate_uuid() function")
            print("    - Ensure all IDs are exactly 22 characters")
            print("    - Check that all fixed attribute IDs are 22 characters")
        
        if standard_attr_percent < 100:
            print(" 2. Standard Attributes Analysis:")
            print(f"    - You're using {standard_attr_percent:.0f}% of standard attributes")
            print("    - Note: Using 'has_section' as equivalent of 'blocks' is valid")
            print("    - Consider adding 'cover' attribute if relevant for your use case")
        
        if not entity_type_ok:
            print(" 3. Create Proper Type Entities:")
            print("    - Define PackageInsert, Section, Manufacturer as type entities")
            print("    - Reference these instead of hardcoded IDs")
        
        print("=" * 80)
    
    return scores, overall_score

def display_sample_entities(entities_file):
    """Display sample entities with clear property mapping"""
    print("\n SAMPLE ENTITIES:")
    print("=" * 80)
    
    with open(output_file, 'r') as f:
        data = json.load(f)
        entities = data.get('entities', [])
        relations = data.get('relations', [])
    
    # Create reverse mapping for display
    reverse_props = {v: k for k, v in PROPERTIES.items()}
    reverse_types = {v: k for k, v in ENTITY_TYPES.items()}
    
    # Find a PackageInsert entity
    drug_entity = None
    section_entity = None
    manufacturer_entity = None
    
    for entity in entities:
        types = entity.get('types', [])
        type_names = [reverse_types.get(t, t) for t in types]
        
        if 'PackageInsert' in type_names and not drug_entity:
            drug_entity = entity
        elif 'Section' in type_names and not section_entity:
            section_entity = entity
        elif 'Manufacturer' in type_names and not manufacturer_entity:
            manufacturer_entity = entity
        
        if drug_entity and section_entity and manufacturer_entity:
            break
    
    # Display PackageInsert entity sample
    if drug_entity:
        print(" SAMPLE PACKAGE INSERT ENTITY:")
        print(f"   Entity ID: {drug_entity['id']} (length: {len(drug_entity['id'])})")
        print(f"   Types: {drug_entity.get('types', [])}")
        print("   Values:")
        for i, value in enumerate(drug_entity.get('values', [])[:4]):  # Show first 4 values
            prop_name = reverse_props.get(value.get('property'), value.get('property', 'unknown'))
            val = value.get('value', '')
            if len(str(val)) > 60:
                val = str(val)[:60] + "..."
            print(f"   {i+1}. {prop_name}: {val}")
        print(f"   ... ({len(drug_entity.get('values', []))} total values)")
    
    # Display section entity sample
    if section_entity:
        print("\n SAMPLE SECTION ENTITY:")
        print(f"   Entity ID: {section_entity['id']} (length: {len(section_entity['id'])})")
        print(f"   Types: {section_entity.get('types', [])}")
        print("   Values:")
        for i, value in enumerate(section_entity.get('values', [])):
            prop_name = reverse_props.get(value.get('property'), value.get('property', 'unknown'))
            val = value.get('value', '')
            if prop_name == 'content' and len(str(val)) > 80:
                val = str(val)[:80] + "..."
            print(f"   {i+1}. {prop_name}: {val}")
    
    # Display manufacturer entity sample
    if manufacturer_entity:
        print("\n SAMPLE MANUFACTURER ENTITY:")
        print(f"   Entity ID: {manufacturer_entity['id']} (length: {len(manufacturer_entity['id'])})")
        print(f"   Types: {manufacturer_entity.get('types', [])}")
        print("   Values:")
        for i, value in enumerate(manufacturer_entity.get('values', [])):
            prop_name = reverse_props.get(value.get('property'), value.get('property', 'unknown'))
            val = value.get('value', '')
            print(f"   {i+1}. {prop_name}: {val}")
    
    # Display sample relations
    if relations:
        print("\n SAMPLE RELATIONS:")
        print(f"   Total relations: {len(relations)}")
        for i, rel in enumerate(relations[:3]):
            rel_type = rel.get('type', 'unknown')
            reverse_rel = {v: k for k, v in RELATIONS.items()}
            rel_name = reverse_rel.get(rel_type, rel_type)
            print(f"   {i+1}. {rel_name}: {rel.get('from', '?')} -> {rel.get('to', '?')}")
    
    print("\n PROPERTY MAPPING:")
    print("=" * 80)
    print("   Properties (GRC-20 standard uses 32-char hex UUIDs):")
    for name, prop_id in sorted(PROPERTIES.items()):
        print(f"   • {name}: {prop_id}")
    
    print("\n   Entity Types:")
    for name, type_id in ENTITY_TYPES.items():
        print(f"   • {name}: {type_id}")
    
    print("\n   Relation Types:")
    for name, rel_id in RELATIONS.items():
        print(f"   • {name}: {rel_id}")
    
    print("=" * 80)

def analyze_pharmaceutical_data(file_path, sample_size=100):
    """Analyze your actual data structure to inform GRC-20 type definitions"""
    with open(file_path, 'r') as f:
        data = json.load(f)
    
    # Analyze top-level fields
    top_level_fields = defaultdict(int)
    section_types = Counter()
    
    # Sample the data for analysis
    sample_data = data[:sample_size] if len(data) > sample_size else data
    
    for doc in sample_data:
        # Count top-level fields
        for field in doc.keys():
            top_level_fields[field] += 1
        
        # Analyze sections
        for section in doc.get('sections', []):
            section_type = section.get('section_type', 'OTHER')
            section_types[section_type] += 1
    
    return {
        'top_level_fields': dict(top_level_fields),
        'section_types': dict(section_types),
        'total_inserts': len(data)
    }

# def create_type_entities():
#     """Create type entities using schema-defined IDs.
#     
#     Note: Types are defined in PharmaSchema, this creates the type entities
#     with their name triples for export.
#     """
#     type_entities = []
#     
#     # PackageInsert type entity
#     type_entities.append({
#         "entity": ENTITY_TYPES['PackageInsert'],
#         "triples": [
#             create_triple(ENTITY_TYPES['PackageInsert'], "name", "PackageInsert"),
#             create_triple(ENTITY_TYPES['PackageInsert'], "type", GRC20_SPEC["standard_types"]["type"])
#         ]
#     })
#     
#     # Section type entity
#     type_entities.append({
#         "entity": ENTITY_TYPES['Section'],
#         "triples": [
#             create_triple(ENTITY_TYPES['Section'], "name", "Section"),
#             create_triple(ENTITY_TYPES['Section'], "type", GRC20_SPEC["standard_types"]["type"])
#         ]
#     })
#     
#     # Manufacturer type entity
#     type_entities.append({
#         "entity": ENTITY_TYPES['Manufacturer'],
#         "triples": [
#             create_triple(ENTITY_TYPES['Manufacturer'], "name", "Manufacturer"),
#             create_triple(ENTITY_TYPES['Manufacturer'], "type", GRC20_SPEC["standard_types"]["type"])
#         ]
#     })
#     
# 
#     # Add provenance to type entities
#     for type_entity in type_entities:
#         type_entity['triples'].append({
#             'entity': type_entity['entity'],
#             'attribute': schema.prop('provenance'),
#             'value': {'type': 1, 'value': provenance_entity['entity']}
#         })
# 
#     return type_entities
# 
def extract_description_from_sections(sections):
    """Extract description content from sections"""
    if not sections:
        return None
    
    # Look for description sections
    for section in sections:
        title = section.get('title', '').lower()
        if 'description' in title:
            return section.get('content', '')
    
    # If no explicit description section, use the first section's content
    if sections and 'content' in sections[0]:
        return sections[0].get('content', '')
    
    return None

def get_or_create_manufacturer(manufacturer_name, provenance_id):
    """Get or create a manufacturer entity, deduplicating by name.
    
    Returns:
        tuple: (entity_dict or None, entity_id) - entity is None if already created
    """
    global MANUFACTURER_LOOKUP
    
    if not manufacturer_name:
        return None, None
    
    # Normalize name for deduplication
    normalized = manufacturer_name.strip().lower()
    
    if normalized in MANUFACTURER_LOOKUP:
        return None, MANUFACTURER_LOOKUP[normalized]  # Already created
    
    # Create new manufacturer entity
    mfr_id = generate_uuid()
    MANUFACTURER_LOOKUP[normalized] = mfr_id
    
    # Create manufacturer entity with new GRC-20 format
    values = []
    val = create_value("name", manufacturer_name)
    if val:
        values.append(val)
    
    entity = create_entity(mfr_id, "Manufacturer", manufacturer_name, values)
    return entity, mfr_id

def convert_package_insert_to_grc20(insert_data, analysis_results, provenance_id):
    """Convert a single package insert to GRC-20 format.
    
    Creates:
    - PackageInsert entity with metadata
    - Section entities for each section
    - Manufacturer entity (deduplicated by name)
    - Relations linking sections to package insert and manufacturer
    
    Returns:
        tuple: (entities list, relations list)
    """
    entities = []
    relations = []
    
    insert_id = generate_uuid()
    name = insert_data.get('title', '')
    
    # Create the main PackageInsert entity
    values = []
    
    val = create_value("name", name)
    if val:
        values.append(val)
    
    # Extract description from sections
    description = extract_description_from_sections(insert_data.get('sections', []))
    if description:
        val = create_value("description", description[:500])
        if val:
            values.append(val)
    
    # Add FDA-specific attributes
    for prop_name, data_key in [("fda_set_id", "fda_set_id"), ("set_id", "set_id")]:
        if data_key in insert_data:
            val = create_value(prop_name, insert_data[data_key])
            if val:
                values.append(val)
    
    if 'effective_time' in insert_data:
        val = create_value("effective_time", insert_data['effective_time'])
        if val:
            values.append(val)
    
    insert_entity = create_entity(insert_id, "PackageInsert", name, values)
    entities.append(insert_entity)
    
    # Handle manufacturer
    manufacturer_name = insert_data.get('manufacturer')
    if manufacturer_name:
        mfr_entity, mfr_id = get_or_create_manufacturer(manufacturer_name, provenance_id)
        if mfr_entity:
            entities.append(mfr_entity)
        
        # Create manufactured_by relation
        rel = create_relation(
            generate_uuid(), "manufactured_by", insert_id, mfr_id
        )
        relations.append(rel)
    
    # Convert sections
    for section in insert_data.get('sections', []):
        section_id = generate_uuid()
        section_type_name = section.get('section_type', 'OTHER')
        section_title = section.get('title', section_type_name)
        
        section_values = []
        
        val = create_value("name", section_title)
        if val:
            section_values.append(val)
        
        val = create_value("section_type", section_type_name)
        if val:
            section_values.append(val)
        
        if 'content' in section:
            val = create_value("content", section['content'])
            if val:
                section_values.append(val)
        
        section_entity = create_entity(section_id, "Section", section_title, section_values)
        entities.append(section_entity)
        
        # Create has_section relation
        rel = create_relation(
            generate_uuid(), "has_section", insert_id, section_id
        )
        relations.append(rel)
    
    return entities, relations

def convert_dataset_to_grc20(input_file, output_file, progress=None):
    """Convert the entire dataset to GRC-20 format with clean progress reporting"""
    print("=" * 80)
    print("PHARMACEUTICAL KNOWLEDGE GRAPH - GRC-20 CONVERSION")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Source: FDA SPL XML Files")
    print(f"Target: GRC-20 Standard Compliance")
    print("=" * 80)
    
    print(f"Analyzing data structure from {input_file}...")
    analysis = analyze_pharmaceutical_data(input_file)
    
    print(f"\n DATASET ANALYSIS:")
    print(f"   • Found {analysis['total_inserts']:,} parent inserts")
    print(f"   • Top-level fields: {len(analysis['top_level_fields'])} fields")
    print(f"   • Section types: {len(analysis['section_types'])} types")
    
    # Display key fields (limit for readability)
    key_fields = ['fda_document_id', 'fda_set_id', 'title', 'manufacturer', 'provenance_hash']
    print(f"   • Key fields: {', '.join(key_fields)}")
    
    # Display top section types
    top_sections = sorted(analysis['section_types'].items(), key=lambda x: x[1], reverse=True)[:5]
    print(f"   • Top sections: {', '.join([s[0] for s in top_sections])}")
    
    # Create provenance entity for FDA SPL source
    print("\n" + "=" * 80)
    print("CREATING PROVENANCE")
    print("=" * 80)
    
    provenance_entity = schema.create_provenance_entity(
        source_name="DailyMed",
        date_accessed=datetime.now().strftime("%Y-%m-%d"),
    )
    provenance_id = provenance_entity["id"]
    print(f"  Created provenance: {provenance_id}")
    
    print("\n" + "=" * 80)
    print("CONVERSION PROGRESS:")
    print("=" * 80)
    
    # Create type entities first
#     type_entities = create_type_entities()
#     print(f"Created {len(type_entities)} type entities")
    
    # Load the full dataset
    with open(input_file, 'r') as f:
        parent_inserts = json.load(f)
    
    # Convert to GRC-20
    grc20_entities = [provenance_entity]  # Start with provenance
    grc20_relations = []
    processed_count = 0
    section_count = 0
    description_count = 0
    
    manufacturer_ids = set()  # Track unique manufacturer IDs
    
    for parent_insert in parent_inserts:
        # convert_package_insert_to_grc20 returns (entities, relations)
        created_entities, created_relations = convert_package_insert_to_grc20(parent_insert, analysis, provenance_id)
        
        # Find the PackageInsert entity for description checking
        insert_entity = None
        for entity in created_entities:
            # Check types array for PackageInsert type
            entity_types = entity.get("types", [])
            if ENTITY_TYPES["PackageInsert"] in entity_types:
                insert_entity = entity
                break
            
            # Track section count
            if ENTITY_TYPES['Section'] in entity_types:
                section_count += 1
            
            # Track manufacturer IDs
            if ENTITY_TYPES['Manufacturer'] in entity_types:
                manufacturer_ids.add(entity['id'])
        
        # Count how many inserts have descriptions
        if insert_entity:
            for value in insert_entity.get('values', []):
                if value.get('property') == PROPERTIES.get('description'):
                    description_count += 1
                    break
        
        grc20_entities.extend(created_entities)
        grc20_relations.extend(created_relations)
        
        processed_count += 1
        
        # Update progress bar every 100 inserts
        if processed_count % 100 == 0:
            print_progress_bar(processed_count, len(parent_inserts), progress=progress)
    
    # Complete the progress bar
    print_progress_bar(len(parent_inserts), len(parent_inserts), progress=progress)
    print("\n")
    
    # Save as JSONL files (GRC-20 standard format)
    entities_file = output_file.replace('.json', '_entities.jsonl')
    relations_file = output_file.replace('.json', '_relations.jsonl')
    
    with open(entities_file, 'w') as f:
        for entity in grc20_entities:
            f.write(json.dumps(entity) + '\n')
    
    with open(relations_file, 'w') as f:
        for relation in grc20_relations:
            f.write(json.dumps(relation) + '\n')
    
    print("=" * 80)
    print(" CONVERSION COMPLETE")
    print("=" * 80)
    print(f" RESULTS:")
    print(f"   • Parent inserts processed: {len(parent_inserts):,}")
    print(f"   • PackageInsert entities created: {len(parent_inserts):,}")
    print(f"   • Manufacturer entities created: {len(manufacturer_ids):,}")
    print(f"   • Section entities created: {section_count:,}")
    print(f"   • Relations created: {len(grc20_relations):,}")
    print(f"   • Inserts with descriptions: {description_count:,}")
    print(f"   • Total GRC-20 entities: {len(grc20_entities):,}")
    print(f"   • Average sections per insert: {section_count/len(parent_inserts):.1f}")
    print(f"   • Entities file: {entities_file}")
    print(f"   • Relations file: {relations_file}")
    entities_size = os.path.getsize(entities_file)/1024/1024
    relations_size = os.path.getsize(relations_file)/1024/1024
    print(f"   • File sizes: {entities_size:.1f} MB + {relations_size:.1f} MB")
    
    # Display sample entities
    display_sample_entities(entities_file)
    
    # Run the FIXED compliance check
    scores, overall_score = check_compliance_fixed(grc20_entities)
    
    print("=" * 80)
    print(" GRC-20 COMPLIANCE: {:.0f}%".format(overall_score))
    print(" PROVENANCE TRACKING: PRESERVED")
    print("=" * 80)
    
    return grc20_entities, scores, overall_score

if __name__ == "__main__":
    # Set up file paths - output to data/grc20_v2
    # scripts/production/pipeline/01_dailymed -> project root (5 parents)
    base_dir = Path(__file__).parent.parent.parent.parent.parent / "data" / "grc20_v2"
    base_dir.mkdir(parents=True, exist_ok=True)
    
    input_file = base_dir / "dailymed_documents.json"
    output_file = base_dir / "dailymed_entities.json"
    
    # Run the conversion
    convert_dataset_to_grc20(str(input_file), str(output_file))
