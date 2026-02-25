// src/components/DrugDetail.tsx
import React, { useState, useEffect } from 'react';
import { GRC20Structure } from './GRC20Structure';
import PubChemCard from './PubChemCard';

interface DrugDetailProps {
  drugId: string;
  drugName: string;
}

// Use local API in development
const API_BASE = window.location.hostname === 'localhost' 
  ? 'http://localhost:8000' 
  : 'https://api.pharma.bowsernodes.dynns.com';

export const DrugDetail: React.FC<DrugDetailProps> = ({ drugId, drugName }) => {
  const [drugData, setDrugData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const [activeSectionContent, setActiveSectionContent] = useState<string>("");
  const [showProvenance, setShowProvenance] = useState(false);
  const [showGRC20, setShowGRC20] = useState(false);

  useEffect(() => {
    const fetchDrug = async () => {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/drug/${drugId}`);
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
      const res = await fetch(`${API_BASE}/section/${sectionId}`);
      const data = await res.json();
      setActiveSectionContent(data.content);
    } catch (error) {
      setActiveSectionContent("Error loading content.");
    }
  };

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
      <div className="bg-[#1a1a2e] p-6 rounded-lg border border-[#2d2d4a] mt-4">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-bold text-[#e4e4f1]">Provenance & Identifiers</h3>
          <button onClick={() => setShowProvenance(false)} className="text-[#6b6b80] hover:text-[#e4e4f1]">
            <span className="text-2xl">&times;</span>
          </button>
        </div>
        <div className="space-y-3 max-h-96 overflow-y-auto">
          {provenanceFields.map(field => (
            <div key={field.key} className="flex flex-col sm:flex-row sm:justify-between border-b border-[#2d2d4a] pb-2">
              <span className="font-semibold text-[#a0a0b8] text-sm mr-4">{field.key}</span>
              <span className="font-mono text-xs text-[#e4e4f1] break-all sm:text-right max-w-xs">
                {field.value || 'N/A'}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  };

  if (loading) return <div className="text-center py-12 text-[#a0a0b8]">Loading {drugName}...</div>;
  if (!drugData) return <div className="text-center py-12 text-[#ef4444]">Drug not found.</div>;

  return (
    <div className="space-y-6">
      {/* Header Section */}
      <div className="bg-[#1a1a2e] shadow overflow-hidden sm:rounded-lg border border-[#2d2d4a]">
        <div className="px-4 py-5 sm:px-6 border-b border-[#2d2d4a] bg-[#252542]">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center">
            <div>
              <h3 className="text-xl leading-6 font-bold text-[#e4e4f1]">
                {drugData.name}
              </h3>
              <p className="mt-1 text-sm text-[#6b6b80] font-mono">
                Set ID: {drugData.set_id}
              </p>
            </div>
            <div className="flex space-x-2 mt-3 sm:mt-0">
              <button 
                onClick={() => {
                  setShowProvenance(!showProvenance);
                  setShowGRC20(false);
                }}
                className="px-4 py-2 bg-[#3b82f6] text-white text-sm font-medium rounded-md hover:bg-[#2563eb] transition-colors shadow-sm"
              >
                {showProvenance ? 'Hide Provenance' : 'View Provenance'}
              </button>
              <button 
                onClick={() => {
                  setShowGRC20(!showGRC20);
                  setShowProvenance(false);
                }}
                className="px-4 py-2 bg-[#8b5cf6] text-white text-sm font-medium rounded-md hover:bg-[#7c3aed] transition-colors shadow-sm"
              >
                {showGRC20 ? 'Hide GRC-20' : 'GRC-20 Structure'}
              </button>
            </div>
          </div>
          
          {showProvenance && renderProvenance()}
        </div>
        
        {/* PubChem Card */}
        <PubChemCard drugName={drugName} drugId={drugId} />
        
        {/* Sections Count Bar */}
        <div className="border-b border-[#2d2d4a] px-4 py-3 flex items-center justify-between bg-[#1a1a2e]">
          <span className="text-sm font-medium text-[#a0a0b8]">
            {drugData.section_count} Sections Found
          </span>
        </div>

        {/* Main Content Area */}
        <div className="flex">
          {/* Left Sidebar: Sections List */}
          <div className="w-1/3 border-r border-[#2d2d4a] max-h-[600px] overflow-y-auto bg-[#1a1a2e]">
            <ul className="divide-y divide-[#2d2d4a]">
              {drugData.sections.map((section: any) => (
                <li 
                  key={section.section_id}
                  onClick={() => openSection(section.section_id)}
                  className={`px-4 py-3 cursor-pointer transition-colors
                             ${activeSection === section.section_id 
                               ? 'bg-[#252542] border-l-4 border-[#8b5cf6]' 
                               : 'hover:bg-[#252542] border-l-4 border-transparent'}`}
                >
                  <div className="text-sm font-medium text-[#e4e4f1] truncate">{section.title}</div>
                  <div className="text-xs text-[#6b6b80] mt-1 uppercase tracking-wider">{section.section_type}</div>
                </li>
              ))}
            </ul>
          </div>

          {/* Right Content Viewer */}
          <div className="w-2/3 p-6 bg-[#0f0f23] max-h-[600px] overflow-y-auto min-h-[400px]">
            {activeSection ? (
              <div>
                <h4 className="text-lg font-semibold text-[#e4e4f1] mb-4 border-b border-[#2d2d4a] pb-2">
                  Section Content
                </h4>
                <div className="prose prose-sm max-w-none text-[#a0a0b8] whitespace-pre-wrap font-mono text-xs bg-[#1a1a2e] p-4 rounded border border-[#2d2d4a] shadow-sm">
                  {activeSectionContent}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-[#6b6b80]">
                <svg className="w-16 h-16 mb-4 text-[#2d2d4a]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p>Select a section from the list to view content</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* GRC-20 Structure Panel */}
      {showGRC20 && (
        <GRC20Structure drugId={drugId} drugName={drugName} />
      )}
    </div>
  );
};
