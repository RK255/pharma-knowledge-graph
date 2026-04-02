#!/usr/bin/env python3
"""
Drug Connection Graph Visualizer

Visualizes all connections from an ingredient to related entities.

Usage:
    python drug_graph_viz.py <drug_name>
    python drug_graph_viz.py cetirizine --output cetirizine_graph
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "grc20_v2"
SCHEMA_PATH = Path(__file__).parent / "00_schema"

sys.path.insert(0, str(SCHEMA_PATH))
from pharma_schema import PharmaSchema

class DrugGraphVisualizer:
    def __init__(self):
        self.schema = PharmaSchema()
        self.entities = {}
        self.entity_by_name = {}
        self.relations_from = {}
        self.relations_to = {}
        
        self.type_id_to_name = {v: k for k, v in self.schema.types.items()}
        self.rel_id_to_name = {v: k for k, v in self.schema.relations.items()}
        
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
    
    def get_entity_rxcui(self, eid):
        if eid not in self.entities:
            return None
        prop_id = self.schema.properties.get('rxcui')
        for v in self.entities[eid].get('values', []):
            if v.get('property') == prop_id:
                return v.get('value')
        return None
    
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
    
    def build_graph(self, drug_name, max_depth=3, max_per_type=10):
        """Build a connection graph starting from the ingredient"""
        ingredient_ids = self.entity_by_name.get(drug_name.lower(), [])
        if not ingredient_ids:
            return None
        
        ingredient_id = ingredient_ids[0]
        ingredient = self.entities[ingredient_id]
        
        graph = {
            'nodes': {},
            'edges': [],
            'stats': defaultdict(lambda: defaultdict(int))
        }
        
        # Add the root node
        root_rxcui = self.get_entity_rxcui(ingredient_id)
        graph['nodes'][ingredient_id] = {
            'id': ingredient_id,
            'name': drug_name,
            'type': 'Ingredient',
            'rxcui': root_rxcui,
            'level': 0
        }
        
        # Level 1: Direct connections from Ingredient
        level1_connections = {
            'BrandName': ('tradename_of', 'out'),
            'PreciseIngredient': ('form_of', 'out'),
            'MultipleIngredient': ('has_part', 'out'),
            'ClinicalDrugComponent': ('has_ingredient', 'out'),
            'ClinicalDrugForm': ('has_ingredient', 'out'),
            'ClinicalDrugGroup': ('has_ingredient', 'out'),
        }
        
        for target_type, (rel, direction) in level1_connections.items():
            targets = self.get_related_by_type(ingredient_id, rel, direction, target_type)
            targets = targets[:max_per_type]  # Limit
            
            for tid in targets:
                if tid not in graph['nodes']:
                    tname = self.get_entity_name(tid)
                    trxcui = self.get_entity_rxcui(tid)
                    graph['nodes'][tid] = {
                        'id': tid,
                        'name': tname,
                        'type': target_type,
                        'rxcui': trxcui,
                        'level': 1
                    }
                    graph['edges'].append({
                        'from': ingredient_id,
                        'to': tid,
                        'relation': rel,
                        'level': 1
                    })
                    graph['stats'][target_type]['count'] += 1
        
        # Level 2: From SCDC to SCD/SBD
        scdc_ids = [nid for nid, n in graph['nodes'].items() if n['type'] == 'ClinicalDrugComponent']
        for scdc_id in scdc_ids:
            # SCDC --consists_of--> SCD
            scd_ids = self.get_related_by_type(scdc_id, 'consists_of', 'out', 'ClinicalDrug')
            for scd_id in scd_ids[:max_per_type]:
                if scd_id not in graph['nodes']:
                    scd_name = self.get_entity_name(scd_id)
                    scd_rxcui = self.get_entity_rxcui(scd_id)
                    graph['nodes'][scd_id] = {
                        'id': scd_id,
                        'name': scd_name,
                        'type': 'ClinicalDrug',
                        'rxcui': scd_rxcui,
                        'level': 2
                    }
                    graph['stats']['ClinicalDrug']['count'] += 1
                graph['edges'].append({
                    'from': scdc_id,
                    'to': scd_id,
                    'relation': 'consists_of',
                    'level': 2
                })
            
            # SCDC --consists_of--> SBD
            sbd_ids = self.get_related_by_type(scdc_id, 'consists_of', 'out', 'BrandedDrug')
            for sbd_id in sbd_ids[:max_per_type]:
                if sbd_id not in graph['nodes']:
                    sbd_name = self.get_entity_name(sbd_id)
                    sbd_rxcui = self.get_entity_rxcui(sbd_id)
                    graph['nodes'][sbd_id] = {
                        'id': sbd_id,
                        'name': sbd_name,
                        'type': 'BrandedDrug',
                        'rxcui': sbd_rxcui,
                        'level': 2
                    }
                    graph['stats']['BrandedDrug']['count'] += 1
                graph['edges'].append({
                    'from': scdc_id,
                    'to': sbd_id,
                    'relation': 'consists_of',
                    'level': 2
                })
        
        # Level 3: From SBD to NDC and PackageInsert
        sbd_ids = [nid for nid, n in graph['nodes'].items() if n['type'] == 'BrandedDrug']
        for sbd_id in sbd_ids[:max_per_type]:
            # NDC --maps_to_rxcui--> SBD
            ndc_ids = self.get_related_by_type(sbd_id, 'maps_to_rxcui', 'in', 'NDC')
            for ndc_id in ndc_ids[:5]:  # Limit NDCs per SBD
                if ndc_id not in graph['nodes']:
                    ndc_name = self.get_entity_name(ndc_id)
                    graph['nodes'][ndc_id] = {
                        'id': ndc_id,
                        'name': ndc_name,
                        'type': 'NDC',
                        'rxcui': None,
                        'level': 3
                    }
                    graph['stats']['NDC']['count'] += 1
                graph['edges'].append({
                    'from': ndc_id,
                    'to': sbd_id,
                    'relation': 'maps_to_rxcui',
                    'level': 3
                })
            
            # PackageInsert --maps_to_rxcui--> SBD
            pi_ids = self.get_related_by_type(sbd_id, 'maps_to_rxcui', 'in', 'PackageInsert')
            for pi_id in pi_ids[:2]:  # Limit PIs per SBD
                if pi_id not in graph['nodes']:
                    pi_name = self.get_entity_name(pi_id)
                    graph['nodes'][pi_id] = {
                        'id': pi_id,
                        'name': pi_name,
                        'type': 'PackageInsert',
                        'rxcui': None,
                        'level': 3
                    }
                    graph['stats']['PackageInsert']['count'] += 1
                graph['edges'].append({
                    'from': pi_id,
                    'to': sbd_id,
                    'relation': 'maps_to_rxcui',
                    'level': 3
                })
        
        return graph
    
    def print_ascii_graph(self, graph, drug_name):
        """Print an ASCII visualization of the graph"""
        print("\n" + "=" * 100)
        print(f"CONNECTION GRAPH: {drug_name.upper()}")
        print("=" * 100)
        
        # Group nodes by type
        by_type = defaultdict(list)
        for nid, node in graph['nodes'].items():
            by_type[node['type']].append(node)
        
        # Type abbreviations
        type_abbrev = {
            'Ingredient': 'IN',
            'BrandName': 'BN',
            'PreciseIngredient': 'PIN',
            'MultipleIngredient': 'MIN',
            'ClinicalDrugComponent': 'SCDC',
            'ClinicalDrugForm': 'SCDF',
            'ClinicalDrugGroup': 'SCDG',
            'ClinicalDrug': 'SCD',
            'BrandedDrug': 'SBD',
            'NDC': 'NDC',
            'PackageInsert': 'PI',
        }
        
        # Level 0: Ingredient
        print("\n┌─────────────────────────────────────────────────────────────────────────────────────────────────┐")
        print("│  LEVEL 0: INGREDIENT (IN)                                                                        │")
        print("├─────────────────────────────────────────────────────────────────────────────────────────────────┤")
        for node in by_type.get('Ingredient', []):
            print(f"│  ● {node['name']:<40}  RXCUI: {node['rxcui']:<10}                                │")
        print("└─────────────────────────────────────────────────────────────────────────────────────────────────┘")
        
        # Level 1: Direct connections
        print("\n┌─────────────────────────────────────────────────────────────────────────────────────────────────┐")
        print("│  LEVEL 1: DIRECT CONNECTIONS                                                                    │")
        print("├─────────────────────────────────────────────────────────────────────────────────────────────────┤")
        
        level1_types = ['BrandName', 'PreciseIngredient', 'MultipleIngredient', 'ClinicalDrugComponent', 'ClinicalDrugForm']
        for t in level1_types:
            nodes = by_type.get(t, [])
            if nodes:
                abbrev = type_abbrev.get(t, t[:4])
                print(f"│                                                                                                  │")
                print(f"│  {abbrev} ({len(nodes)} nodes){'.' * (80 - len(abbrev) - len(str(len(nodes))) - 10)}│")
                for node in nodes[:5]:
                    rxcui_str = f"RXCUI: {node['rxcui']}" if node['rxcui'] else ""
                    print(f"│    → {node['name']:<50} {rxcui_str:<20}      │")
                if len(nodes) > 5:
                    print(f"│    ... and {len(nodes) - 5} more{'.' * 67}│")
        print("└─────────────────────────────────────────────────────────────────────────────────────────────────┘")
        
        # Level 2: Clinical Drugs and Branded Drugs
        print("\n┌─────────────────────────────────────────────────────────────────────────────────────────────────┐")
        print("│  LEVEL 2: CLINICAL DRUGS (SCD) & BRANDED DRUGS (SBD)                                            │")
        print("├─────────────────────────────────────────────────────────────────────────────────────────────────┤")
        
        scd_nodes = by_type.get('ClinicalDrug', [])
        sbd_nodes = by_type.get('BrandedDrug', [])
        
        print(f"│                                                                                                  │")
        print(f"│  SCD - Clinical Drugs ({len(scd_nodes)} total){'.' * (63 - len(str(len(scd_nodes))))}│")
        for node in scd_nodes[:5]:
            print(f"│    → {node['name'][:70]:<70}  RXCUI: {node['rxcui']:<10}│")
        if len(scd_nodes) > 5:
            print(f"│    ... and {len(scd_nodes) - 5} more{'.' * 67}│")
        
        print(f"│                                                                                                  │")
        print(f"│  SBD - Branded Drugs ({len(sbd_nodes)} total){'.' * (61 - len(str(len(sbd_nodes))))}│")
        for node in sbd_nodes[:5]:
            print(f"│    → {node['name'][:70]:<70}  RXCUI: {node['rxcui']:<10}│")
        if len(sbd_nodes) > 5:
            print(f"│    ... and {len(sbd_nodes) - 5} more{'.' * 67}│")
        print("└─────────────────────────────────────────────────────────────────────────────────────────────────┘")
        
        # Level 3: NDCs and Package Inserts
        print("\n┌─────────────────────────────────────────────────────────────────────────────────────────────────┐")
        print("│  LEVEL 3: NDCs & PACKAGE INSERTS                                                                │")
        print("├─────────────────────────────────────────────────────────────────────────────────────────────────┤")
        
        ndc_nodes = by_type.get('NDC', [])
        pi_nodes = by_type.get('PackageInsert', [])
        
        print(f"│                                                                                                  │")
        print(f"│  NDCs ({len(ndc_nodes)} total){'.' * (80 - len(str(len(ndc_nodes))) - 9)}│")
        for node in ndc_nodes[:5]:
            print(f"│    → {node['name']:<85}      │")
        if len(ndc_nodes) > 5:
            print(f"│    ... and {len(ndc_nodes) - 5} more{'.' * 67}│")
        
        print(f"│                                                                                                  │")
        print(f"│  Package Inserts ({len(pi_nodes)} total){'.' * (67 - len(str(len(pi_nodes))))}│")
        for node in pi_nodes[:5]:
            print(f"│    → {node['name'][:85]:<85}│")
        if len(pi_nodes) > 5:
            print(f"│    ... and {len(pi_nodes) - 5} more{'.' * 67}│")
        print("└─────────────────────────────────────────────────────────────────────────────────────────────────┘")
        
        # Summary statistics
        print("\n┌─────────────────────────────────────────────────────────────────────────────────────────────────┐")
        print("│  GRAPH STATISTICS                                                                               │")
        print("├─────────────────────────────────────────────────────────────────────────────────────────────────┤")
        print(f"│  Total Nodes: {len(graph['nodes']):<10}  Total Edges: {len(graph['edges']):<10}                                   │")
        print("│                                                                                                  │")
        print("│  Nodes by Type:                                                                                 │")
        for t in ['Ingredient', 'BrandName', 'PreciseIngredient', 'MultipleIngredient', 'ClinicalDrugComponent', 'ClinicalDrugForm', 'ClinicalDrug', 'BrandedDrug', 'NDC', 'PackageInsert']:
            count = len(by_type.get(t, []))
            if count > 0:
                abbrev = type_abbrev.get(t, t[:4])
                print(f"│    {abbrev:<4} ({t:<25}): {count:<10}{'.' * (50 - len(str(count)))}│")
        print("└─────────────────────────────────────────────────────────────────────────────────────────────────┘")
    
    def export_dot(self, graph, drug_name, output_path):
        """Export to GraphViz DOT format"""
        type_colors = {
            'Ingredient': '#FF6B6B',
            'BrandName': '#4ECDC4',
            'PreciseIngredient': '#45B7D1',
            'MultipleIngredient': '#96CEB4',
            'ClinicalDrugComponent': '#FFEAA7',
            'ClinicalDrugForm': '#DDA0DD',
            'ClinicalDrugGroup': '#98D8C8',
            'ClinicalDrug': '#F7DC6F',
            'BrandedDrug': '#BB8FCE',
            'NDC': '#85C1E9',
            'PackageInsert': '#F8B500',
        }
        
        type_abbrev = {
            'Ingredient': 'IN',
            'BrandName': 'BN',
            'PreciseIngredient': 'PIN',
            'MultipleIngredient': 'MIN',
            'ClinicalDrugComponent': 'SCDC',
            'ClinicalDrugForm': 'SCDF',
            'ClinicalDrugGroup': 'SCDG',
            'ClinicalDrug': 'SCD',
            'BrandedDrug': 'SBD',
            'NDC': 'NDC',
            'PackageInsert': 'PI',
        }
        
        with open(output_path, 'w') as f:
            f.write(f'digraph "{drug_name}_graph" {{\n')
            f.write('    rankdir=LR;\n')
            f.write('    node [shape=box, style="rounded,filled", fontname="Helvetica"];\n')
            f.write('    edge [fontname="Helvetica", fontsize=10];\n\n')
            
            # Group nodes by level
            for level in [0, 1, 2, 3]:
                nodes_at_level = [n for n in graph['nodes'].values() if n['level'] == level]
                if nodes_at_level:
                    f.write(f'    subgraph cluster_level_{level} {{\n')
                    f.write(f'        label="Level {level}";\n')
                    f.write('        style=dashed;\n')
                    for node in nodes_at_level:
                        color = type_colors.get(node['type'], '#CCCCCC')
                        abbrev = type_abbrev.get(node['type'], node['type'][:4])
                        label = f"{abbrev}\\n{node['name'][:30]}"
                        if node['rxcui']:
                            label += f"\\nRXCUI: {node['rxcui']}"
                        # Escape quotes in label
                        label = label.replace('"', '\\"')
                        f.write(f'        "{node["id"]}" [label="{label}", fillcolor="{color}"];\n')
                    f.write('    }\n\n')
            
            # Write edges
            f.write('\n')
            edge_labels = defaultdict(int)
            for edge in graph['edges']:
                key = (edge['from'], edge['to'])
                if edge_labels[key] == 0:  # Only write first occurrence
                    f.write(f'    "{edge["from"]}" -> "{edge["to"]}" [label="{edge["relation"]}"];\n')
                edge_labels[key] += 1
            
            f.write('}\n')
        
        print(f"\nDOT file exported to: {output_path}")
        print(f"To render: dot -Tpng {output_path} -o {output_path.replace('.dot', '.png')}")
    
    def export_json(self, graph, output_path):
        """Export to JSON format"""
        output = {
            'nodes': list(graph['nodes'].values()),
            'edges': graph['edges']
        }
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"JSON exported to: {output_path}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python drug_graph_viz.py <drug_name>")
        print("  python drug_graph_viz.py cetirizine --output cetirizine_graph")
        sys.exit(1)
    
    drug_name = sys.argv[1]
    output_base = None
    
    if '--output' in sys.argv:
        idx = sys.argv.index('--output')
        if idx + 1 < len(sys.argv):
            output_base = sys.argv[idx + 1]
    
    viz = DrugGraphVisualizer()
    graph = viz.build_graph(drug_name, max_per_type=15)
    
    if graph is None:
        print(f"Drug '{drug_name}' not found")
        sys.exit(1)
    
    viz.print_ascii_graph(graph, drug_name)
    
    if output_base:
        viz.export_dot(graph, drug_name, f"{output_base}.dot")
        viz.export_json(graph, f"{output_base}.json")


if __name__ == '__main__':
    main()
