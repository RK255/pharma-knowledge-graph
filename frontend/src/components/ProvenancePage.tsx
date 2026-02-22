import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  Box,
  Typography,
  Card,
  CardContent,
  CircularProgress,
  Alert,
  Button,
  Chip
} from '@mui/material';
import { ArrowBack as ArrowBackIcon } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import { ProvenanceResponse } from '../types/api';

const ProvenancePage: React.FC = () => {
  const { hash } = useParams<{ hash: string }>();
  const [provenanceData, setProvenanceData] = useState<ProvenanceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchProvenance = async () => {
      if (!hash) return;

      try {
        const data = await api.lookupProvenance(hash);
        setProvenanceData(data);
      } catch (err) {
        setError('Failed to load provenance data. Please try again.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchProvenance();
  }, [hash]);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error || !provenanceData) {
    return (
      <Alert severity="error">
        {error || 'Provenance data not found.'}
      </Alert>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate(-1)}
          sx={{ mr: 2 }}
        >
          Back
        </Button>
        <Typography variant="h4" component="h1">
          Provenance Verification
        </Typography>
      </Box>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Provenance Hash
          </Typography>
          <Typography variant="body2" sx={{ fontFamily: 'monospace', mb: 2 }}>
            {provenanceData.provenance_hash}
          </Typography>
          <Chip label="Verified" color="success" size="small" />
        </CardContent>
      </Card>

      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
        <Card sx={{ flex: '1 1 300px' }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Document Information
            </Typography>
            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary">
                FDA Document ID
              </Typography>
              <Typography variant="body1" sx={{ fontFamily: 'monospace' }}>
                {provenanceData.data.fda_document_id}
              </Typography>
            </Box>
            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary">
                FDA Set ID
              </Typography>
              <Typography variant="body1" sx={{ fontFamily: 'monospace' }}>
                {provenanceData.data.set_id}
              </Typography>
            </Box>
            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary">
                Drug Name
              </Typography>
              <Typography variant="body1">
                {provenanceData.data.drug_name}
              </Typography>
            </Box>
            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary">
                Data Type
              </Typography>
              <Chip label={provenanceData.data.type} size="small" />
            </Box>
          </CardContent>
        </Card>

        <Card sx={{ flex: '1 1 300px' }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Section Information
            </Typography>
            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary">
                Section Type
              </Typography>
              <Typography variant="body1">
                {provenanceData.data.section_type.replace(/_/g, ' ')}
              </Typography>
            </Box>
            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary">
                Section Title
              </Typography>
              <Typography variant="body1">
                {provenanceData.data.title}
              </Typography>
            </Box>
            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary">
                Citation
              </Typography>
              <Typography variant="body1" sx={{ fontStyle: 'italic' }}>
                {provenanceData.data.citation}
              </Typography>
            </Box>
          </CardContent>
        </Card>
      </Box>

      <Card sx={{ mt: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Verification Status
          </Typography>
          <Typography variant="body1" paragraph>
            This data point has been verified against the original FDA regulatory submission. 
            The hash above can be used to cryptographically verify the integrity and authenticity 
            of this information.
          </Typography>
          <Typography variant="body2" color="text.secondary">
            The provenance system ensures that all pharmaceutical information in this knowledge 
            graph is traceable to its source document and has not been altered since ingestion.
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );
};

export default ProvenancePage;
