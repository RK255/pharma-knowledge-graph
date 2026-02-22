// src/App.tsx
import React, { useState } from 'react';
import { DrugSearch } from './components/DrugSearch';
import { DrugDetail } from './components/DrugDetail';
import { HomePage } from './components/HomePage';

function App() {
  const [selectedDrugId, setSelectedDrugId] = useState<string | null>(null);
  const [selectedDrugName, setSelectedDrugName] = useState<string>('');

  const handleDrugSelect = (drugId: string, drugName: string) => {
    setSelectedDrugId(drugId);
    setSelectedDrugName(drugName);
  };

  const handleBack = () => {
    setSelectedDrugId(null);
    setSelectedDrugName('');
  };

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-6 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Pharmaceutical Knowledge Graph</h1>
              <p className="text-sm text-gray-500 mt-1">FDA Drug Package Inserts with Full Provenance</p>
            </div>
            {selectedDrugId && (
              <button
                onClick={handleBack}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
              >
                ← Back to Search
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
        {!selectedDrugId ? (
          <HomePage>
            <DrugSearch onDrugSelect={handleDrugSelect} />
          </HomePage>
        ) : (
          <DrugDetail drugId={selectedDrugId} drugName={selectedDrugName} />
        )}
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 mt-auto">
        <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <p className="text-center text-sm text-gray-500">
            Data sourced from FDA Structured Product Labeling (SPL) • Built with Redis + FastAPI + React
          </p>
        </div>
      </footer>
    </div>
  );
}

export default App;
