// src/components/GRC20Structure.tsx
import React, { useState, useEffect } from 'react';

interface GRC20StructureProps {
  drugId: string;
  drugName: string;
}

interface Triple {
  attribute_id: string;
  attribute_label: string;
  value: string;
  value_full_length: number;
  value_type: string;
}

interface SectionInfo {
  id: string;
  title: string;
}

interface GRC20Data {
  drug_entity: {
    id: string;
    triple_count: number;
    unique_triple_count: number;
    triples: Triple[];
    context: {
      drug_name: string;
      manufacturer: string;
      set_id: string;
    };
  };
  relationship: {
    type: string;
    total_sections: number;
    sample_section_ids: string[];
    section_titles: SectionInfo[];
  };
  sample_section: {
    id: string;
    title: string;
    triple_count: number;
    triples: Triple[];
  } | null;
}

// Use local API in development
const API_BASE = window.location.hostname === 'localhost' 
  ? 'http://localhost:8000' 
  : 'https://api.pharma.bowsernodes.dynns.com';

export const GRC20Structure: React.FC<GRC20StructureProps> = ({ drugId, drugName }) => {
  const [data, setData] = useState<GRC20Data | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'entity' | 'relationship' | 'section'>('entity');

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/api/grc20/structure/${drugId}`);
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }
        const json = await res.json();
        setData(json);
      } catch (error) {
        console.error('Failed to fetch GRC-20 structure', error);
        setError(error instanceof Error ? error.message : 'Failed to load GRC-20 structure');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [drugId]);

  if (loading) {
    return (
      <div className="bg-[#1a1a2e] rounded-lg shadow-lg p-6 border border-[#2d2d4a]">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-[#252542] rounded w-1/4"></div>
          <div className="h-4 bg-[#252542] rounded w-1/2"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-[#1a1a2e] rounded-lg shadow-lg p-6 border border-[#ef4444]/50">
        <div className="text-[#ef4444] text-sm">Error loading GRC-20: {error}</div>
      </div>
    );
  }

  if (!data) return null;

  const getLabelColor = (label: string) => {
    const colors: Record<string, string> = {
      'name': 'bg-[#3b82f6]/20 text-[#3b82f6]',
      'set_id': 'bg-[#8b5cf6]/20 text-[#8b5cf6]',
      'description': 'bg-[#22c55e]/20 text-[#22c55e]',
      'content': 'bg-[#eab308]/20 text-[#eab308]',
      'entity_reference': 'bg-[#6366f1]/20 text-[#6366f1]',
      'provenance_hash': 'bg-[#ef4444]/20 text-[#ef4444]',
      'section_type': 'bg-[#14b8a6]/20 text-[#14b8a6]',
      'number': 'bg-[#6b7280]/20 text-[#9ca3af]',
    };
    return colors[label] || 'bg-[#374151]/20 text-[#9ca3af]';
  };

  const renderTriple = (triple: Triple, index: number) => (
    <div key={index} className="py-3 border-b border-[#2d2d4a] last:border-0">
      <div className="flex items-center gap-2 mb-2">
        <span className={`px-2 py-1 rounded text-xs font-medium ${getLabelColor(triple.attribute_label)}`}>
          {triple.attribute_label}
        </span>
        <span className="text-xs text-[#6b6b80] font-mono">
          {triple.attribute_id?.substring(0, 10)}...
        </span>
      </div>
      <div className="bg-[#0f0f23] rounded p-3 border border-[#2d2d4a]">
        <code className="text-sm text-[#e4e4f1] break-all">
          {triple.value}
          {triple.value_full_length > 150 && (
            <span className="text-[#6b6b80] text-xs ml-2">
              ({triple.value_full_length} chars)
            </span>
          )}
        </code>
      </div>
    </div>
  );

  return (
    <div className="bg-[#1a1a2e] rounded-lg shadow-lg border border-[#2d2d4a] overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-[#8b5cf6] to-[#6366f1] px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-white">GRC-20 Structure</h3>
            <p className="text-[#c4b5fd] text-sm mt-1">
              {data.drug_entity.context.drug_name} — {data.drug_entity.context.manufacturer}
            </p>
          </div>
          <span className="bg-white/20 text-white px-3 py-1 rounded-full text-xs font-medium">
            GRC-20 Compliant
          </span>
        </div>
      </div>

      {/* Stats */}
      <div className="bg-[#252542] px-6 py-4 border-b border-[#2d2d4a]">
        <div className="grid grid-cols-4 gap-4 text-center">
          <div className="bg-[#1a1a2e] rounded-lg p-3 border border-[#2d2d4a]">
            <div className="text-2xl font-bold text-[#8b5cf6]">{data.drug_entity.unique_triple_count}</div>
            <div className="text-xs text-[#6b6b80]">Attributes</div>
          </div>
          <div className="bg-[#1a1a2e] rounded-lg p-3 border border-[#2d2d4a]">
            <div className="text-2xl font-bold text-[#3b82f6]">{data.relationship.total_sections}</div>
            <div className="text-xs text-[#6b6b80]">Linked Sections</div>
          </div>
          <div className="bg-[#1a1a2e] rounded-lg p-3 border border-[#2d2d4a]">
            <div className="text-2xl font-bold text-[#22c55e]">Base58</div>
            <div className="text-xs text-[#6b6b80]">ID Format</div>
          </div>
          <div className="bg-[#1a1a2e] rounded-lg p-3 border border-[#2d2d4a]">
            <div className="text-2xl font-bold text-[#f97316]">✓</div>
            <div className="text-xs text-[#6b6b80]">Web3 Ready</div>
          </div>
        </div>
      </div>

      {/* Structure Example */}
      <div className="bg-[#0f0f23] px-6 py-4 border-b border-[#2d2d4a]">
        <div className="font-mono text-sm">
          <div className="text-[#8b5cf6] font-semibold mb-2">Triple Structure:</div>
          <div className="bg-[#1a1a2e] rounded p-3 border border-[#2d2d4a]">
            <div className="text-[#a0a0b8]">Entity → [Attribute_ID, Value]</div>
            <div className="mt-2 text-[#6b6b80] text-xs">
              Example: <span className="text-[#8b5cf6]">{data.drug_entity.id.substring(0, 12)}...</span> → [<span className="text-[#3b82f6]">name_attr</span>, <span className="text-[#22c55e]">"{data.drug_entity.context.drug_name}"</span>]
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-[#2d2d4a]">
        <nav className="flex -mb-px">
          <button
            onClick={() => setActiveTab('entity')}
            className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'entity' ? 'border-[#8b5cf6] text-[#8b5cf6]' : 'border-transparent text-[#6b6b80] hover:text-[#a0a0b8]'
            }`}
          >
            Drug Entity
          </button>
          <button
            onClick={() => setActiveTab('relationship')}
            className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'relationship' ? 'border-[#8b5cf6] text-[#8b5cf6]' : 'border-transparent text-[#6b6b80] hover:text-[#a0a0b8]'
            }`}
          >
            Relationships
          </button>
          <button
            onClick={() => setActiveTab('section')}
            className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'section' ? 'border-[#8b5cf6] text-[#8b5cf6]' : 'border-transparent text-[#6b6b80] hover:text-[#a0a0b8]'
            }`}
          >
            Sample Section
          </button>
        </nav>
      </div>

      {/* Tab Content */}
      <div className="p-6">
        {activeTab === 'entity' && (
          <div>
            <div className="mb-4 bg-[#252542] rounded-lg p-4 flex justify-between items-center border border-[#2d2d4a]">
              <div>
                <div className="text-xs text-[#8b5cf6] uppercase tracking-wider mb-1">Entity ID</div>
                <code className="text-sm text-[#e4e4f1] font-bold">{data.drug_entity.id}</code>
              </div>
              <div className="text-right">
                <div className="text-xs text-[#6b6b80]">Triples</div>
                <div className="text-lg font-bold text-[#8b5cf6]">{data.drug_entity.unique_triple_count}</div>
              </div>
            </div>
            <div className="bg-[#0f0f23] rounded-lg p-4 max-h-96 overflow-y-auto border border-[#2d2d4a]">
              {data.drug_entity.triples.map(renderTriple)}
            </div>
          </div>
        )}

        {activeTab === 'relationship' && (
          <div>
            <div className="bg-[#0f0f23] rounded-lg p-6 border border-[#2d2d4a]">
              <div className="text-center">
                <div className="mb-2 text-xs text-[#6b6b80] uppercase tracking-wider">Source Entity</div>
                <div className="inline-block bg-[#3b82f6]/20 text-[#3b82f6] px-4 py-2 rounded-lg font-mono text-sm mb-1">
                  {data.drug_entity.id.substring(0, 14)}...
                </div>
                <div className="text-xs text-[#6b6b80] mb-4">{data.drug_entity.context.drug_name}</div>
                
                <div className="my-4">
                  <span className="bg-[#eab308]/20 text-[#eab308] px-4 py-2 rounded-full text-sm font-medium">
                    has_section →
                  </span>
                </div>
                
                <div className="mb-2 text-xs text-[#6b6b80] uppercase tracking-wider">Target Entities ({data.relationship.total_sections} total)</div>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {data.relationship.section_titles.map((section, i) => (
                    <div key={i} className="flex items-center gap-3 bg-[#22c55e]/10 px-4 py-2 rounded-lg text-left border border-[#22c55e]/20">
                      <code className="text-[#22c55e] font-mono text-xs">{section.id.substring(0, 10)}...</code>
                      <span className="text-[#6b6b80]">→</span>
                      <span className="text-[#a0a0b8] text-sm truncate flex-1">{section.title}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'section' && data.sample_section ? (
          <div>
            <div className="mb-4 bg-[#22c55e]/10 rounded-lg p-4 flex justify-between items-center border border-[#22c55e]/20">
              <div>
                <div className="text-xs text-[#22c55e] uppercase tracking-wider mb-1">Section Entity ID</div>
                <code className="text-sm text-[#e4e4f1] font-bold">{data.sample_section.id}</code>
              </div>
              <div className="text-right">
                <div className="text-xs text-[#6b6b80]">Triples</div>
                <div className="text-lg font-bold text-[#22c55e]">{data.sample_section.triple_count}</div>
              </div>
            </div>
            <div className="mb-2 text-sm text-[#a0a0b8]">
              <strong>Section:</strong> {data.sample_section.title}
            </div>
            <div className="bg-[#0f0f23] rounded-lg p-4 max-h-64 overflow-y-auto border border-[#2d2d4a]">
              {data.sample_section.triples.map(renderTriple)}
            </div>
          </div>
        ) : activeTab === 'section' ? (
          <div className="text-center text-[#6b6b80] py-8">No section data available</div>
        ) : null}
      </div>
    </div>
  );
};
