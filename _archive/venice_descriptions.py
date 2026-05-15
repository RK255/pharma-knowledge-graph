import os
import json
import requests
import time
from dotenv import load_dotenv

# Load .env from pipeline directory
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

VENICE_API_KEY = os.getenv("VENICE_API_KEY")
VENICE_MODEL = "venice-uncensored"

master_file = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/master_drug_descriptions.json"
output_file = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/drug_summaries.json"

# Load master data
with open(master_file, 'r') as f:
    master_data = json.load(f)

def generate_summary(drug_name: str, mechanism: str, description: str, indication: str = None) -> str:
    """Generate layperson-friendly summary via Venice AI"""
    
    # Build context from available data
    context_parts = []
    if mechanism:
        # Truncate very long mechanisms
        mech_text = mechanism[:2000] if len(mechanism) > 2000 else mechanism
        context_parts.append(f"Mechanism of Action: {mech_text}")
    if description:
        desc_text = description[:1000] if len(description) > 1000 else description
        context_parts.append(f"Description: {desc_text}")
    if indication:
        ind_text = indication[:1000] if len(indication) > 1000 else indication
        context_parts.append(f"Indication: {ind_text}")
    
    context = "\n\n".join(context_parts)
    
    prompt = f"""You are writing patient-friendly drug descriptions for a consumer health database. The drug name will be displayed separately above the description, so do NOT include it.

Write a concise 1-3 sentence summary in plain language that everyday people can understand.

RULES:
1. NEVER mention or repeat the drug name
2. Start directly with what the drug IS (drug class/type)
3. Explain how it works in simple terms
4. Mention what conditions it treats
5. Use "It" instead of the drug name

Drug: {drug_name}

Clinical Information:
{context}

Write the summary:"""

    try:
        response = requests.post(
            "https://api.venice.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {VENICE_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": VENICE_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 500
            },
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        else:
            return f"ERROR: HTTP {response.status_code}"
            
    except Exception as e:
        return f"ERROR: {str(e)}"

def process_combo_drug(drug_name: str, ingredients: list) -> str:
    """Generate separate paragraphs for each ingredient in a combo drug"""
    
    paragraphs = []
    
    for ingredient in ingredients:
        safe_name = ingredient.lower().replace(" ", "_")
        filepath = f"/mnt/fast_raid/server_projects/Geo/graph_workshop/data/drug_descriptions/{safe_name}.json"
        
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                ing_data = json.load(f)
            
            summary = generate_summary(
                drug_name=ingredient,
                mechanism=ing_data.get("mechanism_of_action"),
                description=ing_data.get("description"),
                indication=ing_data.get("indication")
            )
            
            paragraphs.append(f"{ingredient}: {summary}")
            time.sleep(0.5)  # Rate limiting between ingredients
        else:
            paragraphs.append(f"{ingredient}: [No data available]")
    
    return "\n\n".join(paragraphs)

def main():
    print(f"Processing {len(master_data)} drugs...")
    print("=" * 60)
    
    results = {}
    success_count = 0
    error_count = 0
    
    for i, (drug_name, drug_data) in enumerate(master_data.items(), 1):
        print(f"[{i:3d}/{len(master_data)}] {drug_name}...", end=" ", flush=True)
        
        # Check if combo drug
        if drug_data.get("is_combo"):
            ingredients = [ing["name"] for ing in drug_data.get("ingredients", [])]
            summary = process_combo_drug(drug_name, ingredients)
            results[drug_name] = {
                "is_combo": True,
                "ingredients": ingredients,
                "summary": summary
            }
            print(f"✓ (combo: {len(ingredients)} ingredients)")
            success_count += 1
        else:
            # Single drug
            summary = generate_summary(
                drug_name=drug_name,
                mechanism=drug_data.get("mechanism_of_action"),
                description=drug_data.get("description"),
                indication=drug_data.get("indication")
            )
            
            results[drug_name] = {
                "is_combo": False,
                "cid": drug_data.get("cid"),
                "summary": summary
            }
            
            if summary.startswith("ERROR"):
                print(f"✗ {summary}")
                error_count += 1
            else:
                print("✓")
                success_count += 1
        
        time.sleep(0.4)  # Rate limiting
    
    # Save results
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\n" + "=" * 60)
    print(f"Complete: {success_count} success, {error_count} errors")
    print(f"Saved to: {output_file}")

if __name__ == "__main__":
    main()
