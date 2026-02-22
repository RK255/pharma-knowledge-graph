import React, { useState } from 'react';
import './DrugSearch.css';

// Define the Drug interface
export interface Drug {
  id: string;
  name: string;
  set_id?: string;
}

// Define props to match App.tsx usage: onSelect(id, name)
interface DrugSearchProps {
  onSelect: (id: string, name: string) => void;
}

// Use 'export const' for Named Export (fixes the import error)
export const DrugSearch: React.FC<DrugSearchProps> = ({ onSelect }) => {
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<Drug[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setQuery(value);

    if (value.length < 2) {
      setSuggestions([]);
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`/api/search/suggestions?q=${value.toLowerCase()}`);
      const data = await response.json();
      setSuggestions(data.suggestions || []);
    } catch (error) {
      console.error('Search error:', error);
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="drug-search-container">
      <div className="search-input-wrapper">
        <input
          type="text"
          value={query}
          onChange={handleSearch}
          placeholder="Search for a drug (e.g., Lisinopril)..."
          className="search-input"
        />
        {loading && (
          <div className="loading-spinner">
            <div className="spinner"></div>
          </div>
        )}
      </div>

      {suggestions.length > 0 && (
        <ul className="suggestions-list">
          {suggestions.map((drug) => (
            <li
              key={drug.id}
              onClick={() => {
                // Call the prop function exactly as App.tsx expects: (id, name)
                onSelect(drug.id, drug.name);
                setQuery(drug.name);
                setSuggestions([]);
              }}
              className="suggestion-item"
            >
              <div className="suggestion-content">
                <div className="suggestion-name">{drug.name || 'Unknown Drug'}</div>
                <div className="suggestion-meta">
                  {/* Safe access to set_id */}
                  ID: {drug.set_id ? drug.set_id.slice(0, 8) + '...' : 'N/A'}
                </div>
              </div>
              <div className="suggestion-action">View Details →</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
