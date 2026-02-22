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

export const GRC20Structure: React.FC<GRC20StructureProps> = ({ drugId, drugName }) => {
  const [data, setData] = useState<GRC20Data | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'entity' | 'relationship' | 'section'>('entity');

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const res = await fetch(`/api/grc20/structure/${drugId}`);
        const json = await res.json();
        setData(json);
      } catch (error) {
        console.error('Failed to fetch GRC-20 structure', error);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [drugId]);

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-lg p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-gray-200 rounded w-1/4"></div>
          <div className="h-4 bg-gray-200 rounded w-1/2"></div>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const getLabelColor = (label: string) => {
    const colors: Record<string, string> = {
      'name': 'bg-blue-100 text-blue-700',
      'set_id': 'bg-purple-100 text-purple-700',
      'description': 'bg-green-100 text-green-700',
      'content': 'bg-yellow-100 text-yellow-700',
      'entity_reference': 'bg-indigo-100 text-indigo-700',
      'provenance_hash': 'bg-red-100 text-red-700',
      'section_type': 'bg-teal-100 text-teal-700',
      'number': 'bg-gray-100 text-gray-700',
    };
    return colors[label] || 'bg-gray-100 text-gray-600';
  };

  const renderTriple = (triple: Triple, index: number) => (
    <div key={index} className="py-3 border-b border-gray-100 last:border-0">
      <div className="flex items-center gap-2 mb-2">
        <span className={`px-2 py-1 rounded text-xs font-medium ${getLabelColor(triple.attribute_label)}`}>
          {triple.attribute_label}
        </span>
        <span className="text-xs text-gray-400 font-mono">
          {triple.attribute_id?.substring(0, 10)}...
        </span>
      </div>
      <div className="bg-gray-50 rounded p-3">
        <code className="text-sm text-gray-800 break-all">
          {triple.value}
          {triple.value_full_length > 150 && (
            <span className="text-gray-400 text-xs ml-2">
              ({triple.value_full_length} chars)
            </span>
          )}
        </code>
      </div>
    </div>
  );

  return (
    <div className="bg-white rounded-lg shadow-lg border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-600 to-indigo-600 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-white">GRC-20 Structure</h3>
            <p className="text-purple-200 text-sm mt-1">
              {data.drug_entity.context.drug_name} — {data.drug_entity.context.manufacturer}
            </p>
          </div>
          <span className="bg-white/20 text-white px-3 py-1 rounded-full text-xs font-medium">
            GRC-20 Compliant
          </span>
        </div>
      </div>

      {/* Stats */}
      <div className="bg-gray-50 px-6 py-4 border-b border-gray-200">
        <div className="grid grid-cols-4 gap-4 text-center">
          <div className="bg-white rounded-lg p-3 shadow-sm">
            <div className="text-2xl font-bold text-purple-600">{data.drug_entity.unique_triple_count}</div>
            <div className="text-xs text-gray-500">Attributes</div>
          </div>
          <div className="bg-white rounded-lg p-3 shadow-sm">
            <div className="text-2xl font-bold text-blue-600">{data.relationship.total_sections}</div>
            <div className="text-xs text-gray-500">Linked Sections</div>
          </div>
          <div className="bg-white rounded-lg p-3 shadow-sm">
            <div className="text-2xl font-bold text-green-600">Base58</div>
            <div className="text-xs text-gray-500">ID Format</div>
          </div>
          <div className="bg-white rounded-lg p-3 shadow-sm">
            <div className="text-2xl font-bold text-orange-600">✓</div>
            <div className="text-xs text-gray-500">Web3 Ready</div>
          </div>
        </div>
      </div>

      {/* Structure Example */}
      <div className="bg-gray-100 px-6 py-4 border-b border-gray-200">
        <div className="font-mono text-sm">
          <div className="text-purple-600 font-semibold mb-2">Triple Structure:</div>
          <div className="bg-white rounded p-3 border">
            <div className="text-gray-600">Entity → [Attribute_ID, Value]</div>
            <div className="mt-2 text-gray-500 text-xs">
              Example: <span className="text-purple-600">{data.drug_entity.id.substring(0, 12)}...</span> → [<span className="text-blue-600">name_attr</span>, <span className="text-green-600">"{data.drug_entity.context.drug_name}"</span>]
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex -mb-px">
          <button
            onClick={() => setActiveTab('entity')}
            className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'entity' ? 'border-purple-500 text-purple-600' : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Drug Entity
          </button>
          <button
            onClick={() => setActiveTab('relationship')}
            className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'relationship' ? 'border-purple-500 text-purple-600' : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Relationships
          </button>
          <button
            onClick={() => setActiveTab('section')}
            className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'section' ? 'border-purple-500 text-purple-600' : 'border-transparent text-gray-500 hover:text-gray-700'
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
            <div className="mb-4 bg-purple-50 rounded-lg p-4 flex justify-between items-center">
              <div>
                <div className="text-xs text-purple-600 uppercase tracking-wider mb-1">Entity ID</div>
                <code className="text-sm text-purple-800 font-bold">{data.drug_entity.id}</code>
              </div>
              <div className="text-right">
                <div className="text-xs text-gray-500">Triples</div>
                <div className="text-lg font-bold text-purple-600">{data.drug_entity.unique_triple_count}</div>
              </div>
            </div>
            <div className="bg-gray-50 rounded-lg p-4 max-h-96 overflow-y-auto">
              {data.drug_entity.triples.map(renderTriple)}
            </div>
          </div>
        )}

        {activeTab === 'relationship' && (
          <div>
            <div className="bg-gray-50 rounded-lg p-6">
              <div className="text-center">
                <div className="mb-2 text-xs text-gray-500 uppercase tracking-wider">Source Entity</div>
                <div className="inline-block bg-blue-100 text-blue-700 px-4 py-2 rounded-lg font-mono text-sm mb-1">
                  {data.drug_entity.id.substring(0, 14)}...
                </div>
                <div className="text-xs text-gray-500 mb-4">{data.drug_entity.context.drug_name}</div>
                
                <div className="my-4">
                  <span className="bg-yellow-100 text-yellow-800 px-4 py-2 rounded-full text-sm font-medium">
                    has_section →
                  </span>
                </div>
                
                <div className="mb-2 text-xs text-gray-500 uppercase tracking-wider">Target Entities ({data.relationship.total_sections} total)</div>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {data.relationship.section_titles.map((section, i) => (
                    <div key={i} className="flex items-center gap-3 bg-green-50 px-4 py-2 rounded-lg text-left">
                      <code className="text-green-700 font-mono text-xs">{section.id.substring(0, 10)}...</code>
                      <span className="text-gray-400">→</span>
                      <span className="text-green-800 text-sm truncate flex-1">{section.title}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'section' && data.sample_section ? (
          <div>
            <div className="mb-4 bg-green-50 rounded-lg p-4 flex justify-between items-center">
              <div>
                <div className="text-xs text-green-600 uppercase tracking-wider mb-1">Section Entity ID</div>
                <code className="text-sm text-green-800 font-bold">{data.sample_section.id}</code>
              </div>
              <div className="text-right">
                <div className="text-xs text-gray-500">Triples</div>
                <div className="text-lg font-bold text-green-600">{data.sample_section.triple_count}</div>
              </div>
            </div>
            <div className="mb-2 text-sm text-gray-600">
              <strong>Section:</strong> {data.sample_section.title}
            </div>
            <div className="bg-gray-50 rounded-lg p-4 max-h-64 overflow-y-auto">
              {data.sample_section.triples.map(renderTriple)}
            </div>
          </div>
        ) : activeTab === 'section' ? (
          <div className="text-center text-gray-500 py-8">No section data available</div>
        ) : null}
      </div>
    </div>
  );
};
