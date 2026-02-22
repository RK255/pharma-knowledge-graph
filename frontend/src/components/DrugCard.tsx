import React, { useState } from 'react';
import { SearchResult } from '../types/api';
import { api } from '../services/api';
import './DrugCard.css';

interface DrugCardProps {
  drug: SearchResult;
}

const DrugCard: React.FC<DrugCardProps> = ({ drug }) => {
  const [details, setDetails] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const handleViewDetails = async () => {
    if (details) {
      setExpanded(!expanded);
      return;
    }

    setLoading(true);
    try {
      const drugDetails = await api.getDrugDetails(drug.drug_name);
      setDetails(drugDetails);
      setExpanded(true);
    } catch (error) {
      console.error('Failed to fetch drug details:', error);
    } finally {
      setLoading(false);
    }
  };

  const getRelevanceColor = (score: number) => {
    return score === 1 ? '#4CAF50' : '#FFC107';
  };

  const getSectionTypeColor = (sectionType: string) => {
    const colors: { [key: string]: string } = {
      'BOXED_WARNING': '#e74c3c',
      'INDICATIONS_AND_USAGE': '#3498db',
      'DOSAGE_AND_ADMINISTRATION': '#2ecc71',
      'WARNINGS_AND_PRECAUTIONS': '#f39c12',
      'ADVERSE_REACTIONS': '#9b59b6',
      'DRUG_INTERACTIONS': '#1abc9c',
      'USE_IN_SPECIFIC_POPULATIONS': '#34495e',
      'OVERDOSAGE': '#e67e22',
      'DESCRIPTION': '#95a5a6',
      'CLINICAL_PHARMACOLOGY': '#16a085',
      'NONCLINICAL_TOXICOLOGY': '#27ae60',
      'HOW_SUPPLIED': '#2980b9',
      'PATIENT_COUNSELING_INFORMATION': '#8e44ad',
      'INSTRUCTIONS_FOR_USE': '#c0392b',
      'MEDICATION_GUIDE': '#d35400'
    };
    return colors[sectionType] || '#7f8c8d';
  };

  return (
    <div className="drug-card">
      <div className="card-header">
        <h3 className="drug-name">{drug.drug_name}</h3>
        <span 
          className="relevance-score" 
          style={{ backgroundColor: getRelevanceColor(drug.relevance_score) }}
        >
          {drug.relevance_score === 1 ? 'Exact Match' : 'Partial Match'}
        </span>
      </div>
      
      <div className="card-actions">
        <button 
          onClick={handleViewDetails} 
          disabled={loading}
          className="details-button"
        >
          {loading ? 'Loading...' : expanded ? 'Hide Details' : 'View Details'}
        </button>
      </div>
      
      {expanded && details && (
        <div className="card-details">
          <div className="section-count">
            <span>{details.total_sections} FDA sections available</span>
          </div>
          
          <div className="sections-preview">
            {details.sections.slice(0, 5).map((section: any, index: number) => (
              <div key={index} className="section-preview">
                <div className="section-header">
                  <h4 style={{ color: getSectionTypeColor(section.section_type) }}>
                    {section.section_type.replace(/_/g, ' ')}
                  </h4>
                  <div className="provenance-badge">
                    <span className="hash-label">Hash:</span>
                    <span className="hash-value">{section.provenance_hash}</span>
                  </div>
                </div>
                <p>{section.title}</p>
              </div>
            ))}
            
            {details.total_sections > 5 && (
              <div className="more-sections">
                ... and {details.total_sections - 5} more sections
              </div>
            )}
          </div>
          
          <div className="provenance-info">
            <span className="provenance-label">🔒 100% FDA Data Integrity</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default DrugCard;
