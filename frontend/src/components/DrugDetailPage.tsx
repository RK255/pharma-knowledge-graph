import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  Box,
  Typography,
  Card,
  Tabs,
  Tab,
  List,
  ListItem,
  ListItemText,
  Chip,
  CircularProgress,
  Alert,
  Button
} from '@mui/material';
import { ArrowBack as ArrowBackIcon } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import { DrugResponse, DrugSection } from '../types/api';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

const TabPanel: React.FC<TabPanelProps> = ({ children, value, index }) => {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`drug-tabpanel-${index}`}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
};

const DrugDetailPage: React.FC = () => {
  const { drugName } = useParams<{ drugName: string }>();
  const [drugData, setDrugData] = useState<DrugResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tabValue, setTabValue] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchDrugDetails = async () => {
      if (!drugName) return;

      try {
        const data = await api.getDrugDetails(drugName);
        setDrugData(data);
      } catch (err) {
        setError('Failed to load drug details. Please try again.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchDrugDetails();
  }, [drugName]);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const handleProvenanceClick = (hash: string) => {
    navigate(`/provenance/${hash}`);
  };

  const getSectionTypeColor = (sectionType: string): "error" | "warning" | "success" | "info" | "default" | "secondary" | "primary" => {
    const colors: Record<string, "error" | "warning" | "success" | "info" | "default" | "secondary" | "primary"> = {
      'BOXED_WARNING': 'error',
      'WARNINGS_AND_PRECAUTIONS': 'warning',
      'CONTRAINDICATIONS': 'error',
      'ADVERSE_REACTIONS': 'warning',
      'INDICATIONS_AND_USAGE': 'success',
      'DOSAGE_AND_ADMINISTRATION': 'info',
      'DESCRIPTION': 'default',
      'CLINICAL_PHARMACOLOGY': 'secondary'
    };
    return colors[sectionType] || 'default';
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error || !drugData) {
    return (
      <Alert severity="error">
        {error || 'Drug not found.'}
      </Alert>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/search')}
          sx={{ mr: 2 }}
        >
          Back to Search
        </Button>
        <Typography variant="h4" component="h1">
          {drugData.drug_name}
        </Typography>
      </Box>

      <Typography variant="body1" color="text.secondary" paragraph>
        {drugData.total_sections} sections available with complete provenance tracking.
      </Typography>

      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tabs
          value={tabValue}
          onChange={handleTabChange}
          aria-label="Drug sections tabs"
          variant="scrollable"
          scrollButtons="auto"
        >
          <Tab label="All Sections" />
          <Tab label="Warnings" />
          <Tab label="Dosage" />
          <Tab label="Clinical Info" />
        </Tabs>
      </Box>

      <TabPanel value={tabValue} index={0}>
        <List>
          {drugData.sections.map((section: DrugSection, index: number) => (
            <Card key={index} sx={{ mb: 2 }}>
              <ListItem>
                <ListItemText
                  primary={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                      <Typography variant="h6">
                        {section.title}
                      </Typography>
                      <Chip
                        label={section.section_type.replace(/_/g, ' ')}
                        color={getSectionTypeColor(section.section_type)}
                        size="small"
                      />
                    </Box>
                  }
                  secondary={
                    <Box>
                      <Typography variant="body2" paragraph>
                        {section.content_preview}...
                      </Typography>
                      <Button
                        size="small"
                        onClick={() => handleProvenanceClick(section.provenance_hash)}
                      >
                        View Provenance
                      </Button>
                    </Box>
                  }
                />
              </ListItem>
            </Card>
          ))}
        </List>
      </TabPanel>

      <TabPanel value={tabValue} index={1}>
        <List>
          {drugData.sections
            .filter((section: DrugSection) => 
              section.section_type.includes('WARNING') || 
              section.section_type.includes('CONTRAINDICATION') ||
              section.section_type.includes('ADVERSE')
            )
            .map((section: DrugSection, index: number) => (
              <Card key={index} sx={{ mb: 2 }}>
                <ListItem>
                  <ListItemText
                    primary={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                        <Typography variant="h6">
                          {section.title}
                        </Typography>
                        <Chip
                          label={section.section_type.replace(/_/g, ' ')}
                          color={getSectionTypeColor(section.section_type)}
                          size="small"
                        />
                      </Box>
                    }
                    secondary={
                      <Box>
                        <Typography variant="body2" paragraph>
                          {section.content_preview}...
                        </Typography>
                        <Button
                          size="small"
                          onClick={() => handleProvenanceClick(section.provenance_hash)}
                        >
                          View Provenance
                        </Button>
                      </Box>
                    }
                  />
                </ListItem>
              </Card>
            ))}
        </List>
      </TabPanel>

      <TabPanel value={tabValue} index={2}>
        <List>
          {drugData.sections
            .filter((section: DrugSection) => 
              section.section_type.includes('DOSAGE') || 
              section.section_type.includes('ADMINISTRATION')
            )
            .map((section: DrugSection, index: number) => (
              <Card key={index} sx={{ mb: 2 }}>
                <ListItem>
                  <ListItemText
                    primary={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                        <Typography variant="h6">
                          {section.title}
                        </Typography>
                        <Chip
                          label={section.section_type.replace(/_/g, ' ')}
                          color={getSectionTypeColor(section.section_type)}
                          size="small"
                        />
                      </Box>
                    }
                    secondary={
                      <Box>
                        <Typography variant="body2" paragraph>
                          {section.content_preview}...
                        </Typography>
                        <Button
                          size="small"
                          onClick={() => handleProvenanceClick(section.provenance_hash)}
                        >
                          View Provenance
                        </Button>
                      </Box>
                    }
                  />
                </ListItem>
              </Card>
            ))}
        </List>
      </TabPanel>

      <TabPanel value={tabValue} index={3}>
        <List>
          {drugData.sections
            .filter((section: DrugSection) => 
              section.section_type.includes('INDICATION') || 
              section.section_type.includes('PHARMACOLOGY') ||
              section.section_type.includes('CLINICAL_STUDIES')
            )
            .map((section: DrugSection, index: number) => (
              <Card key={index} sx={{ mb: 2 }}>
                <ListItem>
                  <ListItemText
                    primary={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                        <Typography variant="h6">
                          {section.title}
                        </Typography>
                        <Chip
                          label={section.section_type.replace(/_/g, ' ')}
                          color={getSectionTypeColor(section.section_type)}
                          size="small"
                        />
                      </Box>
                    }
                    secondary={
                      <Box>
                        <Typography variant="body2" paragraph>
                          {section.content_preview}...
                        </Typography>
                        <Button
                          size="small"
                          onClick={() => handleProvenanceClick(section.provenance_hash)}
                        >
                          View Provenance
                        </Button>
                      </Box>
                    }
                  />
                </ListItem>
              </Card>
            ))}
        </List>
      </TabPanel>
    </Box>
  );
};

export default DrugDetailPage;
