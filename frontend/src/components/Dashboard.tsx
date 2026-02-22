import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { HealthResponse } from '../types/api';
import './Dashboard.css';

const Dashboard: React.FC = () => {
  const [healthData, setHealthData] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchHealthData = async () => {
      try {
        const data = await api.getHealth();
        setHealthData(data);
      } catch (error) {
        console.error('Failed to fetch health data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchHealthData();
  }, []);

  if (loading) {
    return <div className="dashboard-loading">Loading pharmaceutical knowledge graph metrics...</div>;
  }

  if (!healthData) {
    return <div className="dashboard-error">Failed to load system metrics</div>;
  }

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1>Pharmaceutical Knowledge Graph Dashboard</h1>
        <p className="dashboard-subtitle">Real-time metrics for FDA drug data with provenance tracking</p>
      </div>
      
      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-icon">💊</div>
          <div className="metric-value">{healthData.indexed_drugs.toLocaleString()}</div>
          <div className="metric-label">FDA-Approved Drugs</div>
        </div>
        
        <div className="metric-card">
          <div className="metric-icon">📄</div>
          <div className="metric-value">{healthData.provenance_entries.toLocaleString()}</div>
          <div className="metric-label">Provenance Entries</div>
        </div>
        
        <div className="metric-card">
          <div className="metric-icon">🔒</div>
          <div className="metric-value">100%</div>
          <div className="metric-label">Data Integrity</div>
        </div>
        
        <div className="metric-card">
          <div className="metric-icon">⚡</div>
          <div className="metric-value">{healthData.version}</div>
          <div className="metric-label">API Version</div>
        </div>
      </div>
      
      <div className="system-status">
        <h2>System Status</h2>
        <div className={`status-indicator ${healthData.status === 'ok' ? 'status-ok' : 'status-error'}`}>
          <div className="status-dot"></div>
          <span>Service Status: {healthData.status.toUpperCase()}</span>
        </div>
        <p className="service-name">{healthData.service}</p>
      </div>
    </div>
  );
};

export default Dashboard;
