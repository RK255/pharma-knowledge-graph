// src/components/GRC20Structure.tsx
import React, { useState, useEffect } from 'react';

interface GRC20StructureProps {
  drugId: string;
  drugName: string;
}

interface Triple {
  attribute: string;
  value: string;
  value_type: string;
}

interface GRC20Data {
  drug_entity: {
    id: string;
    id_format: string;
    triple_count: number;
    triples: Triple[];
  };
  relationship: {
    type: string;
    format: string;
    total_sections: number;
    sample_section_ids: string[];
  };
  sample_section: {
    id: string;
    triple_count: number;
    triples: Triple[];
  } | null;
  grc20_compliance: {
    entity_id_format: string;
    triple_structure: string;
    value_types: string[];
    relationship_model: string;
    provenance: string;
  };
}

export const GRC20Structure: React.FC<GRC20StructureProps> = ({ drugId, drugName }) => {
  const [data, setData] = useState<GRC20Data | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'entity' | 'relationship' | 'section'>('entity');

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const res = await fetch(\`/api/grc20/structure/\${drugId}\`);
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
          <div className="h-4 bg-gray-200 rounded w-3/4"></div>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const renderTriple = (triple: Triple, index: number) => (
    <div key={index} className="flex items-start space-x-3 py-2 border-b border-gray-100 last:border-0">
      <span className="bg-purple-100 text-purple-700 px-2 py-1 rounded text-xs font-mono min-w-[100px] truncate">
        {triple.attribute?.substring(0, 12)}...
      </span>
      <span className="text-gray-400">→</span>
      <span className={\`flex-1 text-sm font-mono \${
        triple.value_type === 'entity_reference' ? 'text-blue-600' : 'text-gray-700'
      }\`}>
        {triple.value}
      </span>
      <span className="text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded">
        {triple.value_type}
      </span>
    </div>
  );

  return (
    <div className="bg-white rounded-lg shadow-lg border border-gray-200 overflow-hidden">
      <div className="bg-gradient-to-r from-purple-600 to-indigo-600 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-white">GRC-20 Structure</h3>
            <p className="text-purple-200 text-sm mt-1">Web3 Knowledge Graph Format</p>
          </div>
          <div className="flex items-center space-x-2">
            <span className="bg-white/20 text-white px-3 py-1 rounded-full text-xs font-medium">
              ✓ Compliant
            </span>
          </div>
        </div>
      </div>

      <div className="bg-gray-50 px-6 py-3 border-b border-gray-200">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wider">ID Format</div>
            <div className="text-sm font-semibold text-gray-800 mt-1">{data.grc20_compliance.entity_id_format}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wider">Structure</div>
            <div className="text-sm font-semibold text-gray-800 mt-1">Entity → [Attr, Value]</div>
          </div>
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wider">Drug Triples</div>
            <div className="text-sm font-semibold text-purple-600 mt-1">{data.drug_entity.triple_count}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wider">Linked Sections</div>
            <div className="text-sm font-semibold text-purple-600 mt-1">{data.relationship.total_sections}</div>
          </div>
        </div>
      </div>

      <div className="border-b border-gray-200">
        <nav className="flex -mb-px">
          <button
            onClick={() => setActiveTab('entity')}
            className={\`px-6 py-3 text-sm font-medium border-b-2 transition-colors \${
              activeTab === 'entity'
                ? 'border-purple-500 text-purple-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }\`}
          >
            Drug Entity
          </button>
          <button
            onClick={() => setActiveTab('relationship')}
            className={\`px-6 py-3 text-sm font-medium border-b-2 transition-colors \${
              activeTab === 'relationship'
                ? 'border-purple-500 text-purple-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }\`}
          >
            Relationships
          </button>
          <button
            onClick={() => setActiveTab('section')}
            className={\`px-6 py-3 text-sm font-medium border-b-2 transition-colors \${
              activeTab === 'section'
                ? 'border-purple-500 text-purple-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }\`}
          >
            Sample Section
          </button>
        </nav>
      </div>

      <div className="p-6">
        {activeTab === 'entity' && (
          <div>
            <div className="mb-4">
              <code className="bg-gray-100 px-3 py-2 rounded text-sm block">
                Entity ID: <span className="text-purple-600 font-bold">{data.drug_entity.id}</span>
              </code>
            </div>
            <h4 className="font-semibold text-gray-800 mb-3">Triples ({data.drug_entity.triple_count})</h4>
            <div className="bg-gray-50 rounded-lg p-4 max-h-64 overflow-y-auto">
              {data.drug_entity.triples.map(renderTriple)}
            </div>
          </div>
        )}

        {activeTab === 'relationship' && (
          <div>
            <div className="bg-gray-50 rounded-lg p-4 mb-4">
              <div className="text-center">
                <div className="inline-block bg-blue-100 text-blue-700 px-4 py-2 rounded-lg font-mono text-sm">
                  {data.drug_entity.id.substring(0, 10)}...
                </div>
                <div className="my-3">
                  <span className="bg-yellow-100 text-yellow-700 px-3 py-1 rounded text-sm font-medium">
                    --[has_section]--&gt;
                  </span>
                </div>
                <div className="space-y-2">
                  {data.relationship.sample_section_ids.map((sid, i) => (
                    <div key={i} className="bg-green-100 text-green-700 px-4 py-2 rounded-lg font-mono text-sm">
                      {sid.substring(0, 10)}...
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <p className="text-sm text-gray-600">
              <strong>Relationship Model:</strong> {data.grc20_compliance.relationship_model}
            </p>
            <p className="text-sm text-gray-600 mt-2">
              <strong>Total Sections:</strong> {data.relationship.total_sections} section entities linked to this drug
            </p>
          </div>
        )}

        {activeTab === 'section' && data.sample_section ? (
          <div>
            <div className="mb-4">
              <code className="bg-gray-100 px-3 py-2 rounded text-sm block">
                Section ID: <span className="text-green-600 font-bold">{data.sample_section.id}</span>
              </code>
            </div>
            <h4 className="font-semibold text-gray-800 mb-3">Triples ({data.sample_section.triple_count})</h4>
            <div className="bg-gray-50 rounded-lg p-4 max-h-64 overflow-y-auto">
              {data.sample_section.triples.map(renderTriple)}
            </div>
          </div>
        ) : activeTab === 'section' ? (
          <div className="text-center text-gray-500 py-8">
            No section data available
          </div>
        ) : null}
      </div>

      <div className="bg-gray-50 px-6 py-3 border-t border-gray-200">
        <p className="text-xs text-gray-500">
          {data.grc20_compliance.provenance}
        </p>
      </div>
    </div>
  );
};
