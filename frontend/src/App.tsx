import React, { useState } from 'react';
import { DrugSearch } from './components/DrugSearch';
import { DrugDetail } from './components/DrugDetail';

function App() {
  const [selectedDrugId, setSelectedDrugId] = useState<string | null>(null);
  const [selectedDrugName, setSelectedDrugName] = useState<string>("");

  const handleDrugSelect = (entityId: string, name: string) => {
    setSelectedDrugId(entityId);
    setSelectedDrugName(name);
  };

  const handleBack = () => {
    setSelectedDrugId(null);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              {selectedDrugId && (
                <button 
                  onClick={handleBack}
                  className="text-blue-600 hover:text-blue-800 flex items-center"
                >
                  <svg className="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                  </svg>
                  Back to Search
                </button>
              )}
              <h1 className="text-2xl font-bold text-gray-900">
                Pharma Knowledge Graph
              </h1>
            </div>
            <div className="flex items-center space-x-4">
              <span className="text-sm text-gray-500">
                FDA SPL Data with Provenance
              </span>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8">
        {!selectedDrugId ? (
          <div className="flex flex-col items-center justify-center py-12">
            <h2 className="text-4xl font-bold text-gray-800 mb-4 text-center">
              Search FDA Drug Labels
            </h2>
            <p className="text-gray-600 mb-8 text-center max-w-2xl">
              Access comprehensive pharmaceutical data with full provenance tracking. 
              Search for any FDA approved drug to view detailed prescribing information.
            </p>
            <div className="w-full max-w-2xl">
              <DrugSearch onSelect={(id, name) => handleDrugSelect(id, name)} />
            </div>
          </div>
        ) : (
          <DrugDetail drugId={selectedDrugId} drugName={selectedDrugName} />
        )}
      </main>
    </div>
  );
}

export default App;
