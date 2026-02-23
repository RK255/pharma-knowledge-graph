#!/usr/bin/env python3
"""
Reconstruct complete package inserts from the extracted chunks with options menu.
Updated to work with the v22 parser output format which creates individual JSON files.
Modified to automatically load only 10 documents for testing.
"""

import json
import os
import random
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
import subprocess
import glob
import hashlib

def reconstruct_package_insert_content(doc: Dict[str, Any]) -> str:
    """Reconstruct a single package insert from the extracted chunks and return as string."""
    try:
        # Get document identifiers
        fda_set_id = doc.get('set_id', '')
        fda_document_id = doc.get('fda_document_id', '')
        version = doc.get('version_number', '')
        
        # Try multiple field names for product name
        drug_name = (doc.get('product_name') or 
                    doc.get('drug_names', ['Unknown Drug'])[0] if doc.get('drug_names') else 
                    'Unknown Drug')
        
        if not fda_set_id:
            return f"Error: Document has no FDA Set ID"
        
        # Start building the content
        content = []
        
        # Add header information
        content.append("=" * 80)
        content.append(f"PACKAGE INSERT: {drug_name}")
        content.append("=" * 80)
        content.append("")
        
        # Add FDA identifiers
        content.append("FDA IDENTIFIERS:")
        content.append(f"  FDA Set ID: {fda_set_id}")
        content.append(f"  FDA Document ID: {fda_document_id}")
        content.append(f"  Version: {version}")
        
        # Add drug names
        drug_names = doc.get('drug_names', [])
        if drug_names:
            content.append(f"  Drug Names: {', '.join(drug_names)}")
        
        # Add manufacturer
        manufacturer = doc.get('manufacturer', '')
        if manufacturer:
            content.append(f"  Manufacturer: {manufacturer}")
        
        # Add effective time
        effective_time = doc.get('effective_time', '')
        if effective_time:
            content.append(f"  Effective Time: {effective_time}")
        
        # Add NDC codes
        ndc_codes = doc.get('ndc_codes', [])
        if ndc_codes:
            content.append(f"  NDC Codes: {', '.join(ndc_codes)}")
        
        # Add provenance information (truncated hash for display)
        prov_hash = doc.get('provenance_hash', '')
        if prov_hash:
            # Display full hash but add note about truncation
            content.append(f"  Provenance Hash: {prov_hash}")
            content.append(f"  Truncated Hash: {prov_hash[:16]}")
        
        content.append("")
        content.append("=" * 80)
        content.append("")
        
        # Add sections in a logical order
        section_order = [
            'BOXED_WARNING',
            'DESCRIPTION',
            'INDICATIONS_AND_USAGE',
            'CLINICAL_PHARMACOLOGY',
            'NONCLINICAL_TOXICOLOGY',
            'DOSAGE_FORMS_AND_STRENGTHS',
            'DOSAGE_AND_ADMINISTRATION',
            'CONTRAINDICATIONS',
            'WARNINGS_AND_PRECAUTIONS',
            'DRUG_INTERACTIONS',
            'USE_IN_SPECIFIC_POPULATIONS',
            'DRUG_ABUSE_AND_DEPENDENCE',
            'ADVERSE_REACTIONS',
            'OVERDOSAGE',
            'HOW_SUPPLIED',
            'INFORMATION_FOR_PATIENTS',
            'CLINICAL_STUDIES',
            'REFERENCES'
        ]
        
        # Get all sections - Changed structure for v22
        sections_dict = doc.get('sections', {})
        
        # Add sections in the specified order
        for section_type in section_order:
            if section_type in sections_dict:
                section = sections_dict[section_type]
                title = section.get('title', '')
                content_text = section.get('content', '')
                
                if title:
                    content.append(f"{title}")
                    content.append("-" * len(title))
                    content.append("")
                
                if content_text:
                    content.append(content_text)
                    content.append("")
        
        # Add other sections not in the ordered list
        other_sections = [s for s in sections_dict.keys() if s not in section_order]
        if other_sections:
            content.append("OTHER SECTIONS")
            content.append("-" * 13)
            content.append("")
            
            for section_type in other_sections:
                section = sections_dict[section_type]
                title = section.get('title', '')
                content_text = section.get('content', '')
                
                if title:
                    content.append(f"{title}")
                    content.append("-" * len(title))
                    content.append("")
                
                if content_text:
                    content.append(content_text)
                    content.append("")
        
        # Add footer
        content.append("")
        content.append("=" * 80)
        content.append("END OF PACKAGE INSERT")
        content.append("=" * 80)
        content.append("")
        content.append(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        content.append(f"Source File: {doc.get('file_path', 'Unknown')}")
        
        return '\n'.join(content)
    
    except Exception as e:
        return f"Error reconstructing package insert: {str(e)}"

def verify_provenance_hash(doc: Dict[str, Any]) -> bool:
    """Verify the provenance hash against the document content."""
    try:
        # Get the stored hash
        stored_hash = doc.get('provenance_hash', '')
        if not stored_hash:
            return False
        
        # Create a representation of the document for hashing
        # We'll use the set_id and sections content
        doc_repr = {
            'set_id': doc.get('set_id', ''),
            'sections': {}
        }
        
        # Add section content for verification
        sections = doc.get('sections', {})
        for section_type, section_data in sections.items():
            doc_repr['sections'][section_type] = {
                'title': section_data.get('title', ''),
                'content': section_data.get('content', '')
            }
        
        # Calculate the hash
        doc_string = json.dumps(doc_repr, sort_keys=True)
        calculated_hash = hashlib.sha256(doc_string.encode()).hexdigest()
        
        # Compare with stored hash
        return calculated_hash == stored_hash
    except Exception as e:
        print(f"Error verifying hash: {str(e)}")
        return False

def save_package_insert(content: str, doc: Dict[str, Any], output_dir: Path) -> str:
    """Save the reconstructed package insert to a file and return the filepath."""
    try:
        # Get document identifiers
        fda_set_id = doc.get('set_id', '')
        version = doc.get('version_number', '')
        
        # Try multiple field names for product name
        drug_name = (doc.get('product_name') or 
                    doc.get('drug_names', ['Unknown Drug'])[0] if doc.get('drug_names') else 
                    'Unknown Drug')
        
        # Sanitize drug name for filename
        safe_drug_name = "".join(c if c.isalnum() or c in (' ', '_') else '_' for c in drug_name).rstrip()
        
        # Create a filename for the reconstructed insert
        filename = f"{safe_drug_name}_SetID_{fda_set_id}_Ver_{version}.txt"
        filepath = output_dir / filename
        
        # Write the reconstructed insert to file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return str(filepath)
    
    except Exception as e:
        return f"Error saving package insert: {str(e)}"

def display_document_list(documents: List[Dict[str, Any]]) -> None:
    """Display a list of available documents with their index numbers."""
    print("\nAvailable Documents:")
    print("-" * 80)
    print(f"{'Index':<6} {'Drug Name':<40} {'FDA Set ID':<40}")
    print("-" * 80)
    
    for i, doc in enumerate(documents):
        # Try multiple field names for product name
        drug_name = (doc.get('product_name') or 
                    doc.get('drug_names', ['Unknown Drug'])[0] if doc.get('drug_names') else 
                    'Unknown Drug')
        
        fda_set_id = doc.get('set_id', 'Unknown')
        
        # Truncate for display
        drug_name = drug_name[:40]
        fda_set_id = fda_set_id[:40]
        
        print(f"{i:<6} {drug_name:<40} {fda_set_id:<40}")
    
    print("-" * 80)

def view_document_in_terminal(content: str) -> None:
    """Display the document content in the terminal with pagination."""
    try:
        # Try to use 'less' for pagination if available
        try:
            process = subprocess.Popen(['less', '-R'], stdin=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            process.communicate(input=content)
        except (subprocess.SubprocessError, FileNotFoundError):
            # Fall back to 'more' if 'less' is not available
            try:
                process = subprocess.Popen(['more'], stdin=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                process.communicate(input=content)
            except (subprocess.SubprocessError, FileNotFoundError):
                # Fall back to printing directly if neither is available
                print("\n" + "=" * 80)
                print("DOCUMENT CONTENT")
                print("=" * 80)
                print(content)
                print("=" * 80)
                print("END OF DOCUMENT")
    except Exception as e:
        print(f"Error displaying document: {str(e)}")
        print("\n" + "=" * 80)
        print("DOCUMENT CONTENT")
        print("=" * 80)
        print(content)
        print("=" * 80)
        print("END OF DOCUMENT")

def reconstruct_single_document(documents: List[Dict[str, Any]], output_dir: Path) -> None:
    """Reconstruct a single document selected by the user."""
    display_document_list(documents)
    
    try:
        choice = input("\nEnter the index number of the document to reconstruct (or 'back' to return to menu): ")
        
        if choice.lower() == 'back':
            return
        
        index = int(choice)
        if 0 <= index < len(documents):
            doc = documents[index]
            
            # Try multiple field names for product name
            drug_name = (doc.get('product_name') or 
                        doc.get('drug_names', ['Unknown Drug'])[0] if doc.get('drug_names') else 
                        'Unknown Drug')
            
            # Verify the provenance hash
            is_valid = verify_provenance_hash(doc)
            print(f"\nProvenance hash verification: {'VALID' if is_valid else 'INVALID'}")
            
            # Reconstruct the document content
            content = reconstruct_package_insert_content(doc)
            
            if content.startswith("Error"):
                print(content)
                return
            
            # Ask what the user wants to do with the document
            while True:
                print("\n" + "=" * 60)
                print(f"Document: {drug_name}")
                print("=" * 60)
                print("1. View in terminal")
                print("2. Save to file")
                print("3. View and save")
                print("4. Verify provenance hash")
                print("5. Back to document list")
                print("6. Back to main menu")
                print("=" * 60)
                
                action = input("Enter your choice (1-6): ")
                
                if action == '1':
                    view_document_in_terminal(content)
                elif action == '2':
                    filepath = save_package_insert(content, doc, output_dir)
                    if filepath.startswith("Error"):
                        print(filepath)
                    else:
                        print(f"Saved to: {filepath}")
                    break
                elif action == '3':
                    view_document_in_terminal(content)
                    filepath = save_package_insert(content, doc, output_dir)
                    if filepath.startswith("Error"):
                        print(filepath)
                    else:
                        print(f"Saved to: {filepath}")
                    break
                elif action == '4':
                    is_valid = verify_provenance_hash(doc)
                    print(f"Provenance hash verification: {'VALID' if is_valid else 'INVALID'}")
                elif action == '5':
                    reconstruct_single_document(documents, output_dir)
                    return
                elif action == '6':
                    return
                else:
                    print("Invalid choice. Please enter a number between 1 and 6.")
        else:
            print("Invalid index number. Please try again.")
    except ValueError:
        print("Invalid input. Please enter a number.")

def reconstruct_all_documents(documents: List[Dict[str, Any]], output_dir: Path) -> None:
    """Reconstruct all documents."""
    print(f"Reconstructing {len(documents)} documents...")
    
    count = 0
    for doc in documents:
        content = reconstruct_package_insert_content(doc)
        if not content.startswith("Error"):
            filepath = save_package_insert(content, doc, output_dir)
            if not filepath.startswith("Error"):
                count += 1
    
    print(f"Reconstructed {count} package inserts in {output_dir}")

def load_documents_from_files(output_dir: Path) -> List[Dict[str, Any]]:
    """Load documents from individual JSON files created by v22 parser."""
    # Get all JSON files in the output directory
    json_files = glob.glob(str(output_dir / "*.json"))
    
    # Skip the processing stats file
    json_files = [f for f in json_files if not f.endswith('processing_stats.json')]
    
    documents = []
    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                doc = json.load(f)
                documents.append(doc)
        except Exception as e:
            print(f"Error loading {json_file}: {str(e)}")
    
    return documents

def main():
    # Load the documents from individual files created by v22 parser
    output_dir = Path('/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/development/output')
    
    if not output_dir.exists():
        print(f"Error: Output directory {output_dir} not found.")
        print("Please run the parser first to generate the document files.")
        return
    
    documents = load_documents_from_files(output_dir)
    
    if not documents:
        print("No documents found in the output directory.")
        return
    
    # Take a random sample of 10 documents
    print(f"Taking a random sample of 10 documents from {len(documents)} total documents")
    random.seed(42)  # For reproducible sampling
    documents = random.sample(documents, 10)
    
    # Create output directory for reconstructed inserts
    recon_output_dir = Path('reconstructed_inserts')
    recon_output_dir.mkdir(exist_ok=True)
    
    # Main menu loop
    while True:
        print("\n" + "=" * 60)
        print("Package Insert Reconstructor")
        print("=" * 60)
        print("1. Reconstruct a single document")
        print("2. Reconstruct all documents")
        print("3. Exit")
        print("=" * 60)
        
        choice = input("Enter your choice (1-3): ")
        
        if choice == '1':
            reconstruct_single_document(documents, recon_output_dir)
        elif choice == '2':
            reconstruct_all_documents(documents, recon_output_dir)
        elif choice == '3':
            print("Exiting the program.")
            break
        else:
            print("Invalid choice. Please enter a number between 1 and 3.")

if __name__ == '__main__':
    main()
