import os
import csv
import sys

# --- Configuration ---
OUTPUT_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs"

def find_latest_master_file():
    """Finds the most recently created master CID map CSV file."""
    try:
        all_files = os.listdir(OUTPUT_DIR)
        master_files = [os.path.join(OUTPUT_DIR, f) for f in all_files if f.startswith('master_RxNorm') and '_with_cids_' in f and f.endswith('.csv')]
        if not master_files:
            print("❌ No master 'with_cids' file found. Please run the IN_CID_Mapper.py script first.")
            return None
        master_files.sort(key=os.path.getmtime, reverse=True)
        return master_files[0]
    except FileNotFoundError:
        print(f"❌ Error: The directory {OUTPUT_DIR} was not found.")
        return None

def main():
    """Creates a clean list of RxCUI and name from the master file."""
    print("🧹 Creating a clean ingredient list (RxCUI, Name)...")
    
    master_file = find_latest_master_file()
    if not master_file:
        sys.exit(1)

    clean_file_path = os.path.join(OUTPUT_DIR, "clean_layer0_ingredients.csv")
    
    with open(master_file, 'r', encoding='utf-8') as f_in, \
         open(clean_file_path, 'w', newline='', encoding='utf-8') as f_out:
        
        reader = csv.reader(f_in)
        writer = csv.writer(f_out)
        
        # Write header for the new clean file
        writer.writerow(['rxcui', 'name'])
        
        next(reader) # skip header of master file
        for rxcui, name, cid in reader:
            if rxcui and rxcui != 'N/A':
                writer.writerow([rxcui, name])
                
    print(f"✅ Clean list created at: {clean_file_path}")

if __name__ == "__main__":
    main()
