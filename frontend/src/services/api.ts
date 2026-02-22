import axios from 'axios';
import { SearchResponse, DrugResponse, HealthResponse, ProvenanceResponse } from '../types/api';

const API_BASE_URL = "http://192.168.50.180:8000";

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const api = {
  // Health check
  getHealth: async (): Promise<HealthResponse> => {
    const response = await apiClient.get<HealthResponse>('/');
    return response.data;
  },

  // Drug search
  searchDrugs: async (query: string): Promise<SearchResponse> => {
    const response = await apiClient.get<SearchResponse>(`/search?query=${encodeURIComponent(query)}`);
    return response.data;
  },

  // Get drug details
  getDrugDetails: async (drugName: string): Promise<DrugResponse> => {
    const response = await apiClient.get<DrugResponse>(`/drug/${encodeURIComponent(drugName)}`);
    return response.data;
  },

  // Lookup provenance
  lookupProvenance: async (hash: string): Promise<ProvenanceResponse> => {
    const response = await apiClient.get<ProvenanceResponse>(`/lookup/${encodeURIComponent(hash)}`);
    return response.data;
  },
};
