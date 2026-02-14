import pandas as pd
from collections import defaultdict

# --- Configuration ---
RXNCONSO_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNCONSO.RRF"

def debug_conso():
    print("--- Debugging RXNCONSO.RRF ---")
    
    line_count = 0
    rxnorm_count = 0
    suppress_flags = defaultdict(int)
    sample_lines = []

    with open(RXNCONSO_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line_count += 1
            parts = line.strip().split('|')
            
            if len(parts) >= 18:
                sab = parts[11]
                if sab == 'RXNORM':
                    rxnorm_count += 1
                    
                    # Count the different suppress flags
                    suppress = parts[17]
                    suppress_flags[suppress] += 1
                        
                    # Save a few sample lines for each flag type
                    if len(sample_lines) < 10: # Save more samples
                         sample_lines.append({
                            'line_num': line_count,
                            'rxcui': parts[0],
                            'name': parts[15],
                            'tty': parts[12],
                            'sab': parts[11],
                            'suppress': parts[17]
                        })

    print(f"Total lines in file: {line_count}")
    print(f"Lines with 'RXNORM' as source (SAB): {rxnorm_count}")
    
    print("\n--- Distribution of SUPPRESS Flags for RXNORM entries ---")
    for flag, count in sorted(suppress_flags.items()):
        print(f"Suppress Flag '{flag}': {count} occurrences")
        
    print("\n--- Sample RXNORM Records ---")
    for i, sample in enumerate(sample_lines):
        print(f"Sample {i+1}:")
        print(f"  RXCUI: {sample['rxcui']}")
        print(f"  Name:  {sample['name']}")
        print(f"  TTY:   {sample['tty']}")
        print(f"  Supp:  {sample['suppress']}")
        print("-" * 20)

if __name__ == "__main__":
    debug_conso()
