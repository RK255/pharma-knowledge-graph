import React from 'react';
import './Navigation.css';

const Navigation: React.FC = () => {
  return (
    <nav className="navigation">
      <div className="nav-container">
        <div className="nav-logo">
          <h1>PharmaGraph</h1>
        </div>
        <div className="nav-links">
          <a href="#dashboard" className="nav-link">Dashboard</a>
          <a href="#search" className="nav-link">Search</a>
        </div>
      </div>
    </nav>
  );
};

export default Navigation;
