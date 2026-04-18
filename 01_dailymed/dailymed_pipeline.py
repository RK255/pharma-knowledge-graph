#!/usr/bin/env python3
"""
DailyMed Pipeline - Main Entry Point

Orchestrates the full pipeline:
1. ftp_ripper     - Download XMLs from FDA FTP
2. parser         - Parse XML → documents
3. grc20_convert  - Documents → GRC-20 entities
4. validate       - Validate output

Usage:
    python dailymed_pipeline.py --xml-dir /path/to/xml --limit 100
    python dailymed_pipeline.py --skip-download --xml-dir /path/to/xml
    python dailymed_pipeline.py --step parse --xml-dir /path/to/xml
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from progress import Progress

# Output directory
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent.parent / "data" / "grc20_v2"


def run_ftp_ripper(output_dir: Path, limit: int = None):
    """Download DailyMed XMLs from FDA FTP."""
    print("\n" + "=" * 80)
    print("STEP 1: FTP DOWNLOAD")
    print("=" * 80)
    
    try:
        from .ftp_ripper import download_dailymed
        xml_dir = output_dir / "dailymed_xml"
        xml_dir.mkdir(parents=True, exist_ok=True)
        download_dailymed(str(xml_dir), limit=limit)
        return xml_dir
    except ImportError:
        print("ERROR: ftp_ripper.py not found or missing download_dailymed function")
        return None
    except Exception as e:
        print(f"ERROR: FTP download failed: {e}")
        return None


def run_parser(xml_dir: Path, output_dir: Path, limit: int = None, progress=None) -> bool:
    """Parse XML files to documents."""
    print("\n" + "=" * 80)
    print("STEP 2: PARSE XML → DOCUMENTS")
    print("=" * 80)
    
    if progress:
        progress.report(0.1, "Parsing XML files...")
    
    try:
        from spl_parser import process_xml_files
        output_dir.mkdir(parents=True, exist_ok=True)
        result = process_xml_files(str(xml_dir), limit=limit, output_dir=str(output_dir), progress=progress)
        
        # Save documents
        docs_file = output_dir / "dailymed_documents.json"
        import json
        with open(docs_file, 'w') as f:
            json.dump(result['documents'], f, indent=2)
        
        print(f"  Parsed {len(result['documents'])} documents → {docs_file}")
        return True
    except ImportError:
        print("ERROR: parser.py not found")
        return False
    except Exception as e:
        print(f"ERROR: Parsing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_grc20_convert(output_dir: Path, progress=None) -> bool:
    """Convert documents to GRC-20 entities."""
    print("\n" + "=" * 80)
    print("STEP 3: CONVERT → GRC-20")
    print("=" * 80)
    
    if progress:
        progress.report(0.5, "Converting to GRC-20...")
    
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from grc20_convert import convert_dataset_to_grc20
        input_file = output_dir / "dailymed_documents.json"
        output_file = output_dir / "dailymed_entities.json"
        
        stats = convert_dataset_to_grc20(str(input_file), str(output_file), progress=progress)
        # Validation scores not available in current implementation
        # The function returns (entity_count, relation_count)
        return True
    except ImportError:
        print("ERROR: grc20_convert.py not found")
        return False
    except Exception as e:
        print(f"ERROR: GRC-20 conversion failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_validate(output_dir: Path) -> bool:
    """Validate GRC-20 output."""
    print("\n" + "=" * 80)
    print("STEP 4: VALIDATE")
    print("=" * 80)
    
    try:
        from validate import validate_grc20
        entities_file = output_dir / "dailymed_entities.jsonl"
        
        if not entities_file.exists():
            print(f"ERROR: Entities file not found: {entities_file}")
            return False
        
        result = validate_grc20(str(entities_file))
        print(f"  Validation: {'PASSED' if result else 'FAILED'}")
        return result
    except ImportError:
        print("WARNING: validate.py not found, skipping validation")
        return True
    except Exception as e:
        print(f"ERROR: Validation failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='DailyMed Pipeline - Download, Parse, Convert, Validate',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline with limit
  python dailymed_pipeline.py --xml-dir ./xml --limit 100

  # Skip download, parse existing XMLs
  python dailymed_pipeline.py --skip-download --xml-dir ./xml

  # Run specific step only
  python dailymed_pipeline.py --step convert --xml-dir ./xml
        """
    )
    
    parser.add_argument('--xml-dir', help='Directory containing XML files (or where to download)')
    parser.add_argument('--output-dir', default=None, help='Output directory (default: data/grc20_v2)')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of files to process')
    parser.add_argument('--skip-download', action='store_true', help='Skip FTP download step')
    parser.add_argument('--step', choices=['download', 'parse', 'convert', 'validate'], 
                        help='Run only this step')
    parser.add_argument('--no-validate', action='store_true', help='Skip validation step')
    
    args = parser.parse_args()
    
    # Set output directory
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize progress reporter
    progress = Progress(step_num=1, step_name="DailyMed")
    
    print("=" * 80)
    print("DAILYMED PIPELINE")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Output: {output_dir}")
    
    # Determine XML directory
    xml_dir = Path(args.xml_dir) if args.xml_dir else output_dir / "dailymed_xml"
    
    # Run steps
    success = True
    
    if args.step == 'download':
        success = run_ftp_ripper(output_dir, args.limit) is not None
    elif args.step == 'parse':
        success = run_parser(xml_dir, output_dir, args.limit, progress)
    elif args.step == 'convert':
        success = run_grc20_convert(output_dir, progress)
    elif args.step == 'validate':
        success = run_validate(output_dir)
    else:
        # Full pipeline
        if not args.skip_download:
            xml_dir = run_ftp_ripper(output_dir, args.limit)
            if xml_dir is None:
                success = False
        
        if success:
            success = run_parser(xml_dir, output_dir, args.limit, progress)
        
        if success:
            success = run_grc20_convert(output_dir, progress)
        
        if success and not args.no_validate:
            success = run_validate(output_dir)
    
    print("\n" + "=" * 80)
    if progress:
        progress.complete("Pipeline complete")
    print("PIPELINE COMPLETE")
    print("=" * 80)
    print(f"Status: {'SUCCESS' if success else 'FAILED'}")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
