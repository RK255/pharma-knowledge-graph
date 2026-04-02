#!/usr/bin/env python3
"""
Package Insert Viewer

Shows package insert details and all connected sections.

Usage:
    python package_insert_viewer.py <drug_name>
    python package_insert_viewer.py cetirizine
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "grc20_v2"
SCHEMA_PATH = Path(__file__).parent / "00_schema"

sys.path.insert(0, str(SCHEMA_PATH))
from pharma_schema import PharmaSchema

class PackageInsertViewer:
    def __init__(self):
        self.schema = PharmaSchema()
        self.entities = {}
        self.entity_by_name = {}
        self.relations_from = {}
        self.relations_to = {}
        
        self.type_id_to_name = {v: k for k, v in self.schema.types.items()}
        self.rel_id_to_name = {v: k for k, v in self.schema.relations.items()}
        self.prop_id_to_name = {v: k for k, v in self.schema.properties.items()}
        
        self._load_data()
    
    def _load_data(self):
        print("Loading knowledge graph...", end=" ", flush=True)
        
        entities_file = DATA_DIR / "grc20_merged_entities.jsonl"
        with open(entities_file, 'r') as f:
            for line in f:
                entity = json.loads(line)
                eid = entity['id']
                self.entities[eid] = entity
                name = entity.get('name', '')
                if name:
                    name_lower = name.lower()
                    if name_lower not in self.entity_by_name:
                        self.entity_by_name[name_lower] = []
                    self.entity_by_name[name_lower].append(eid)
        
        relations_file = DATA_DIR / "grc20_merged_relations.jsonl"
        with open(relations_file, 'r') as f:
            for line in f:
                rel = json.loads(line)
                from_id = rel.get('from')
                to_id = rel.get('to')
                rel_type = rel.get('type')
                if isinstance(rel_type, dict):
                    rel_type = rel_type.get('id')
                
                if from_id not in self.relations_from:
                    self.relations_from[from_id] = []
                self.relations_from[from_id].append((rel_type, to_id))
                
                if to_id not in self.relations_to:
                    self.relations_to[to_id] = []
                self.relations_to[to_id].append((rel_type, from_id))
        
        print(f"Loaded {len(self.entities):,} entities, {sum(len(v) for v in self.relations_from.values()):,} relations")
    
    def get_type_name(self, entity):
        type_ids = entity.get('types', [])
        if not type_ids:
            return 'Unknown'
        return self.type_id_to_name.get(type_ids[0], type_ids[0][:8])
    
    def get_entity_name(self, eid):
        if eid not in self.entities:
            return f"Unknown({eid[:8]})"
        return self.entities[eid].get('name', 'unnamed')
    
    def get_entity_props(self, eid):
        if eid not in self.entities:
            return {}
        props = {}
        for v in self.entities[eid].get('values', []):
            prop_id = v.get('property')
            prop_name = self.prop_id_to_name.get(prop_id, prop_id[:8] if prop_id else 'unknown')
            val = v.get('value')
            if prop_name in props:
                if not isinstance(props[prop_name], list):
                    props[prop_name] = [props[prop_name]]
                props[prop_name].append(val)
            else:
                props[prop_name] = val
        return props
    
    def get_rel_name(self, rel_id):
        return self.rel_id_to_name.get(rel_id, rel_id[:8] if rel_id else 'unknown')
    
    def get_related(self, eid, rel_name=None, direction='out'):
        rel_id = self.schema.relations.get(rel_name) if rel_name else None
        relations = self.relations_from.get(eid, []) if direction == 'out' else self.relations_to.get(eid, [])
        results = []
        for rt, other_id in relations:
            if rel_id and rt != rel_id:
                continue
            rel_name_found = self.get_rel_name(rt)
            results.append((rel_name_found, other_id))
        return results
    
    def get_related_by_type(self, eid, rel_name, direction, target_type):
        relations = self.get_related(eid, rel_name, direction)
        results = []
        for _, other_id in relations:
            entity = self.entities.get(other_id, {})
            if self.get_type_name(entity) == target_type:
                results.append(other_id)
        return results
    
    def get_all_related_by_type(self, eid, target_type):
        """Get all entities of a type connected in either direction"""
        results = []
        for rel_name, other_id in self.get_related(eid, direction='out'):
            entity = self.entities.get(other_id, {})
            if self.get_type_name(entity) == target_type:
                results.append((rel_name, other_id, 'out'))
        for rel_name, other_id in self.get_related(eid, direction='in'):
            entity = self.entities.get(other_id, {})
            if self.get_type_name(entity) == target_type:
                results.append((rel_name, other_id, 'in'))
        return results
    
    def view_package_inserts(self, drug_name):
        """Find and display package inserts for a drug"""
        # Find the ingredient
        ingredient_ids = self.entity_by_name.get(drug_name.lower(), [])
        if not ingredient_ids:
            print(f"Drug '{drug_name}' not found")
            return
        
        ingredient_id = ingredient_ids[0]
        ingredient_name = self.entities[ingredient_id].get('name', drug_name)
        
        print("\n" + "=" * 100)
        print(f"PACKAGE INSERTS FOR: {ingredient_name.upper()}")
        print("=" * 100)
        
        # Find all SBDs connected to this ingredient
        scdc_ids = self.get_related_by_type(ingredient_id, 'has_ingredient', 'out', 'ClinicalDrugComponent')
        
        sbd_ids = set()
        for scdc_id in scdc_ids:
            sbds = self.get_related_by_type(scdc_id, 'consists_of', 'out', 'BrandedDrug')
            sbd_ids.update(sbds)
        
        # Find all package inserts connected to SBDs
        pi_ids = set()
        pi_to_sbd = {}
        for sbd_id in sbd_ids:
            pis = self.get_related_by_type(sbd_id, 'maps_to_rxcui', 'in', 'PackageInsert')
            for pi_id in pis:
                pi_ids.add(pi_id)
                if pi_id not in pi_to_sbd:
                    pi_to_sbd[pi_id] = []
                pi_to_sbd[pi_id].append(sbd_id)
        
        if not pi_ids:
            print("\nNo package inserts found for this drug.")
            return
        
        print(f"\nFound {len(pi_ids)} package insert(s)\n")
        
        # Display each package insert
        for pi_id in pi_ids:
            self._display_package_insert(pi_id, pi_to_sbd.get(pi_id, []))
    
    def _display_package_insert(self, pi_id, connected_sbds):
        """Display a single package insert with all its sections"""
        pi_entity = self.entities.get(pi_id, {})
        pi_props = self.get_entity_props(pi_id)
        pi_name = pi_entity.get('name', 'Unknown')
        
        print("─" * 100)
        print(f"PACKAGE INSERT: {pi_name}")
        print("─" * 100)
        
        # Display properties
        print(f"\n{'PROPERTIES':<25}")
        for prop in ['set_id', 'rxcui', 'spl_id', 'version']:
            if prop in pi_props:
                print(f"  {prop:<20}: {pi_props[prop]}")
        
        # Display connected SBDs (Branded Drugs)
        if connected_sbds:
            print(f"\n{'CONNECTED BRANDED DRUGS':<25}")
            for sbd_id in connected_sbds[:5]:
                sbd_name = self.get_entity_name(sbd_id)
                print(f"  • {sbd_name}")
            if len(connected_sbds) > 5:
                print(f"  ... and {len(connected_sbds) - 5} more")
        
        # Find sections connected to this PI
        # Check for 'has_section' relation (outgoing from PI to Section)
        sections_out = self.get_related_by_type(pi_id, 'has_section', 'out', 'Section')
        sections_in = self.get_related_by_type(pi_id, 'has_section', 'in', 'Section')
        sections_from_content = self.get_related_by_type(pi_id, 'has_content', 'out', 'Section')
        sections_from_content_in = self.get_related_by_type(pi_id, 'has_content', 'in', 'Section')
        
        # Also check all relations for Section types
        all_sections = []
        seen_section_ids = set()
        
        for rel_name, other_id in self.get_related(pi_id, direction='out'):
            entity = self.entities.get(other_id, {})
            if self.get_type_name(entity) == 'Section' and other_id not in seen_section_ids:
                all_sections.append((rel_name, other_id))
                seen_section_ids.add(other_id)
        
        for rel_name, other_id in self.get_related(pi_id, direction='in'):
            entity = self.entities.get(other_id, {})
            if self.get_type_name(entity) == 'Section' and other_id not in seen_section_ids:
                all_sections.append((rel_name, other_id))
                seen_section_ids.add(other_id)
        
        print(f"\n{'SECTIONS':<25}")
        if all_sections:
            # Group sections by type if available
            sections_by_type = defaultdict(list)
            for rel_name, section_id in all_sections:
                section_props = self.get_entity_props(section_id)
                section_name = self.entities.get(section_id, {}).get('name', 'Unknown')
                section_type = section_props.get('section_type', 'Unknown')
                sections_by_type[section_type].append((section_name, section_id, section_props))
            
            total_sections = sum(len(v) for v in sections_by_type.values())
            print(f"  Found {total_sections} sections in {len(sections_by_type)} categories\n")
            
            for section_type, sections in sorted(sections_by_type.items()):
                print(f"\n  [{section_type}] ({len(sections)} sections)")
                for section_name, section_id, section_props in sections[:3]:
                    # Truncate long names
                    display_name = section_name[:70] + "..." if len(section_name) > 70 else section_name
                    print(f"    • {display_name}")
                    # Show some content preview if available
                    content = section_props.get('content', '')
                    if content:
                        preview = content[:100].replace('\n', ' ').strip()
                        print(f"      Preview: {preview}...")
                if len(sections) > 3:
                    print(f"    ... and {len(sections) - 3} more sections of this type")
        else:
            print("  No sections found")
        
        # Display raw section details for first few
        print(f"\n{'SECTION DETAILS (first 5)':<25}")
        for i, (rel_name, section_id) in enumerate(all_sections[:5]):
            section_entity = self.entities.get(section_id, {})
            section_props = self.get_entity_props(section_id)
            section_name = section_entity.get('name', 'Unknown')
            section_type = section_props.get('section_type', 'Unknown')
            
            print(f"\n  ┌─ Section {i+1} ─────────────────────────────────────────────────────────────┐")
            print(f"  │ Name:       {section_name[:75]}│")
            print(f"  │ Type:       {section_type:<75}│")
            print(f"  │ Relation:   {rel_name:<75}│")
            
            # Show content preview
            content = section_props.get('content', '')
            if content:
                lines = content.split('\n')[:5]
                print(f"  │ Content Preview:                                                              │")
                for line in lines:
                    line = line.strip()[:73]
                    print(f"  │   {line:<73}│")
                if len(content.split('\n')) > 5:
                    print(f"  │   ... ({len(content.split(chr(10))) - 5} more lines){' ' * (57 - len(str(len(content.split(chr(10))) - 5)))}│")
            print(f"  └──────────────────────────────────────────────────────────────────────────────┘")
        
        if len(all_sections) > 5:
            print(f"\n  ... and {len(all_sections) - 5} more sections")
        
        print()
    
    def explore_section_types(self):
        """List all section types in the knowledge graph"""
        section_type = self.schema.types.get('Section')
        section_type_prop = self.schema.properties.get('section_type')
        
        type_counts = defaultdict(int)
        section_count = 0
        
        for eid, entity in self.entities.items():
            if section_type in entity.get('types', []):
                section_count += 1
                for v in entity.get('values', []):
                    if v.get('property') == section_type_prop:
                        stype = v.get('value', 'Unknown')
                        type_counts[stype] += 1
                        break
        
        print(f"\nTotal Sections: {section_count:,}")
        print(f"\nSection Types:")
        for stype, count in sorted(type_counts.items(), key=lambda x: -x[1])[:30]:
            print(f"  {stype:<50}: {count:>6,}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python package_insert_viewer.py <drug_name>   # View package inserts for a drug")
        print("  python package_insert_viewer.py --section-types  # List all section types")
        sys.exit(1)
    
    arg = sys.argv[1]
    
    viewer = PackageInsertViewer()
    
    if arg == '--section-types':
        viewer.explore_section_types()
    else:
        viewer.view_package_inserts(arg)


if __name__ == '__main__':
    main()
