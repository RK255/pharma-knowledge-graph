import requests
import os
import json
import time

drugs = [
    "Atorvastatin", "Metformin", "Levothyroxine", "Lisinopril", "Amlodipine",
    "Metoprolol", "Albuterol", "Losartan", "Gabapentin", "Omeprazole",
    "Sertraline", "Rosuvastatin", "Pantoprazole", "Escitalopram",
    "Dextroamphetamine", "Hydrochlorothiazide", "Bupropion", "Fluoxetine",
    "Semaglutide", "Montelukast", "Trazodone", "Simvastatin", "Amoxicillin",
    "Tamsulosin", "Acetaminophen; Hydrocodone", "Fluticasone", "Meloxicam",
    "Apixaban", "Furosemide", "Insulin Glargine", "Duloxetine", "Ibuprofen",
    "Famotidine", "Empagliflozin", "Carvedilol", "Tramadol", "Alprazolam",
    "Prednisone", "Hydroxyzine", "Buspirone", "Clopidogrel", "Glipizide",
    "Citalopram", "Potassium Chloride", "Allopurinol", "Aspirin",
    "Cyclobenzaprine", "Ergocalciferol", "Oxycodone", "Methylphenidate",
    "Venlafaxine", "Spironolactone", "Ondansetron", "Zolpidem", "Cetirizine",
    "Estradiol", "Pravastatin", "Hydrochlorothiazide; Lisinopril", "Lamotrigine",
    "Quetiapine", "Fluticasone; Salmeterol", "Clonazepam", "Azithromycin",
    "Hydrochlorothiazide; Losartan", "Amoxicillin; Clavulanate", "Latanoprost",
    "Cholecalciferol", "Propranolol", "Ezetimibe", "Topiramate", "Paroxetine",
    "Diclofenac", "Budesonide; Formoterol", "Atenolol", "Lisdexamfetamine",
    "Doxycycline", "Pregabalin", "Ethinyl Estradiol; Norethindrone", "Glimepiride",
    "Tizanidine", "Clonidine", "Fenofibrate", "Insulin Lispro", "Valsartan",
    "Cephalexin", "Baclofen", "Rivaroxaban", "Ferrous Sulfate", "Amitriptyline",
    "Finasteride", "Dapagliflozin", "Acetaminophen; Oxycodone", "Folic Acid",
    "Aripiprazole", "Olmesartan", "Ethinyl Estradiol; Norgestimate", "Valacyclovir",
    "Mirtazapine", "Lorazepam", "Levetiracetam"
]

from config import BASE_DIR
output_dir = str(BASE_DIR / "data" / "drug_descriptions")
os.makedirs(output_dir, exist_ok=True)

def find_section(sections, target_keywords):
    """Recursively search for a section matching keywords"""
    for section in sections:
        heading = section.get("TOCHeading", "").lower()
        
        # Check if this section matches
        if all(kw in heading for kw in target_keywords):
            if "Information" in section:
                for info in section["Information"]:
                    if "Value" in info and "StringWithMarkup" in info["Value"]:
                        return info["Value"]["StringWithMarkup"][0]["String"]
        
        # Recurse into subsections
        if "Section" in section:
            result = find_section(section["Section"], target_keywords)
            if result:
                return result
    return None

def get_cid(drug_name):
    """Get PubChem CID from drug name"""
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{requests.utils.quote(drug_name)}/cids/JSON"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data["IdentifierList"]["CID"][0]
    except:
        pass
    return None

def get_drug_data(cid):
    """Fetch full PUG View record and extract DrugBank sections"""
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            sections = data["Record"]["Section"]
            
            return {
                "mechanism_of_action": find_section(sections, ["mechanism", "action"]),
                "description": find_section(sections, ["description"]),
                "indication": find_section(sections, ["indication"]),
                "pharmacodynamics": find_section(sections, ["pharmacodynamics"]),
                "therapeutic_uses": find_section(sections, ["therapeutic", "uses"]),
            }
    except Exception as e:
        print(f"    Error fetching record: {e}")
    return None

print(f"Fetching DrugBank data for {len(drugs)} drugs...\n")
print("=" * 60)

success = 0
failed = []
skipped = []

for i, drug in enumerate(drugs, 1):
    safe_name = drug.lower().replace(" ", "_").replace(";", "_")
    filepath = os.path.join(output_dir, f"{safe_name}.json")
    
    # Skip if exists
    if os.path.exists(filepath):
        print(f"[{i:3d}/{len(drugs)}] ≡ {drug} (exists)")
        success += 1
        continue
    
    print(f"[{i:3d}/{len(drugs)}] → {drug}...", end=" ")
    
    # Get CID
    cid = get_cid(drug)
    if not cid:
        print(f"✗ (no CID)")
        failed.append(drug)
        continue
    
    # Get full record
    drug_data = get_drug_data(cid)
    if not drug_data:
        print(f"✗ (no record)")
        failed.append(drug)
        continue
    
    # Save
    result = {
        "drug_name": drug,
        "cid": cid,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        **drug_data
    }
    
    with open(filepath, 'w') as f:
        json.dump(result, f, indent=2)
    
    moa_status = "✓" if drug_data["mechanism_of_action"] else "○"
    print(f"{moa_status} (CID: {cid})")
    success += 1
    
    time.sleep(0.4)  # Rate limiting

print("\n" + "=" * 60)
print(f"Complete: {success} success, {len(failed)} failed")
if failed:
    print(f"Failed drugs: {', '.join(failed)}")
print(f"Files saved to: {output_dir}")
