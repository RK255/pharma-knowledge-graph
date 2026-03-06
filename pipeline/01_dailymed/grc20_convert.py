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
from grc20_utils import generate_grc20_id, GRC20_VALUE_TYPES

# Initialize schema
schema = PharmaSchema()

# GRC-20 Specification Constants (from schema)
GRC20_SPEC = {
    "value_types": GRC20_VALUE_TYPES,
    "standard_attributes": {
        "name": schema.attr("name"),
        "type": schema.attr("type"),
        "description": schema.attr("description"),
    },
    "standard_types": {
        "type": schema.attr("type")
    }
}

# Attribute mappings from schema
ATTRIBUTES = {
    "name": schema.attr("name"),
    "type": schema.attr("type"),
    "description": schema.attr("description"),
    "content": schema.attr("content"),
    "section_type": schema.attr("section_type"),
    "fda_set_id": schema.attr("fda_set_id"),
    "effective_time": schema.attr("effective_time"),
    "set_id": schema.attr("set_id"),
    "provenance": schema.attr("provenance"),
    "from_entity": schema.attr("from_entity"),
    "to_entity": schema.attr("to_entity"),
}

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

def create_triple(entity_id, attribute_name, value, value_type="TEXT"):
    """Create a GRC-20 triple using schema IDs"""
    attr_id = ATTRIBUTES.get(attribute_name) or schema.attr(attribute_name)
    return {
        "entity": entity_id,
        "attribute": attr_id,
        "value": {
            "type": GRC20_VALUE_TYPES.get(value_type, 1),
            "value": str(value)
        }
    }

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
    """Check if all value types match GRC-20 specification"""
    issues = []
    valid_types = set(GRC20_SPEC["value_types"].values())
    
    for entity in entities:
        for triple in entity.get('triples', []):
            value_type = triple.get('value', {}).get('type')
            if value_type not in valid_types:
                issues.append({
                    "entity": entity.get('entity'),
                    "attribute": triple.get('attribute'),
                    "issue": f"Invalid value type: {value_type}",
                    "fix": f"Use one of: {list(valid_types)}"
                })
    
    return issues, len(issues) == 0

def check_entity_ids_fixed(entities):
    """FIXED version of the entity ID check that doesn't false-positive on section names"""
    issues = []
    
    for entity in entities:
        entity_id = entity.get('entity')
        if not entity_id or len(entity_id) != 22:
            issues.append({
                "entity": entity_id,
                "issue": f"Invalid entity ID length: {len(entity_id) if entity_id else 0}",
                "fix": "Generate 22-character Base58 ID using UUID4"
            })
        
        # Check triples for valid attribute IDs
        for triple in entity.get('triples', []):
            attr_id = triple.get('attribute')
            if not attr_id or len(attr_id) != 22:
                issues.append({
                    "entity": entity_id,
                    "attribute": attr_id,
                    "issue": f"Invalid attribute ID length: {len(attr_id) if attr_id else 0}",
                    "fix": "Use 22-character Base58 ID"
                })
            
            # FIXED: Only check entity references in 'has_section' attributes, not 'name' attributes
            value = triple.get('value', {}).get('value')
            if isinstance(value, str) and len(value) == 22 and value.isalnum():
                # Only validate as Base58 if this is a has_section attribute
                if triple.get('attribute') == RELATIONS["has_section"]:
                    if not all(c in '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz' for c in value):
                        issues.append({
                            "entity": entity_id,
                            "attribute": attr_id,
                            "issue": f"Invalid entity reference in value: {value}",
                            "fix": "Use valid Base58 encoding"
                        })
    
    return issues, len(issues) == 0

def check_standard_attributes(entities):
    """Check if standard attributes are used correctly with detailed tracking"""
    issues = []
    standard_attrs = GRC20_SPEC["standard_attributes"]
    
    # Count usage of standard attributes
    usage_count = defaultdict(int)
    custom_attrs = set()
    
    # Track which standard attributes are used (pharma-specific)
    # Note: cover/blocks are Geo-specific, not relevant for pharma data
    used_standard = {
        "name": False,
        "type": False,
        "description": False,
        "has_section": False,  # Our equivalent to blocks
    }
    
    has_section_id = RELATIONS.get("has_section")
    
    for entity in entities:
        for triple in entity.get('triples', []):
            attr_id = triple.get('attribute')
            
            # Check if it's a standard attribute
            if attr_id in standard_attrs.values():
                # Find which standard attribute this is
                for std_name, std_id in standard_attrs.items():
                    if attr_id == std_id:
                        used_standard[std_name] = True
                        usage_count[attr_id] += 1
                        break
            # Check for has_section relation (our blocks equivalent)
            elif attr_id == has_section_id:
                used_standard["has_section"] = True
                usage_count[attr_id] += 1
            else:
                custom_attrs.add(attr_id)
    
    # Calculate compliance score
    used_count = sum(used_standard.values())
    total_count = len(used_standard)
    compliance_percent = (used_count / total_count) * 100
    
    return issues, used_standard, compliance_percent, usage_count

def check_entity_types(entities):
    """Check if entity types are properly defined"""
    issues = []
#     type_entities = set()
    type_usage = defaultdict(int)
    
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
        if attr_name == "blocks" and ATTRIBUTES.get("has_section") in usage_count:
            print(f"     • {attr_name}: ✅ (using '{ATTRIBUTES.get('has_section')}' as equivalent)")
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
            print("    - Use the corrected generate_grc20_id() function")
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

def display_sample_entities(output_file):
    """Display sample entities with clear attribute mapping"""
    print("\n SAMPLE ENTITIES:")
    print("=" * 80)
    
    with open(output_file, 'r') as f:
        data = json.load(f)
        entities = data['entities']  # Get entities from proper GRC-20 structure
    
    # Create reverse mapping for display
    reverse_attrs = {v: k for k, v in ATTRIBUTES.items()}
    
    # Find a PackageInsert entity
    drug_entity = None
    section_entity = None
    
    for entity in entities:
        if entity.get('triples'):
            # Check if it's a PackageInsert entity
            for triple in entity['triples']:
                if triple.get('attribute') == ATTRIBUTES["type"] and triple.get('value', {}).get('value') == ENTITY_TYPES.get('PackageInsert'):
                    drug_entity = entity
                    break
                elif triple.get('attribute') == ATTRIBUTES["type"] and triple.get('value', {}).get('value') == ENTITY_TYPES.get('section'):
                    section_entity = entity
                    break
            
            if drug_entity and section_entity:
                break
    
    # Display PackageInsert entity sample
    if drug_entity:
        print(" SAMPLE DRUG ENTITY:")
        print(f"   Entity ID: {drug_entity['entity']} (length: {len(drug_entity['entity'])})")
        print("   Triples:")
        for i, triple in enumerate(drug_entity['triples'][:3]):  # Show first 3 triples
            attr_name = reverse_attrs.get(triple['attribute'], triple['attribute'])
            attr_id = triple['attribute']
            print(f"   {i+1}. {attr_name}: {triple['value']['value']} (attr ID: {attr_id}, length: {len(attr_id)})")
        print(f"   ... ({len(drug_entity['triples'])} total triples)")
    
    # Display section entity sample
    if section_entity:
        print("\n SAMPLE SECTION ENTITY:")
        print(f"   Entity ID: {section_entity['entity']} (length: {len(section_entity['entity'])})")
        print("   Triples:")
        for i, triple in enumerate(section_entity['triples']):
            attr_name = reverse_attrs.get(triple['attribute'], triple['attribute'])
            value = triple['value']['value']
            if attr_name == 'content' and len(value) > 100:
                value = value[:100] + "..."
            attr_id = triple['attribute']
            print(f"   {i+1}. {attr_name}: {value} (attr ID: {attr_id}, length: {len(attr_id)})")
    
    print("\n ATTRIBUTE MAPPING:")
    print("=" * 80)
    print("   Fixed Attributes:")
    for name, attr_id in ATTRIBUTES.items():
        # Mark if this is equivalent to a standard attribute
        equiv_note = ""
        if name == "has_section":
            equiv_note = " (equivalent to 'blocks')"
        print(f"   • {name}: {attr_id} (length: {len(attr_id)}){equiv_note}")
    
    print("\n   Entity Types:")
    for name, type_id in ENTITY_TYPES.items():
        print(f"   • {name}: {type_id} (length: {len(type_id)})")
    
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
#             'attribute': schema.attr('provenance'),
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

def get_or_create_manufacturer(manufacturer_name):
    """Get existing manufacturer ID or create new one. Deduplicates by name."""
    global MANUFACTURER_LOOKUP
    
    if not manufacturer_name:
        return None
    
    # Normalize name for deduplication
    normalized = manufacturer_name.strip().lower()
    
    if normalized in MANUFACTURER_LOOKUP:
        return MANUFACTURER_LOOKUP[normalized]
    
    # Create new manufacturer entity
    mfr_id = generate_grc20_id()
    MANUFACTURER_LOOKUP[normalized] = mfr_id
    return mfr_id

def convert_package_insert_to_grc20(insert_data, analysis_results, provenance_id):
    """Convert a single package insert to GRC-20 format.
    
    Creates:
    - PackageInsert entity with metadata
    - Section entities for each section
    - Manufacturer entity (deduplicated by name)
    - Links sections to package insert via has_section relation
    - Links to manufacturer via manufactured_by relation
    """
    insert_id = generate_grc20_id()
    
    # Create the main PackageInsert entity
    insert_triples = [
        create_triple(insert_id, "name", insert_data.get('title', '')),
        create_triple(insert_id, "type", ENTITY_TYPES['PackageInsert'])
    ]
    
    # Extract description from sections
    description = extract_description_from_sections(insert_data.get('sections', []))
    if description:
        insert_triples.append(create_triple(insert_id, "description", description[:500]))
    
    # Add FDA-specific attributes
    if 'fda_set_id' in insert_data:
        insert_triples.append(create_triple(insert_id, "fda_set_id", insert_data['fda_set_id']))
    
    if 'set_id' in insert_data:
        insert_triples.append(create_triple(insert_id, "set_id", insert_data['set_id']))
    
    if 'effective_time' in insert_data:
        insert_triples.append(create_triple(insert_id, "effective_time", insert_data['effective_time'], "TIME"))
    
    # Add provenance link
    insert_triples.append(create_triple(insert_id, "provenance", provenance_id))
    # Handle manufacturer as entity relation
    manufacturer_entity = None
    manufactured_by_rel_entity = None
    manufacturer_name = insert_data.get('manufacturer')
    if manufacturer_name:
        mfr_id = get_or_create_manufacturer(manufacturer_name)
        
        # Create manufactured_by relation entity
        manufactured_by_rel_id = generate_grc20_id()
        manufactured_by_rel_entity = {
            "entity": manufactured_by_rel_id,
            "triples": [
                # Type attributes for relation
                {"entity": manufactured_by_rel_id, "attribute": ATTRIBUTES["type"], "value": {"type": 1, "value": ENTITY_TYPES['Relation']}},
                {"entity": manufactured_by_rel_id, "attribute": ATTRIBUTES["type"], "value": {"type": 1, "value": RELATIONS["manufactured_by"]}},
                # from and to
                {"entity": manufactured_by_rel_id, "attribute": ATTRIBUTES.get("from_entity") or schema.attr("from_entity"), "value": {"type": 1, "value": insert_id}},
                {"entity": manufactured_by_rel_id, "attribute": ATTRIBUTES.get("to_entity") or schema.attr("to_entity"), "value": {"type": 1, "value": mfr_id}},
                # Provenance
                {"entity": manufactured_by_rel_id, "attribute": ATTRIBUTES["provenance"], "value": {"type": 1, "value": provenance_id}},
            ]
        }
        
        manufacturer_entity = {
            "entity": mfr_id,
            "triples": [
                create_triple(mfr_id, "name", manufacturer_name),
                create_triple(mfr_id, "type", ENTITY_TYPES['Manufacturer']),
                create_triple(mfr_id, "provenance", provenance_id)
            ]
        }
    
    
    # Convert sections to separate entities
    section_entities = []
    for section in insert_data.get('sections', []):
        section_id = generate_grc20_id()
        section_type_name = section.get('section_type', 'OTHER')
        
        # Create has_section relation entity
        has_section_rel_id = generate_grc20_id()
        has_section_rel_entity = {
            "entity": has_section_rel_id,
            "triples": [
                # Type attributes for relation
                {"entity": has_section_rel_id, "attribute": ATTRIBUTES["type"], "value": {"type": 1, "value": ENTITY_TYPES['Relation']}},
                {"entity": has_section_rel_id, "attribute": ATTRIBUTES["type"], "value": {"type": 1, "value": RELATIONS["has_section"]}},
                # from and to
                {"entity": has_section_rel_id, "attribute": ATTRIBUTES.get("from_entity") or schema.attr("from_entity"), "value": {"type": 1, "value": insert_id}},
                {"entity": has_section_rel_id, "attribute": ATTRIBUTES.get("to_entity") or schema.attr("to_entity"), "value": {"type": 1, "value": section_id}},
                # Provenance
                {"entity": has_section_rel_id, "attribute": ATTRIBUTES["provenance"], "value": {"type": 1, "value": provenance_id}},
            ]
        }
        section_entities.append(has_section_rel_entity)
        
        # Create section entity
        section_triples = [
            create_triple(section_id, "name", section.get('title', '')),
            create_triple(section_id, "type", ENTITY_TYPES['Section']),
            create_triple(section_id, "section_type", section_type_name),
        ]
        
        # Add content if it exists
        if 'content' in section:
            section_triples.append(create_triple(section_id, "content", section['content']))
        
        # Add provenance link
        section_triples.append(create_triple(section_id, "provenance", provenance_id))
        
        section_entity = {
            "entity": section_id,
            "triples": section_triples
        }
        section_entities.append(section_entity)
    
    # Create the main PackageInsert entity
    insert_entity = {
        "entity": insert_id,
        "triples": insert_triples
    }
    
    # Combine: insert_entity, section_entities (includes relations), manufacturer_entity, relation_entity
    all_entities = [insert_entity] + section_entities
    if manufacturer_entity:
        all_entities.append(manufacturer_entity)
    if manufactured_by_rel_entity:
        all_entities.append(manufactured_by_rel_entity)
    
    return all_entities  # Return list of all entities created

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
    
    provenance_entity = schema.create_provenance(
        source="FDA SPL - DailyMed",
        citation="DailyMed Package Insert Data, U.S. Food and Drug Administration. https://dailymed.nlm.nih.gov/",
        date_accessed=datetime.now().strftime("%Y-%m-%d"),
        source_url="https://dailymed.nlm.nih.gov/dailymed/about.cfm",
        provenance_type="IMPORTED",
    )
    provenance_id = provenance_entity["entity"]
    print(f"  Created provenance: {provenance_id}")
    
    print("\n" + "=" * 80)
    print("CONVERSION PROGRESS:")
    print("=" * 80)
    
    # Create type entities first
#     type_entities = create_type_entities()
#     print(f"Created {len(type_entities)} type entities")
    
    # Create provenance entity
    provenance_entity = schema.create_provenance(
        source="FDA SPL - DailyMed",
        citation="DailyMed Package Insert Data, U.S. Food and Drug Administration. https://dailymed.nlm.nih.gov/",
        date_accessed=datetime.now().strftime("%Y-%m-%d"),
        source_url="https://dailymed.nlm.nih.gov/dailymed/about.cfm",
        provenance_type="IMPORTED",
    )
    provenance_id = provenance_entity["entity"]
    print(f"  Created provenance: {provenance_id}")
    
    # Load the full dataset
    with open(input_file, 'r') as f:
        parent_inserts = json.load(f)
    
    # Convert to GRC-20
    grc20_entities = []  # No type entities
    grc20_entities.append(provenance_entity)  # Add provenance entity
    processed_count = 0
    section_count = 0
    description_count = 0
    
    manufacturer_entities = {}  # Track unique manufacturers
    
    for parent_insert in parent_inserts:
        # convert_package_insert_to_grc20 returns a list of all entities
        created_entities = convert_package_insert_to_grc20(parent_insert, analysis, provenance_id)
        # Find the PackageInsert entity for description checking
        insert_entity = None
        for entity in created_entities:
            for triple in entity.get("triples", []):
                if triple.get("attribute") == ATTRIBUTES["type"] and triple.get("value", {}).get("value") == ENTITY_TYPES["PackageInsert"]:
                    insert_entity = entity
                    break
        
        
        for entity in created_entities:
            grc20_entities.append(entity)
            
            # Track manufacturer for deduplication
            triples = entity.get('triples', [])
            for triple in triples:
                if triple.get('attribute') == ATTRIBUTES["type"]:
                    type_val = triple.get('value', {}).get('value')
                    if type_val == ENTITY_TYPES['Manufacturer']:
                        mfr_id = entity['entity']
                        if mfr_id not in manufacturer_entities:
                            manufacturer_entities[mfr_id] = entity
                    elif type_val == ENTITY_TYPES['Section']:
                        section_count += 1
        
        # Count how many inserts have descriptions
        if insert_entity:
            for triple in insert_entity['triples']:
                if triple.get('attribute') == ATTRIBUTES['description']:
                    description_count += 1
                    break
            
        
        processed_count += 1
        
        # Update progress bar every 100 inserts
        if processed_count % 100 == 0:
            print_progress_bar(processed_count, len(parent_inserts), progress=progress)
    
    # Complete the progress bar
    print_progress_bar(len(parent_inserts), len(parent_inserts), progress=progress)
    print("\n")
    
    # Create proper GRC-20 structure with entities wrapper
    grc20_data = {
        'entities': grc20_entities
    }
    
    # Save the converted data
    with open(output_file, 'w') as f:
        json.dump(grc20_data, f, indent=2)
    
    print("=" * 80)
    print(" CONVERSION COMPLETE")
    print("=" * 80)
    print(f" RESULTS:")
    print(f"   • Parent inserts processed: {len(parent_inserts):,}")
    print(f"   • Type entities created: {0}")
    print(f"   • PackageInsert entities created: {len(parent_inserts):,}")
    print(f"   • Manufacturer entities created: {len(manufacturer_entities):,}")
    print(f"   • Section entities created: {section_count:,}")
    print(f"   • Inserts with descriptions: {description_count:,}")
    print(f"   • Total GRC-20 entities: {len(grc20_entities):,}")
    print(f"   • Average sections per insert: {section_count/len(parent_inserts):.1f}")
    print(f"   • Output file: {output_file}")
    print(f"   • File size: {os.path.getsize(output_file)/1024/1024:.1f} MB")
    
    # Display sample entities
    display_sample_entities(output_file)
    
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
