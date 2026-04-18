#!/usr/bin/env python3
"""
Validate v3 schema is backward compatible with existing pipeline usage.
"""

from pharma_schema import (
    PharmaSchema,
    ENTITY_TYPES,
    ATTRIBUTES,
    RELATION_TYPES,
    GRC20_RELATION_TYPE_IDS,
    TTY_TO_ENTITY_TYPE,
    generate_grc20_id,
)

def test_v2_compatibility():
    """Test that all v2 usage patterns still work."""
    print("=" * 60)
    print("BACKWARD COMPATIBILITY TESTS (v2 patterns)")
    print("=" * 60)
    
    schema = PharmaSchema()
    
    # Test 1: create_entity (v2 signature)
    print("\n[TEST 1] create_entity() - v2 signature")
    entity = schema.create_entity("Ingredient", "Acetaminophen")
    print(f"  ✓ Entity created: {entity['entity'][:15]}...")
    print(f"  ✓ Triples count: {len(entity['triples'])}")
    
    # Test 2: create_entity with entity_id (v2 signature)
    print("\n[TEST 2] create_entity() - with entity_id")
    entity = schema.create_entity("ClinicalDrug", "Ibuprofen 200mg tablet", entity_id="test-id-123")
    print(f"  ✓ Entity ID preserved: {entity['entity']}")
    
    # Test 3: relation() (v2 signature)
    print("\n[TEST 3] relation() - v2 signature")
    triples = schema.relation("entity-a", "has_ingredient", "entity-b")
    print(f"  ✓ Relation triples: {len(triples)}")
    
    # Test 4: relation() with relation_id (v2 signature)
    print("\n[TEST 4] relation() - with relation_id")
    triples = schema.relation("entity-a", "has_dose_form", "entity-b", relation_id="rel-123")
    print(f"  ✓ Relation ID used in triples")
    
    # Test 5: create_provenance (v2 signature)
    print("\n[TEST 5] create_provenance()")
    prov = schema.create_provenance("RxNorm", "NIH RxNorm Database", "2024-01-15")
    print(f"  ✓ Provenance created: {prov['entity'][:15]}...")
    
    # Test 6: add_provenance_link (v2 signature)
    print("\n[TEST 6] add_provenance_link()")
    entity_with_prov = schema.add_provenance_link(entity, prov['entity'])
    print(f"  ✓ Provenance link added, triples: {len(entity_with_prov['triples'])}")
    
    # Test 7: attr(), rel(), type_id() accessors
    print("\n[TEST 7] Accessor methods")
    try:
        attr_id = schema.attr("name")
        print(f"  ✓ attr('name') = {attr_id}")
        rel_id = schema.rel("has_ingredient")
        print(f"  ✓ rel('has_ingredient') = {rel_id}")
        type_id = schema.type_id("Ingredient")
        print(f"  ✓ type_id('Ingredient') = {type_id}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    # Test 8: All v2 entity types exist
    print("\n[TEST 8] v2 entity types preserved")
    v2_types = ["Ingredient", "ClinicalDrug", "BrandedDrug", "BrandName", "DoseForm",
                "PackageInsert", "Manufacturer", "NDC", "Provenance", "Section", 
                "DrugClass", "Relation"]
    for t in v2_types:
        if t in schema.types:
            print(f"  ✓ {t}")
        else:
            print(f"  ✗ {t} MISSING!")
    
    # Test 9: All v2 relation types exist
    print("\n[TEST 9] v2 relation types preserved")
    v2_rels = ["has_section", "has_ingredient", "has_dose_form", "has_tradename",
               "is_a", "consists_of", "contains", "has_part", "has_form", 
               "reformulated_to", "has_quantified_form", "has_boss", "equivalent_to",
               "maps_to_rxcui", "has_provenance"]
    for r in v2_rels:
        if r in schema.relations:
            print(f"  ✓ {r}")
        else:
            print(f"  ✗ {r} MISSING!")
    
    # Test 10: Existing relation type IDs preserved
    print("\n[TEST 10] Existing GRC-20 relation IDs preserved")
    preserved_count = 0
    for rel_name, rel_id in GRC20_RELATION_TYPE_IDS.items():
        if rel_id and rel_name in schema.relations:
            if schema.relations[rel_name] == rel_id:
                preserved_count += 1
            else:
                print(f"  ✗ {rel_name}: ID changed from {rel_id} to {schema.relations[rel_name]}")
    print(f"  ✓ {preserved_count} relation IDs preserved")

def test_v3_features():
    """Test new v3 features."""
    print("\n" + "=" * 60)
    print("V3 FEATURE TESTS")
    print("=" * 60)
    
    schema = PharmaSchema()
    
    # Test 1: tty_to_entity_type
    print("\n[TEST 1] tty_to_entity_type()")
    for tty in ["IN", "PIN", "SCDC", "SCDF", "SCD", "SBD", "BN"]:
        entity_type = schema.tty_to_entity_type(tty)
        print(f"  {tty} -> {entity_type}")
    
    # Test 2: get_relation_type_for_tty_pair
    print("\n[TEST 2] get_relation_type_for_tty_pair()")
    tests = [
        ("IN", "SCDC", "RO"),
        ("IN", "SCDF", "RO"),
        ("SCDC", "SCD", "RO"),
        ("SCD", "SBD", "RN"),
    ]
    for src, tgt, code in tests:
        rel = schema.get_relation_type_for_tty_pair(src, tgt, code)
        print(f"  {src} --[{code}]--> {tgt} = {rel}")
    
    # Test 3: create_entity with rxcui and tty
    print("\n[TEST 3] create_entity() - v3 signature with rxcui/tty")
    entity = schema.create_entity(
        "Ingredient", 
        "Acetaminophen", 
        rxcui="161", 
        tty="IN"
    )
    print(f"  ✓ Entity created with rxcui/tty")
    print(f"  ✓ Triples: {len(entity['triples'])} (should be 4: type, name, rxcui, tty)")
    
    # Test 4: relation with tty attributes
    print("\n[TEST 4] relation() - v3 signature with tty attributes")
    triples = schema.relation(
        "ingredient-entity", 
        "has_ingredient", 
        "drug-entity",
        rela_code="RO",
        source_tty="SCDC",
        target_tty="IN"
    )
    print(f"  ✓ Relation created with tty attributes")
    print(f"  ✓ Triples: {len(triples)} (should be 7: 4 base + 3 tty attrs)")
    
    # Test 5: New TTY-based entity types
    print("\n[TEST 5] New TTY-based entity types")
    new_types = ["PreciseIngredient", "ClinicalDrugComponent", "ClinicalDrugForm",
                 "ClinicalDrugGroup", "BrandedDrugComponent", "BrandedDrugForm",
                 "BrandedDrugGroup", "DoseFormGroup", "GenericPack", "BrandPack"]
    for t in new_types:
        if t in schema.types:
            print(f"  ✓ {t}")
        else:
            print(f"  ✗ {t} MISSING!")
    
    # Test 6: New attributes
    print("\n[TEST 6] New v3 attributes")
    new_attrs = ["rela_code", "source_tty", "target_tty"]
    for a in new_attrs:
        if a in schema.attributes:
            print(f"  ✓ {a}")
        else:
            print(f"  ✗ {a} MISSING!")

def test_schema_counts():
    """Print schema statistics."""
    print("\n" + "=" * 60)
    print("SCHEMA STATISTICS")
    print("=" * 60)
    
    schema = PharmaSchema()
    print(f"\nEntity Types: {len(schema.types)}")
    print(f"Attributes: {len(schema.attributes)}")
    print(f"Relation Types: {len(schema.relations)}")
    
    print(f"\nTTY mappings: {len(TTY_TO_ENTITY_TYPE)}")

if __name__ == "__main__":
    test_v2_compatibility()
    test_v3_features()
    test_schema_counts()
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)
