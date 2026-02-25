#!/usr/bin/env python3
"""
Redis-Based Provenance System
"""

import redis
import json
import hashlib
import time
import os
from datetime import datetime
from typing import Optional, Dict, List, Any


class ProvenanceLedger:
    """Redis-based provenance ledger for pharmaceutical knowledge graph."""
    
    def __init__(self, host='localhost', port=6379, db=0):
        self.redis = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        self.ledger_key = "provenance:ledger"
        self.sources_key = "provenance:sources"
        self.stats_key = "provenance:stats"
        self.timeline_key = "provenance:timeline"
        
    def create_entry(self, data_type: str, source: str, source_file: str, **kwargs) -> str:
        metadata = {
            "data_type": data_type,
            "source": source,
            "source_file": source_file,
            "date_accessed": datetime.now().strftime("%Y-%m-%d"),
            **kwargs
        }
        
        entry_json = json.dumps(metadata, sort_keys=True)
        hash_id = hashlib.sha256(entry_json.encode()).hexdigest()[:16]
        
        if self.redis.hexists(self.ledger_key, hash_id):
            return hash_id
            
        self.redis.hset(self.ledger_key, hash_id, entry_json)
        self.redis.sadd(self.sources_key, source)
        self.redis.hincrby(self.stats_key, "total_entries", 1)
        self.redis.hset(self.stats_key, "last_update", time.time())
        self.redis.zadd(self.timeline_key, {hash_id: time.time()})
        
        return hash_id
        
    def get_entry(self, hash_id: str) -> Optional[Dict]:
        entry_json = self.redis.hget(self.ledger_key, hash_id)
        if entry_json:
            return json.loads(entry_json)
        return None
        
    def get_stats(self) -> Dict:
        stats = {
            "total_entries": self.redis.hlen(self.ledger_key),
            "sources": list(self.redis.smembers(self.sources_key)),
            "last_update": self.redis.hget(self.stats_key, "last_update"),
        }
        if stats["last_update"]:
            stats["last_update_human"] = datetime.fromtimestamp(
                float(stats["last_update"])
            ).strftime("%Y-%m-%d %H:%M:%S")
        return stats
        
    def get_recent_entries(self, count: int = 10) -> List[Dict]:
        hash_ids = self.redis.zrange(self.timeline_key, -count, -1, withscores=True)
        entries = []
        for hash_id, timestamp in hash_ids:
            entry = self.get_entry(hash_id)
            if entry:
                entry['hash_id'] = hash_id
                entry['timestamp'] = timestamp
                entries.append(entry)
        return entries
        
    def import_from_json(self, filepath: str) -> int:
        """Import ledger from JSON file."""
        with open(filepath, 'r') as f:
            ledger = json.load(f)
            
        pipe = self.redis.pipeline()
        count = 0
        
        for hash_id, metadata in ledger.items():
            entry_json = json.dumps(metadata, sort_keys=True)
            
            if not self.redis.hexists(self.ledger_key, hash_id):
                pipe.hset(self.ledger_key, hash_id, entry_json)
                pipe.sadd(self.sources_key, metadata.get('source', 'unknown'))
                pipe.zadd(self.timeline_key, {hash_id: time.time()})
                count += 1
                
                if count % 50000 == 0:
                    pipe.execute()
                    pipe = self.redis.pipeline()
                    print(f"  Imported {count:,} entries...")
                    
        if count > 0:
            pipe.hincrby(self.stats_key, "total_entries", count)
            pipe.hset(self.stats_key, "last_update", time.time())
            pipe.execute()
            
        return count
        
    def export_to_json(self, filepath: str) -> int:
        """Export ledger to JSON file."""
        ledger = {}
        for hash_id, entry_json in self.redis.hscan_iter(self.ledger_key, count=1000):
            ledger[hash_id] = json.loads(entry_json)
            
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(ledger, f, indent=2)
            
        return len(ledger)


def migrate_from_json(json_path: str):
    """Migrate existing JSON ledger to Redis."""
    ledger = ProvenanceLedger()
    
    print(f"=== Migrating JSON Ledger to Redis ===")
    print(f"Source: {json_path}")
    
    current = ledger.get_stats()
    print(f"Current Redis entries: {current['total_entries']:,}")
    
    start = time.time()
    count = ledger.import_from_json(json_path)
    elapsed = time.time() - start
    
    print(f"\n✅ Imported {count:,} new entries in {elapsed:.1f} seconds")
    print(f"   Rate: {count/elapsed:,.0f} entries/second")
    
    stats = ledger.get_stats()
    print(f"\nNew Redis total: {stats['total_entries']:,}")
    print(f"Sources: {stats['sources']}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        json_path = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/provenance/Granular_Provenance_Ledger.json"
        if len(sys.argv) > 2:
            json_path = sys.argv[2]
        migrate_from_json(json_path)
        
    elif len(sys.argv) > 1 and sys.argv[1] == "stats":
        ledger = ProvenanceLedger()
        stats = ledger.get_stats()
        print("=== Provenance Stats ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")
            
    elif len(sys.argv) > 1 and sys.argv[1] == "export":
        ledger = ProvenanceLedger()
        output = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/provenance/ledger_export.json"
        count = ledger.export_to_json(output)
        print(f"Exported {count:,} entries to {output}")
        
    else:
        print("Usage:")
        print("  python provenance_redis.py migrate [json_path]")
        print("  python provenance_redis.py stats")
        print("  python provenance_redis.py export")
