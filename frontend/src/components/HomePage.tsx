// src/components/HomePage.tsx
import React from 'react';

interface HomePageProps {
  children: React.ReactNode;
}

export const HomePage: React.FC<HomePageProps> = ({ children }) => {
  return (
    <div className="space-y-8">
      {/* Stats Section */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div className="text-center">
            <div className="text-3xl font-bold text-blue-600">51K+</div>
            <div className="text-sm text-gray-500 mt-1">Package Inserts</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-green-600">1M+</div>
            <div className="text-sm text-gray-500 mt-1">Sections</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-purple-600">100%</div>
            <div className="text-sm text-gray-500 mt-1">Provenance</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-orange-600">FDA</div>
            <div className="text-sm text-gray-500 mt-1">SPL Data</div>
          </div>
        </div>
      </div>

      {/* Search Section */}
      <div className="bg-gradient-to-r from-blue-500 to-purple-600 rounded-xl shadow-lg p-8">
        <h2 className="text-2xl font-bold text-white text-center mb-6">
          Search FDA Drug Information
        </h2>
        {children}
      </div>

      {/* Info Section */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-xl shadow-sm p-6">
          <div className="text-blue-500 text-2xl mb-3">📋</div>
          <h3 className="font-semibold text-gray-900 mb-2">Complete Package Inserts</h3>
          <p className="text-sm text-gray-600">
            Access full FDA-approved labeling including indications, dosage, contraindications, and more.
          </p>
        </div>
        <div className="bg-white rounded-xl shadow-sm p-6">
          <div className="text-green-500 text-2xl mb-3">🔍</div>
          <h3 className="font-semibold text-gray-900 mb-2">Full Provenance Tracking</h3>
          <p className="text-sm text-gray-600">
            Every piece of data is traceable to its source FDA document with set IDs and citations.
          </p>
        </div>
        <div className="bg-white rounded-xl shadow-sm p-6">
          <div className="text-purple-500 text-2xl mb-3">🏭</div>
          <h3 className="font-semibold text-gray-900 mb-2">Multiple Manufacturers</h3>
          <p className="text-sm text-gray-600">
            Compare labeling across different manufacturers for the same drug.
          </p>
        </div>
      </div>
    </div>
  );
};
