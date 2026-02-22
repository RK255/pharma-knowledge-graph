// src/components/DrugDetail.tsx
import React, { useState, useEffect } from 'react';

interface DrugDetailProps {
  drugId: string;
  drugName: string;
}

export const DrugDetail: React.FC<DrugDetailProps> = ({ drugId, drugName }) => {
  const [drugData, setDrugData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const [activeSectionContent, setActiveSectionContent] = useState<string>("");
  const [showProvenance, setShowProvenance] = useState(false);

  useEffect(() => {
    const fetchDrug = async () => {
      setLoading(true);
      try {
        const res = await fetch(`/drug/${drugId}`);
        const data = await res.json();
        setDrugData(data);
      } catch (error) {
        console.error("Failed to fetch drug details", error);
      } finally {
        setLoading(false);
      }
    };
    fetchDrug();
  }, [drugId]);

  const openSection = async (sectionId: string) => {
    setActiveSection(sectionId);
    setActiveSectionContent("Loading...");
    try {
      const res = await fetch(`/section/${sectionId}`);
      const data = await res.json();
      setActiveSectionContent(data.content);
    } catch (error) {
      setActiveSectionContent("Error loading content.");
    }
  };

  // Helper to render provenance/metadata
  const renderProvenance = () => {
    if (!drugData) return null;

    const provenanceFields = [
      { key: 'Drug Name', value: drugData.name },
      { key: 'Set ID', value: drugData.set_id },
      { key: 'NDA/ANDA Number', value: drugData.nda },
      { key: 'NDC Codes', value: drugData.ndc },
      { key: 'Manufacturer', value: drugData.manufacturer },
      { key: 'AMA Citation', value: drugData.ama_citation },
      { key: 'Drug ID', value: drugData.drug_id },
      { key: 'Section Count', value: drugData.section_count?.toString() },
    ];

    return (
      <div className="bg-white p-6 rounded-lg shadow-lg border border-gray-200 mt-4">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-bold text-gray-800">Provenance & Identifiers</h3>
          <button onClick={() => setShowProvenance(false)} className="text-gray-500 hover:text-gray-700">
            <span className="text-2xl">&times;</span>
          </button>
        </div>
        <div className="space-y-3 max-h-96 overflow-y-auto">
          {provenanceFields.map(field => (
            <div key={field.key} className="flex flex-col sm:flex-row sm:justify-between border-b border-gray-100 pb-2">
              <span className="font-semibold text-gray-600 text-sm mr-4">{field.key}</span>
              <span className="font-mono text-xs text-gray-800 break-all sm:text-right max-w-xs">
                {field.value || 'N/A'}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  };

  if (loading) return <div className="text-center py-12">Loading {drugName}...</div>;
  if (!drugData) return <div className="text-center py-12 text-red-500">Drug not found.</div>;

  return (
    <div className="bg-white shadow overflow-hidden sm:rounded-lg">
      {/* Header Section */}
      <div className="px-4 py-5 sm:px-6 border-b border-gray-200 bg-gray-50">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center">
          <div>
            <h3 className="text-xl leading-6 font-bold text-gray-900">
              {drugData.name}
            </h3>
            <p className="mt-1 text-sm text-gray-500 font-mono">
              Set ID: {drugData.set_id}
            </p>
          </div>
          <button 
            onClick={() => setShowProvenance(!showProvenance)}
            className="mt-3 sm:mt-0 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 transition-colors shadow-sm"
          >
            {showProvenance ? 'Hide Provenance' : 'View Provenance'}
          </button>
        </div>
        
        {/* Provenance Area */}
        {showProvenance && renderProvenance()}
      </div>
      
      {/* Sections Count Bar */}
      <div className="border-b border-gray-200 px-4 py-3 flex items-center justify-between bg-white">
        <span className="text-sm font-medium text-gray-700">
          {drugData.section_count} Sections Found
        </span>
      </div>

      {/* Main Content Area */}
      <div className="flex">
        {/* Left Sidebar: Sections List */}
        <div className="w-1/3 border-r border-gray-200 max-h-[600px] overflow-y-auto bg-white">
          <ul className="divide-y divide-gray-100">
            {drugData.sections.map((section: any) => (
              <li 
                key={section.section_id}
                onClick={() => openSection(section.section_id)}
                className={`px-4 py-3 cursor-pointer transition-colors
                           ${activeSection === section.section_id 
                             ? 'bg-blue-50 border-l-4 border-blue-500' 
                             : 'hover:bg-gray-50 border-l-4 border-transparent'}`}
              >
                <div className="text-sm font-medium text-gray-800 truncate">{section.title}</div>
                <div className="text-xs text-gray-500 mt-1 uppercase tracking-wider">{section.section_type}</div>
              </li>
            ))}
          </ul>
        </div>

        {/* Right Content Viewer */}
        <div className="w-2/3 p-6 bg-gray-50 max-h-[600px] overflow-y-auto min-h-[400px]">
          {activeSection ? (
            <div>
              <h4 className="text-lg font-semibold text-gray-800 mb-4 border-b pb-2">
                Section Content
              </h4>
              <div className="prose prose-sm max-w-none text-gray-700 whitespace-pre-wrap font-mono text-xs bg-white p-4 rounded border border-gray-200 shadow-sm">
                {activeSectionContent}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-gray-400">
              <svg className="w-16 h-16 mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p>Select a section from the list to view content</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
