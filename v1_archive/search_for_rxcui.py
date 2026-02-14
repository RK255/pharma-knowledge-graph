import sys

# --- Configuration ---
# We'll search for the first RxCUI from your previous output
TARGET_RXCUI = "4574424"
RXNCONSO_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNCONSO.RRF"

def search_for_rxcui():
    print(f"--- Searching for RxCUI '{TARGET_RXCUI}' in RXNCONSO.RRF ---")

    found_lines = []
    
    try:
        with open(RXNCONSO_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 18 and parts[0] == TARGET_RXCUI:
                    found_lines.append(parts)
    except FileNotFoundError:
        print(f"❌ ERROR: Could not find the file at {RXNCONSO_PATH}")
        return

    print(f"\n✅ Found {len(found_lines)} lines for RxCUI '{TARGET_RXCUI}'.")
    
    if not found_lines:
        print("This RxCUI does not exist in the RXNCONSO.RRF file.")
    else:
        print("\n--- Details for Found Lines ---")
        for i, parts in enumerate(found_lines):
            print(f"\nLine #{i+1}:")
            print(f"  Full Raw Line: {'|'.join(parts)}")
            print(f"  RxCui:      '{parts[0]}'")
            print(f"  Name (STR): '{parts[14]}'")
            print(f"  TTY:        '{parts[12]}'")
            print(f"  SAB (Source):'{parts[11]}'")
            print(f"  Suppress:   '{parts[17]}'")

if __name__ == "__main__":
    search_for_rxcui()
