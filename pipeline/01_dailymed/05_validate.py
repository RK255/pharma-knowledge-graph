#!/usr/bin/env python3
"""
Fixed Provenance Verification System for Drug Knowledge Graph
Corrects the hash consistency calculation issue and adds provenance spot checks.
"""

import os
import json
import logging
import argparse
import hashlib
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
from collections import defaultdict

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class FixedProvenanceVerifier:
    """Fixed verifier for provenance data with corrected hash consistency calculation and spot checks."""
    
    def __init__(self, ledger_file: str, documents_file: str, kg_file: str, output_dir: str):
        self.ledger_file = ledger_file
        self.documents_file = documents_file
        self.kg_file = kg_file
        self.output_dir = output_dir
        
        # Load all data
        self.ledger = self._load_ledger()
        self.documents = self._load_documents()
        self.kg = self._load_kg()
        
        # Initialize verification results
        self.verification_results = {
            'completeness': {},
            'integrity': {},
            'provenance': {},
            'spot_checks': {},
            'summary': {}
        }
    
    def _load_ledger(self) -> Dict[str, Any]:
        if os.path.exists(self.ledger_file):
            with open(self.ledger_file, 'r') as f:
                return json.load(f)
        return {}
    
    def _load_documents(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.documents_file):
            with open(self.documents_file, 'r') as f:
                return json.load(f)
        return []
    
    def _load_kg(self) -> Dict[str, Any]:
        if os.path.exists(self.kg_file):
            with open(self.kg_file, 'r') as f:
                return json.load(f)
        return {'nodes': [], 'relationships': []}
    
    def get_provenance_examples(self) -> List[Dict[str, Any]]:
        """Get 3 random examples of provenance records for spot checking."""
        examples = []
        
        # Collect all provenance hashes with their records
        all_provenance = []
        
        # Get document provenance
        for doc in self.documents:
            prov_hash = doc.get('provenance_hash')
            if prov_hash:
                # Find the corresponding ledger entry
                prov_record = None
                for data_type, entries in self.ledger.items():
                    if data_type not in ['metadata', 'sources'] and prov_hash in entries:
                        prov_record = entries[prov_hash]
                        break
                
                all_provenance.append({
                    'type': 'document',
                    'hash': prov_hash,
                    'title': doc.get('title', 'Unknown'),
                    'record': prov_record
                })
        
        # Get section provenance
        for doc in self.documents:
            for section in doc.get('sections', []):
                prov_hash = section.get('provenance_hash')
                if prov_hash:
                    # Find the corresponding ledger entry
                    prov_record = None
                    for data_type, entries in self.ledger.items():
                        if data_type not in ['metadata', 'sources'] and prov_hash in entries:
                            prov_record = entries[prov_hash]
                            break
                    
                    all_provenance.append({
                        'type': 'section',
                        'hash': prov_hash,
                        'title': section.get('title', 'Unknown'),
                        'parent_doc': doc.get('title', 'Unknown'),
                        'record': prov_record
                    })
        
        # Get relationship provenance
        for rel in self.kg['relationships']:
            prov_hash = rel.get('properties', {}).get('provenance_fda_spl')
            if prov_hash:
                # Find the corresponding ledger entry
                prov_record = None
                for data_type, entries in self.ledger.items():
                    if data_type not in ['metadata', 'sources'] and prov_hash in entries:
                        prov_record = entries[prov_hash]
                        break
                
                all_provenance.append({
                    'type': 'relationship',
                    'hash': prov_hash,
                    'relationship_type': rel.get('type', 'Unknown'),
                    'record': prov_record
                })
        
        # Randomly select 3 examples
        if len(all_provenance) >= 3:
            examples = random.sample(all_provenance, 3)
        else:
            examples = all_provenance
        
        return examples
    
    def verify_completeness(self) -> Dict[str, Any]:
        """Verify data completeness across documents and knowledge graph."""
        logger.info("Verifying data completeness...")
        
        results = {
            'documents': {},
            'sections': {},
            'nodes': {},
            'relationships': {}
        }
        
        # Document completeness
        total_docs = len(self.documents)
        docs_with_applications = sum(1 for doc in self.documents if 'application_type' in doc)
        docs_with_ndc = sum(1 for doc in self.documents if doc.get('ndc_codes'))
        docs_with_manufacturer = sum(1 for doc in self.documents if doc.get('manufacturer'))
        
        results['documents'] = {
            'total': total_docs,
            'with_applications': docs_with_applications,
            'with_ndc': docs_with_ndc,
            'with_manufacturer': docs_with_manufacturer,
            'application_coverage': (docs_with_applications / total_docs * 100) if total_docs > 0 else 0,
            'ndc_coverage': (docs_with_ndc / total_docs * 100) if total_docs > 0 else 0,
            'manufacturer_coverage': (docs_with_manufacturer / total_docs * 100) if total_docs > 0 else 0
        }
        
        # Section completeness
        section_counts = defaultdict(int)
        total_sections = 0
        
        for doc in self.documents:
            for section in doc.get('sections', []):
                section_type = section.get('section_type', 'UNKNOWN')
                section_counts[section_type] += 1
                total_sections += 1
        
        results['sections'] = {
            'total': total_sections,
            'by_type': dict(section_counts)
        }
        
        # Node completeness
        total_nodes = len(self.kg['nodes'])
        node_types = defaultdict(int)
        nodes_with_provenance = 0
        
        for node in self.kg['nodes']:
            node_type = node.get('labels', ['UNKNOWN'])[0]
            node_types[node_type] += 1
            
            if 'provenance_fda_spl' in node.get('properties', {}):
                nodes_with_provenance += 1
        
        results['nodes'] = {
            'total': total_nodes,
            'by_type': dict(node_types),
            'with_provenance': nodes_with_provenance,
            'provenance_coverage': (nodes_with_provenance / total_nodes * 100) if total_nodes > 0 else 0
        }
        
        # Relationship completeness
        total_rels = len(self.kg['relationships'])
        rel_types = defaultdict(int)
        rels_with_provenance = 0
        
        for rel in self.kg['relationships']:
            rel_type = rel.get('type', 'UNKNOWN')
            rel_types[rel_type] += 1
            
            if 'provenance_fda_spl' in rel.get('properties', {}):
                rels_with_provenance += 1
        
        results['relationships'] = {
            'total': total_rels,
            'by_type': dict(rel_types),
            'with_provenance': rels_with_provenance,
            'provenance_coverage': (rels_with_provenance / total_rels * 100) if total_rels > 0 else 0
        }
        
        return results
    
    def verify_integrity(self) -> Dict[str, Any]:
        """Verify data integrity across documents and knowledge graph."""
        logger.info("Verifying data integrity...")
        
        results = {
            'document_section_relationships': {},
            'node_relationship_consistency': {},
            'provenance_hash_consistency': {}
        }
        
        # Document-section relationship integrity
        doc_sections_map = defaultdict(set)
        for doc in self.documents:
            doc_id = doc.get('unique_id', '')
            for section in doc.get('sections', []):
                section_id = section.get('section_unique_id', '')
                doc_sections_map[doc_id].add(section_id)
        
        # Check if all document-section relationships exist in KG
        doc_section_rels_in_kg = set()
        for rel in self.kg['relationships']:
            if rel.get('type') in ['HAS_SECTION', 'HAS_BOXED_WARNING', 'HAS_INDICATIONS', 'HAS_DOSAGE_INFO', 
                                  'HAS_DOSAGE_FORMS', 'HAS_CONTRAINDICATIONS', 'HAS_WARNINGS', 
                                  'HAS_ADVERSE_REACTIONS', 'HAS_DRUG_INTERACTIONS', 'HAS_SPECIAL_POPULATIONS_INFO',
                                  'HAS_ABUSE_INFO', 'HAS_OVERDOSAGE_INFO', 'HAS_DESCRIPTION', 'HAS_PHARMACOLOGY',
                                  'HAS_TOXICOLOGY', 'HAS_SUPPLY_INFO', 'HAS_PATIENT_INFO', 'HAS_CLINICAL_STUDIES',
                                  'HAS_REFERENCES', 'HAS_OTHER_INFO']:
                doc_section_rels_in_kg.add((rel.get('start_node'), rel.get('end_node')))
        
        # Find missing relationships
        missing_rels = 0
        for doc_id, section_ids in doc_sections_map.items():
            for section_id in section_ids:
                if (doc_id, section_id) not in doc_section_rels_in_kg:
                    missing_rels += 1
        
        results['document_section_relationships'] = {
            'document_section_pairs': sum(len(sids) for sids in doc_sections_map.values()),
            'relationships_in_kg': len(doc_section_rels_in_kg),
            'missing_relationships': missing_rels,
            'integrity_score': (len(doc_section_rels_in_kg) / sum(len(sids) for sids in doc_sections_map.values()) * 100) if doc_sections_map else 100
        }
        
        # Node-relationship consistency
        node_ids_in_kg = set(node.get('id') for node in self.kg['nodes'])
        rel_start_nodes = set(rel.get('start_node') for rel in self.kg['relationships'])
        rel_end_nodes = set(rel.get('end_node') for rel in self.kg['relationships'])
        
        orphan_rels = 0
        for rel in self.kg['relationships']:
            start = rel.get('start_node')
            end = rel.get('end_node')
            if start not in node_ids_in_kg or end not in node_ids_in_kg:
                orphan_rels += 1
        
        results['node_relationship_consistency'] = {
            'total_nodes': len(node_ids_in_kg),
            'unique_start_nodes': len(rel_start_nodes),
            'unique_end_nodes': len(rel_end_nodes),
            'orphan_relationships': orphan_rels,
            'consistency_score': ((len(self.kg['relationships']) - orphan_rels) / len(self.kg['relationships']) * 100) if self.kg['relationships'] else 100
        }
        
        # FIXED: Provenance hash consistency calculation
        prov_hashes_in_ledger = set()
        for data_type, entries in self.ledger.items():
            if data_type not in ['metadata', 'sources']:
                prov_hashes_in_ledger.update(entries.keys())
        
        prov_hashes_in_docs = set()
        for doc in self.documents:
            prov_hash = doc.get('provenance_hash')
            if prov_hash:
                prov_hashes_in_docs.add(prov_hash)
            
            for section in doc.get('sections', []):
                prov_hash = section.get('provenance_hash')
                if prov_hash:
                    prov_hashes_in_docs.add(prov_hash)
        
        prov_hashes_in_kg = set()
        for node in self.kg['nodes']:
            prov_hash = node.get('properties', {}).get('provenance_fda_spl')
            if prov_hash:
                prov_hashes_in_kg.add(prov_hash)
        
        for rel in self.kg['relationships']:
            prov_hash = rel.get('properties', {}).get('provenance_fda_spl')
            if prov_hash:
                prov_hashes_in_kg.add(prov_hash)
        
        # FIXED: Calculate consistency as the percentage of document hashes that appear in both ledger and KG
        docs_in_ledger = prov_hashes_in_docs & prov_hashes_in_ledger
        docs_in_kg = prov_hashes_in_docs & prov_hashes_in_kg
        
        consistency_score = 0
        if prov_hashes_in_docs:
            # Calculate what percentage of document hashes are in both ledger and KG
            docs_in_both = prov_hashes_in_docs & prov_hashes_in_ledger & prov_hashes_in_kg
            consistency_score = (len(docs_in_both) / len(prov_hashes_in_docs)) * 100
        
        results['provenance_hash_consistency'] = {
            'hashes_in_ledger': len(prov_hashes_in_ledger),
            'hashes_in_documents': len(prov_hashes_in_docs),
            'hashes_in_kg': len(prov_hashes_in_kg),
            'docs_in_ledger': len(docs_in_ledger),
            'docs_in_kg': len(docs_in_kg),
            'docs_in_both': len(prov_hashes_in_docs & prov_hashes_in_ledger & prov_hashes_in_kg),
            'consistency_score': consistency_score
        }
        
        return results
    
    def verify_provenance(self) -> Dict[str, Any]:
        """Verify provenance data quality and completeness."""
        logger.info("Verifying provenance data...")
        
        results = {
            'source_tracking': {},
            'citation_quality': {},
            'temporal_consistency': {}
        }
        
        # Source tracking
        source_usage = defaultdict(int)
        source_dates = {}
        
        for source, info in self.ledger.get('sources', {}).items():
            source_usage[source] = info.get('usage_count', 0)
            source_dates[source] = {
                'first_used': info.get('first_used', ''),
                'last_used': info.get('last_used', '')
            }
        
        results['source_tracking'] = {
            'total_sources': len(source_usage),
            'source_usage': dict(source_usage),
            'source_dates': source_dates
        }
        
        # Citation quality
        docs_with_citations = 0
        sections_with_citations = 0
        total_sections = 0
        
        for doc in self.documents:
            if doc.get('ama_citation'):
                docs_with_citations += 1
            
            for section in doc.get('sections', []):
                total_sections += 1
                if section.get('citation'):
                    sections_with_citations += 1
        
        results['citation_quality'] = {
            'documents_with_citations': docs_with_citations,
            'document_citation_rate': (docs_with_citations / len(self.documents) * 100) if self.documents else 0,
            'sections_with_citations': sections_with_citations,
            'section_citation_rate': (sections_with_citations / total_sections * 100) if total_sections > 0 else 0
        }
        
        # Temporal consistency
        dates_in_docs = set()
        dates_in_provenance = set()
        
        for doc in self.documents:
            effective_time = doc.get('effective_time')
            if effective_time:
                dates_in_docs.add(effective_time[:4])  # Extract year
        
        for data_type, entries in self.ledger.items():
            if data_type not in ['metadata', 'sources']:
                for prov_hash, prov_data in entries.items():
                    date = prov_data.get('date_accessed')
                    if date:
                        dates_in_provenance.add(date[:4])  # Extract year
        
        results['temporal_consistency'] = {
            'years_in_documents': sorted(dates_in_docs),
            'years_in_provenance': sorted(dates_in_provenance),
            'date_range_consistent': len(dates_in_docs & dates_in_provenance) > 0
        }
        
        return results
    
    def run_spot_checks(self) -> Dict[str, Any]:
        """Run spot checks on provenance records."""
        logger.info("Running provenance spot checks...")
        
        examples = self.get_provenance_examples()
        
        spot_check_results = {
            'total_examples': len(examples),
            'examples': []
        }
        
        for i, example in enumerate(examples):
            example_data = {
                'example_number': i + 1,
                'type': example['type'],
                'hash': example['hash'],
                'title': example.get('title', 'N/A'),
                'parent_doc': example.get('parent_doc', 'N/A'),
                'relationship_type': example.get('relationship_type', 'N/A'),
                'provenance_record': example.get('record', {})
            }
            spot_check_results['examples'].append(example_data)
        
        return spot_check_results
    
    def run_verification(self) -> Dict[str, Any]:
        """Run all verification checks and generate a comprehensive report."""
        logger.info("Running comprehensive provenance verification...")
        
        # Run all verification checks
        self.verification_results['completeness'] = self.verify_completeness()
        self.verification_results['integrity'] = self.verify_integrity()
        self.verification_results['provenance'] = self.verify_provenance()
        self.verification_results['spot_checks'] = self.run_spot_checks()
        
        # Generate summary scores
        completeness_score = (
            self.verification_results['completeness']['documents']['application_coverage'] +
            self.verification_results['completeness']['nodes']['provenance_coverage'] +
            self.verification_results['completeness']['relationships']['provenance_coverage']
        ) / 3
        
        integrity_score = (
            self.verification_results['integrity']['document_section_relationships']['integrity_score'] +
            self.verification_results['integrity']['node_relationship_consistency']['consistency_score'] +
            self.verification_results['integrity']['provenance_hash_consistency']['consistency_score']
        ) / 3
        
        provenance_score = (
            min(100, self.verification_results['provenance']['citation_quality']['document_citation_rate'] * 1.25) +
            min(100, self.verification_results['provenance']['citation_quality']['section_citation_rate'] * 1.25)
        ) / 2
        
        self.verification_results['summary'] = {
            'overall_score': (completeness_score + integrity_score + provenance_score) / 3,
            'completeness_score': completeness_score,
            'integrity_score': integrity_score,
            'provenance_score': provenance_score
        }
        
        # Save verification results
        with open(os.path.join(self.output_dir, 'fixed_provenance_verification.json'), 'w') as f:
            json.dump(self.verification_results, f, indent=2)
        
        return self.verification_results
    
    def print_summary(self):
        """Print a summary of the verification results."""
        print("\n=== FIXED PROVENANCE VERIFICATION SUMMARY ===")
        
        summary = self.verification_results['summary']
        print(f"Overall Score: {summary['overall_score']:.1f}/100")
        print(f"Completeness Score: {summary['completeness_score']:.1f}/100")
        print(f"Integrity Score: {summary['integrity_score']:.1f}/100")
        print(f"Provenance Score: {summary['provenance_score']:.1f}/100")
        
        print("\n=== COMPLETENESS HIGHLIGHTS ===")
        comp = self.verification_results['completeness']
        print(f"Documents with Applications: {comp['documents']['application_coverage']:.1f}%")
        print(f"Documents with NDC Codes: {comp['documents']['ndc_coverage']:.1f}%")
        print(f"Nodes with Provenance: {comp['nodes']['provenance_coverage']:.1f}%")
        print(f"Relationships with Provenance: {comp['relationships']['provenance_coverage']:.1f}%")
        
        print("\n=== INTEGRITY HIGHLIGHTS ===")
        integ = self.verification_results['integrity']
        print(f"Document-Section Relationships: {integ['document_section_relationships']['integrity_score']:.1f}%")
        print(f"Node-Relationship Consistency: {integ['node_relationship_consistency']['consistency_score']:.1f}%")
        print(f"Provenance Hash Consistency: {integ['provenance_hash_consistency']['consistency_score']:.1f}%")
        
        print("\n=== PROVENANCE HIGHLIGHTS ===")
        prov = self.verification_results['provenance']
        print(f"Document Citation Rate: {prov['citation_quality']['document_citation_rate']:.1f}%")
        print(f"Section Citation Rate: {prov['citation_quality']['section_citation_rate']:.1f}%")
        print(f"Sources Tracked: {prov['source_tracking']['total_sources']}")
        
        # Add hash consistency details
        hash_consistency = integ['provenance_hash_consistency']
        print(f"\nHash Consistency Details:")
        print(f"  Document hashes: {hash_consistency['hashes_in_documents']}")
        print(f"  In ledger: {hash_consistency['docs_in_ledger']}")
        print(f"  In KG: {hash_consistency['docs_in_kg']}")
        print(f"  In both: {hash_consistency['docs_in_both']}")
        
        # Add provenance spot checks
        print(f"\n=== PROVENANCE SPOT CHECKS ===")
        spot_checks = self.verification_results['spot_checks']
        print(f"Showing {spot_checks['total_examples']} random examples:")
        
        for example in spot_checks['examples']:
            print(f"\n--- Example {example['example_number']} ({example['type'].title()}) ---")
            print(f"Hash: {example['hash']}")
            if example['type'] == 'document':
                print(f"Title: {example['title']}")
            elif example['type'] == 'section':
                print(f"Section: {example['title']}")
                print(f"Parent Document: {example['parent_doc']}")
            elif example['type'] == 'relationship':
                print(f"Relationship Type: {example['relationship_type']}")
            
            # Show key fields from provenance record
            prov_record = example.get('provenance_record', {})
            print(f"Source: {prov_record.get('source', 'N/A')}")
            print(f"Data Type: {prov_record.get('data_type', 'N/A')}")
            print(f"Date Accessed: {prov_record.get('date_accessed', 'N/A')}")
            
            # Show additional fields if available
            if 'fda_document_id' in prov_record:
                print(f"FDA Document ID: {prov_record['fda_document_id']}")
            if 'fda_section_id' in prov_record:
                print(f"FDA Section ID: {prov_record['fda_section_id']}")
            if 'section_type' in prov_record:
                print(f"Section Type: {prov_record['section_type']}")
        
        print(f"\nDetailed report saved to: {os.path.join(self.output_dir, 'fixed_provenance_verification.json')}")

def main():
    parser = argparse.ArgumentParser(description='Verify provenance data for the drug knowledge graph.')
    parser.add_argument('--output-dir', default='output', help='Output directory for processed data')
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    
    # Initialize verifier
    verifier = FixedProvenanceVerifier(
        ledger_file=str(output_dir / 'provenance_ledger.json'),
        documents_file=str(output_dir / 'enhanced_chunked_documents.json'),
        kg_file=str(output_dir / 'enhanced_kg_chunks.json'),
        output_dir=str(output_dir)
    )
    
    # Run verification
    results = verifier.run_verification()
    
    # Print summary
    verifier.print_summary()

if __name__ == '__main__':
    main()
