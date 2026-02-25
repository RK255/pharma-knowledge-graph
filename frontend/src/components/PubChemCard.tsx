import React, { useState, useEffect } from 'react';
import axios from 'axios';

interface PubChemData {
  rxcui: string;
  name: string;
  cid: string | null;
  sid: string | null;
  smiles: string | null;
  inchikey: string | null;
  iupac: string | null;
  pmid: string | null;
}

interface Props {
  drugName: string;
  drugId?: string;
}

// Use production API (same server)
const API_BASE = window.location.hostname === 'localhost' 
  ? 'http://localhost:8000' 
  : `https://api.pharma.bowsernodes.dynns.com`;

const PubChemCard: React.FC<Props> = ({ drugName, drugId }) => {
  const [data, setData] = useState<{ ingredients: PubChemData[] } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchPubChem = async () => {
      if (!drugId && !drugName) return;
      
      try {
        setLoading(true);
        // Use drug_id if available, otherwise fall back to name
        const url = drugId 
          ? `${API_BASE}/api/drug/${drugId}/pubchem`
          : `${API_BASE}/api/drug/${encodeURIComponent(drugName)}/pubchem`;
        const response = await axios.get(url);
        setData(response.data);
      } catch (err) {
        console.error('PubChem fetch error:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchPubChem();
  }, [drugName, drugId]);

  if (loading) return null;
  if (!data || !data.ingredients || data.ingredients.length === 0) return null;

  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <span style={styles.icon}>🧪</span>
        <span style={styles.title}>PubChem Properties</span>
      </div>
      {data.ingredients.map((ing, idx) => (
        <div key={ing.rxcui || idx} style={styles.ingredient}>
          <div style={styles.ingredientName}>{ing.name}</div>
          <div style={styles.grid}>
            {ing.cid && (
              <div style={styles.field}>
                <span style={styles.label}>CID</span>
                <a href={`https://pubchem.ncbi.nlm.nih.gov/compound/${ing.cid}`} target="_blank" rel="noreferrer" style={styles.link}>{ing.cid}</a>
              </div>
            )}
            {ing.sid && (
              <div style={styles.field}>
                <span style={styles.label}>SID</span>
                <a href={`https://pubchem.ncbi.nlm.nih.gov/substance/${ing.sid}`} target="_blank" rel="noreferrer" style={styles.link}>{ing.sid}</a>
              </div>
            )}
            {ing.pmid && (
              <div style={styles.field}>
                <span style={styles.label}>PubMed</span>
                <a href={`https://pubmed.ncbi.nlm.nih.gov/${ing.pmid.split('|')[0]}`} target="_blank" rel="noreferrer" style={styles.link}>{ing.pmid.split('|')[0]}</a>
              </div>
            )}
            {ing.smiles && (
              <div style={styles.fieldFull}>
                <span style={styles.label}>SMILES</span>
                <code style={styles.code}>{ing.smiles}</code>
              </div>
            )}
            {ing.inchikey && (
              <div style={styles.fieldFull}>
                <span style={styles.label}>InChIKey</span>
                <code style={styles.codeSmall}>{ing.inchikey.replace('InChIKey=', '')}</code>
              </div>
            )}
            {ing.iupac && (
              <div style={styles.fieldFull}>
                <span style={styles.label}>IUPAC Name</span>
                <span style={styles.value}>{ing.iupac}</span>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

const styles: { [key: string]: React.CSSProperties } = {
  card: {
    backgroundColor: '#1a1a2e',
    padding: '12px 16px',
    borderBottom: '1px solid #2d2d4a',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginBottom: '10px',
  },
  icon: {
    fontSize: '16px',
  },
  title: {
    color: '#a0a0b8',
    fontSize: '13px',
    fontWeight: 500,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  ingredient: {
    backgroundColor: '#0f0f23',
    borderRadius: '6px',
    padding: '10px',
    border: '1px solid #2d2d4a',
  },
  ingredientName: {
    color: '#38bdf8',
    fontSize: '14px',
    fontWeight: 500,
    marginBottom: '8px',
    textTransform: 'capitalize',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: '8px',
  },
  field: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  fieldFull: {
    gridColumn: '1 / -1',
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  label: {
    color: '#6b6b80',
    fontSize: '10px',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  value: {
    color: '#e4e4f1',
    fontSize: '12px',
  },
  link: {
    color: '#38bdf8',
    fontSize: '12px',
    textDecoration: 'none',
  },
  code: {
    color: '#a5f3fc',
    fontSize: '11px',
    fontFamily: 'monospace',
    backgroundColor: '#1a1a2e',
    padding: '4px 6px',
    borderRadius: '3px',
    wordBreak: 'break-all',
  },
  codeSmall: {
    color: '#a5f3fc',
    fontSize: '10px',
    fontFamily: 'monospace',
    backgroundColor: '#1a1a2e',
    padding: '3px 5px',
    borderRadius: '3px',
  },
};

export default PubChemCard;
