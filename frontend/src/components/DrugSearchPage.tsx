import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Container,
  Typography,
  TextField,
  Button,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemText,
  CircularProgress,
  Alert,
  InputAdornment
} from '@mui/material';
import { Search as SearchIcon, ArrowBack as ArrowBackIcon } from '@mui/icons-material';
import { api } from '../services/api';
import { SearchResponse, SearchResult } from '../types/api';

const DrugSearchPage: React.FC = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const navigate = useNavigate();

  const handleSearch = async () => {
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    setSearched(true);

    try {
      const data = await api.searchDrugs(query);
      setResults(data);
    } catch (err) {
      setError('Failed to search for drugs. Please try again.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const handleDrugClick = (drugName: string) => {
    navigate(`/drug/${encodeURIComponent(drugName)}`);
  };

  return (
    <Container maxWidth="lg">
      <Box sx={{ my: 4 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
          <Button
            startIcon={<ArrowBackIcon />}
            onClick={() => navigate('/')}
            sx={{ mr: 2 }}
          >
            Back to Home
          </Button>
          <Typography variant="h4" component="h1">
            Drug Search
          </Typography>
        </Box>

        <Box sx={{ mb: 4 }}>
          <TextField
            fullWidth
            label="Search for a drug"
            variant="outlined"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyPress={handleKeyPress}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <Button onClick={handleSearch} disabled={loading}>
                    <SearchIcon />
                  </Button>
                </InputAdornment>
              ),
            }}
          />
        </Box>

        {loading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
            <CircularProgress />
          </Box>
        )}

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {!loading && !error && searched && results && (
          <Box>
            <Typography variant="h6" gutterBottom>
              Found {results.total_results} results for "{results.query}"
            </Typography>
            <List>
              {results.results.map((result: SearchResult, index: number) => (
                <Card key={index} sx={{ mb: 2, cursor: 'pointer' }} onClick={() => handleDrugClick(result.drug_name)}>
                  <ListItem>
                    <ListItemText
                      primary={result.drug_name}
                      secondary={`Relevance Score: ${result.relevance_score}`}
                    />
                  </ListItem>
                </Card>
              ))}
            </List>
          </Box>
        )}

        {!loading && !error && searched && results && results.results.length === 0 && (
          <Alert severity="info">
            No drugs found matching your search.
          </Alert>
        )}
      </Box>
    </Container>
  );
};

export default DrugSearchPage;
