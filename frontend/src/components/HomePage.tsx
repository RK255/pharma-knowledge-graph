import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Container,
  Typography,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Alert
} from '@mui/material';
import { Search as SearchIcon } from '@mui/icons-material';
import { api } from '../services/api';
import { HealthResponse } from '../types/api';

const HomePage: React.FC = () => {
  const [stats, setStats] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await api.getHealth();
        setStats(data);
      } catch (err) {
        setError('Failed to load statistics');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
  }, []);

  const handleSearchClick = () => {
    navigate('/search');
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error">
        {error}
      </Alert>
    );
  }

  return (
    <Container maxWidth="lg">
      <Box sx={{ my: 4 }}>
        <Typography variant="h3" component="h1" gutterBottom align="center">
          Pharmaceutical Knowledge Graph
        </Typography>
        <Typography variant="h5" component="h2" gutterBottom align="center" color="text.secondary">
          FDA Regulatory Data with Complete Provenance Tracking
        </Typography>
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
          <Button
            variant="contained"
            size="large"
            startIcon={<SearchIcon />}
            onClick={handleSearchClick}
          >
            Search Drugs
          </Button>
        </Box>
      </Box>

      {stats && (
        <Box sx={{ my: 4 }}>
          <Typography variant="h4" component="h2" gutterBottom>
            System Overview
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
            <Card sx={{ flex: '1 1 200px' }}>
              <CardContent>
                <Typography variant="h6" component="div">
                  {stats.indexed_drugs.toLocaleString()}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Indexed Drugs
                </Typography>
              </CardContent>
            </Card>
            <Card sx={{ flex: '1 1 200px' }}>
              <CardContent>
                <Typography variant="h6" component="div">
                  {stats.provenance_entries.toLocaleString()}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Provenance Entries
                </Typography>
              </CardContent>
            </Card>
            <Card sx={{ flex: '1 1 200px' }}>
              <CardContent>
                <Typography variant="h6" component="div">
                  {stats.version}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  API Version
                </Typography>
              </CardContent>
            </Card>
            <Card sx={{ flex: '1 1 200px' }}>
              <CardContent>
                <Typography variant="h6" component="div">
                  {stats.status}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  System Status
                </Typography>
              </CardContent>
            </Card>
          </Box>
        </Box>
      )}
    </Container>
  );
};

export default HomePage;
