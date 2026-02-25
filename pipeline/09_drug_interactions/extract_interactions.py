#!/usr/bin/env python3
"""
Drug-Drug Interaction Extraction v7 - PARALLEL BATCHED
"""
import os
import json
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional
import asyncio
import httpx
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import time

XML_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop/data/dailymed/xml_only")
OUTPUT_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop/data/interactions")
OUTPUT_FILE = OUTPUT_DIR / "interactions_structured.json"
MANIFEST_FILE = OUTPUT_DIR / "extraction_manifest.json"
VENICE_API_KEY = "VENICE-INFERENCE-KEY-REDACTED"
VENICE_MODEL = "venice-uncensored"

BATCH_SIZE = 10
PARALLEL_BATCHES = 5
SAVE_INTERVAL = 20

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BATCH_PROMPT = """Extract drug interactions from these FDA package inserts. Return JSON only.

DRUGS:
{drugs_text}

Format: {{"Drug Name": [{{"interacting_drug":"name","severity":"MAJOR/MODERATE/MINOR/UNKNOWN","mechanism":"brief","clinical_impact":"effect","recommendation":"action"}}]}}"""


def load_manifest() -> Dict:
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE, 'r') as f:
            return json.load(f)
    return {"created_at": datetime.now().isoformat(), "processed_set_ids": {}, "stats": {"total_files": 0, "with_interactions": 0, "total_interactions": 0}}


def save_manifest(manifest: Dict):
    manifest["updated_at"] = datetime.now().isoformat()
    with open(MANIFEST_FILE, 'w') as f:
        json.dump(manifest, f, indent=2)


def parse_xml_for_interactions(xml_path: Path) -> Optional[Dict]:
    try:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
        
        set_id = None
        for elem in root.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag.lower() == 'setid':
                set_id = elem.attrib.get('root', elem.text)
                break
            for attr, val in elem.attrib.items():
                if 'setid' in attr.lower() and val:
                    set_id = val
                    break
        if not set_id:
            return None
        
        drug_name = None
        for elem in root.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag == 'manufacturedDrug':
                for child in elem.iter():
                    child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    if child_tag == 'name' and child.text:
                        drug_name = child.text.strip()
                        break
            if drug_name:
                break
        
        if not drug_name:
            for elem in root.iter():
                tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                if tag == 'manufacturedProduct':
                    for child in elem.iter():
                        child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                        if child_tag == 'name' and child.text:
                            text = child.text.strip()
                            if not any(x in text.lower() for x in ['inc', 'llc', 'ltd', 'pharma', 'corp']):
                                drug_name = text
                                break
                if drug_name:
                    break
        
        if not drug_name:
            drug_name = "Unknown Drug"
        
        interaction_text = None
        for section in root.iter():
            if section.get('code') == '34070-8':
                text_parts = [elem.text.strip() for elem in section.iter() if elem.text and elem.text.strip()]
                interaction_text = ' '.join(text_parts) if text_parts else None
                break
        
        if not interaction_text:
            for section in root.iter():
                for child in section:
                    tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    if tag == 'title' and 'drug interaction' in (child.text or '').lower():
                        text_parts = [elem.text.strip() for elem in section.iter() if elem.text and elem.text.strip()]
                        interaction_text = ' '.join(text_parts) if len(text_parts) > 1 else None
                        break
                if interaction_text:
                    break
        
        if not interaction_text or len(interaction_text) < 100:
            return None
        
        return {
            'set_id': set_id,
            'drug_name': drug_name,
            'drug_id': xml_path.stem,
            'interaction_text': interaction_text[:1500]
        }
    except:
        return None


async def extract_batch(client: httpx.AsyncClient, batch: List[Dict], batch_num: int) -> tuple:
    drugs_text = ""
    for drug in batch:
        drugs_text += f"
[{drug['drug_name']}]
{drug['interaction_text']}
"
    
    prompt = BATCH_PROMPT.format(drugs_text=drugs_text)
    
    try:
        response = await client.post(
            "https://api.venice.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {VENICE_API_KEY}"},
            json={
                "model": VENICE_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 4000
            },
            timeout=120.0
        )
        
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            
            if '```' in content:
                content = content.split('```')[1]
                if content.startswith('json'):
                    content = content[4:]
            
            results = json.loads(content.strip())
            
            timestamp = datetime.now().isoformat()
            interactions = []
            for drug in batch:
                drug_results = results.get(drug['drug_name'], [])
                for ext in drug_results:
                    interactions.append({
                        "subject_drug": drug['drug_name'],
                        "subject_drug_id": drug['drug_id'],
                        "set_id": drug['set_id'],
                        "interacting_drug": ext.get('interacting_drug', 'Unknown'),
                        "severity": ext.get('severity', 'UNKNOWN'),
                        "mechanism": ext.get('mechanism'),
                        "clinical_impact": ext.get('clinical_impact'),
                        "recommendation": ext.get('recommendation'),
                        "source_text": drug['interaction_text'][:500],
                        "citation": f"{drug['drug_name']} [package insert]. Set ID: {drug['set_id']}",
                        "extracted_at": timestamp
                    })
            
            return (batch_num, batch, interactions)
        else:
            print(f"
  Batch {batch_num}: API error {response.status_code}")
    except Exception as e:
        print(f"
  Batch {batch_num}: Error - {e}")
    
    return (batch_num, batch, [])


async def main(limit: int = 0):
    print("=" * 60)
    print("Drug-Drug Interaction Extraction v7 (PARALLEL BATCHED)")
    print(f"  Batch size: {BATCH_SIZE} drugs")
    print(f"  Parallel batches: {PARALLEL_BATCHES}")
    print("=" * 60)
    
    manifest = load_manifest()
    processed_set_ids = set(manifest['processed_set_ids'].keys())
    print(f"Resuming: {len(processed_set_ids)} already processed")
    
    print("
[Phase 1] Scanning XML files...")
    xml_files = sorted(XML_DIR.glob("*.xml"))
    total_files = len(xml_files)
    if limit:
        xml_files = xml_files[:limit]
    
    start_scan = time.time()
    with ThreadPoolExecutor(max_workers=20) as executor:
        all_drugs = list(filter(None, executor.map(parse_xml_for_interactions, xml_files)))
    scan_time = time.time() - start_scan
    
    print(f"  Scanned {len(xml_files)} files in {scan_time:.1f}s")
    print(f"  Found {len(all_drugs)} with interaction sections")
    
    drugs_to_process = [d for d in all_drugs if d['set_id'] not in processed_set_ids]
    print(f"  {len(drugs_to_process)} need processing")
    
    if not drugs_to_process:
        print("Nothing to process!")
        return
    
    print(f"
[Phase 2] Processing with {PARALLEL_BATCHES} parallel batches...")
    
    all_interactions = []
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, 'r') as f:
            all_interactions = json.load(f)
    
    manifest['stats']['total_files'] = total_files
    manifest['stats']['with_interactions'] = len(all_drugs)
    
    batches = [(i, drugs_to_process[i:i + BATCH_SIZE]) for i in range(0, len(drugs_to_process), BATCH_SIZE)]
    
    start_process = time.time()
    processed = 0
    
    async with httpx.AsyncClient() as client:
        semaphore = asyncio.Semaphore(PARALLEL_BATCHES)
        
        async def bounded_extract(batch_info):
            batch_num, batch = batch_info
            async with semaphore:
                return await extract_batch(client, batch, batch_num)
        
        tasks = [bounded_extract(b) for b in batches]
        
        for coro in asyncio.as_completed(tasks):
            batch_num, batch, interactions = await coro
            all_interactions.extend(interactions)
            processed += len(batch)
            
            timestamp = datetime.now().isoformat()
            for drug in batch:
                count = len([i for i in interactions if i['set_id'] == drug['set_id']])
                manifest['processed_set_ids'][drug['set_id']] = {
                    "file": drug['drug_id'],
                    "drug_name": drug['drug_name'],
                    "timestamp": timestamp,
                    "interactions_count": count
                }
            manifest['stats']['total_interactions'] = len(all_interactions)
            
            elapsed = time.time() - start_process
            rate = processed / (elapsed / 60) if elapsed > 0 else 0
            print(f"  Batch {batch_num}/{len(batches)}: {len(interactions)} interactions | {processed}/{len(drugs_to_process)} drugs | {rate:.0f}/min")
            
            if processed % (SAVE_INTERVAL * BATCH_SIZE) == 0:
                with open(OUTPUT_FILE, 'w') as f:
                    json.dump(all_interactions, f)
                save_manifest(manifest)
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(all_interactions, f, indent=2)
    save_manifest(manifest)
    
    process_time = time.time() - start_process
    rate = processed / (process_time / 60) if process_time > 0 else 0
    print(f"
{'='*60}")
    print(f"DONE!")
    print(f"  Phase 1 (scan): {scan_time:.1f}s")
    print(f"  Phase 2 (extract): {process_time:.1f}s ({process_time/60:.1f} min)")
    print(f"  Total interactions: {len(all_interactions)}")
    print(f"  Rate: {rate:.0f} drugs/min")


if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    asyncio.run(main(limit))
