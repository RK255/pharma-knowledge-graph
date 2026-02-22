// src/components/DrugSearch.tsx
import React, { useState, useEffect } from 'react';

interface DrugSearchProps {
  onDrugSelect: (drugId: string, drugName: string) => void;
}

interface Suggestion {
  name: string;
  variant_count: number;
  top_manufacturer: string;
}

export const DrugSearch: React.FC<DrugSearchProps> = ({ onDrugSelect }) => {
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedDrug, setSelectedDrug] = useState<string | null>(null);
  const [variants, setVariants] = useState<any[]>([]);
  const [showVariantSelector, setShowVariantSelector] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchSuggestions = async () => {
      if (query.length >= 2) {
        try {
          const res = await fetch(`/api/search/suggestions?q=${encodeURIComponent(query)}`);
          const data = await res.json();
          setSuggestions(data.suggestions || []);
          setShowDropdown(true);
        } catch (error) {
          console.error('Failed to fetch suggestions', error);
        }
      } else {
        setSuggestions([]);
        setShowDropdown(false);
      }
    };
    
    const debounce = setTimeout(fetchSuggestions, 300);
    return () => clearTimeout(debounce);
  }, [query]);

  const selectDrug = async (drugName: string) => {
    setSelectedDrug(drugName);
    setQuery(drugName);
    setShowDropdown(false);
    setLoading(true);
    
    try {
      const res = await fetch(`/api/drug-variants/${encodeURIComponent(drugName)}`);
      const data = await res.json();
      
      if (data.variants.length === 1) {
        // Only one variant, go directly to details
        onDrugSelect(data.variants[0].id, drugName);
      } else {
        // Multiple variants, show selector
        setVariants(data.variants);
        setShowVariantSelector(true);
      }
    } catch (error) {
      console.error('Failed to fetch variants', error);
    } finally {
      setLoading(false);
    }
  };

  const selectVariant = (variant: any) => {
    setShowVariantSelector(false);
    onDrugSelect(variant.id, selectedDrug || variant.name);
  };

  return (
    <div className="relative w-full max-w-2xl mx-auto">
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSelectedDrug(null);
            setShowVariantSelector(false);
          }}
          placeholder="Search for a drug (e.g., Lisinopril, Metformin, Aspirin)..."
          className="w-full px-6 py-4 text-lg border-2 border-gray-300 rounded-xl shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none transition-all"
        />
        {loading && (
          <div className="absolute right-4 top-1/2 -translate-y-1/2">
            <svg className="animate-spin h-6 w-6 text-blue-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          </div>
        )}
      </div>

      {/* Search Suggestions Dropdown */}
      {showDropdown && suggestions.length > 0 && (
        <div className="absolute z-10 w-full mt-2 bg-white border border-gray-200 rounded-xl shadow-lg max-h-96 overflow-y-auto">
          {suggestions.map((s, idx) => (
            <div
              key={idx}
              onClick={() => selectDrug(s.name)}
              className="px-6 py-4 hover:bg-blue-50 cursor-pointer border-b border-gray-100 last:border-0 transition-colors"
            >
              <div className="flex justify-between items-center">
                <div>
                  <span className="font-semibold text-gray-900">{s.name}</span>
                  {s.variant_count > 1 && (
                    <span className="ml-2 px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">
                      {s.variant_count} manufacturers
                    </span>
                  )}
                </div>
                <span className="text-sm text-gray-500">{s.top_manufacturer}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Variant Selector Modal */}
      {showVariantSelector && variants.length > 0 && (
        <div className="absolute z-20 w-full mt-2 bg-white border border-gray-200 rounded-xl shadow-lg max-h-[500px] overflow-y-auto">
          <div className="sticky top-0 bg-gray-50 px-6 py-4 border-b border-gray-200">
            <h3 className="font-bold text-lg text-gray-900">
              {selectedDrug} - Select Manufacturer
            </h3>
            <p className="text-sm text-gray-500">{variants.length} package inserts available</p>
          </div>
          <div className="divide-y divide-gray-100">
            {variants.map((v, idx) => (
              <div
                key={v.id}
                onClick={() => selectVariant(v)}
                className="px-6 py-4 hover:bg-blue-50 cursor-pointer transition-colors"
              >
                <div className="flex justify-between items-start">
                  <div>
                    <div className="font-semibold text-gray-900">{v.manufacturer}</div>
                    <div className="text-xs text-gray-500 mt-1 font-mono">
                      Set ID: {v.set_id?.substring(0, 18)}...
                    </div>
                    {v.nda && v.nda !== 'N/A' && (
                      <div className="text-xs text-gray-500 mt-1">
                        {v.nda}
                      </div>
                    )}
                  </div>
                  <div className="text-right">
                    <span className="px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full">
                      {v.section_count || 0} sections
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Click outside to close */}
      {(showDropdown || showVariantSelector) && (
        <div 
          className="fixed inset-0 z-0" 
          onClick={() => {
            setShowDropdown(false);
            setShowVariantSelector(false);
          }}
        />
      )}
    </div>
  );
};
