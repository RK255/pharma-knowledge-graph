// API Response Types
export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  provenance_entries: number;
  indexed_drugs: number;
}

export interface SearchResult {
  drug_name: string;
  relevance_score: number;
}

export interface SearchResponse {
  status: string;
  query: string;
  total_results: number;
  results: SearchResult[];
}

export interface DrugSection {
  section_type: string;
  title: string;
  content_preview: string;
  provenance_hash: string;
}

export interface DrugResponse {
  status: string;
  drug_name: string;
  total_sections: number;
  sections: DrugSection[];
}

export interface ProvenanceData {
  fda_document_id: string;
  drug_name: string;
  set_id: string;
  section_type: string;
  title: string;
  citation: string;
  type: string;
}

export interface ProvenanceResponse {
  status: string;
  provenance_hash: string;
  data: ProvenanceData;
}
