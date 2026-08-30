// installer/src/App.tsx
import React, { useState, useEffect } from 'react';
import { Sidebar } from './components/Layout/Sidebar';
import { Header } from './components/Layout/Header';
import { Dashboard } from './components/Dashboard/Dashboard';
import { Chat } from './components/Chat/Chat';
import { Models } from './components/Models/Models';
import { GPUs } from './components/GPUs/GPUs';
import { Nodes } from './components/Network/Nodes';
import { VPN } from './components/Network/VPN';
import { AskSomeone } from './components/AI/AskSomeone';
import { GoodAnswer } from './components/AI/GoodAnswer';
import { Training } from './components/AI/Training';
import { Marketplace } from './components/AI/Marketplace';
import { Deploy } from './components/Operations/Deploy';
import { Queue } from './components/Operations/Queue';
import { Monitor } from './components/Operations/Monitor';
import { Containers } from './components/Operations/Containers';
import { Backup } from './components/Operations/Backup';
import { Settings } from './components/Settings/Settings';
import { EmergencyAccess } from './components/Settings/EmergencyAccess';
import { Logs } from './components/Settings/Logs';
import { About } from './components/Settings/About';
import { SystemCheck } from './components/Tools/SystemCheck';
import { InstallLog } from './components/Tools/InstallLog';
import { Credentials } from './components/Tools/Credentials';
import { Modules } from './components/Tools/Modules';
import { api } from './api/client';
import './styles/index.css';

type View =
  | 'dashboard' | 'chat' | 'models' | 'gpus'
  | 'nodes' | 'vpn'
  | 'ask-someone' | 'good-answer' | 'training' | 'marketplace'
  | 'deploy' | 'queue' | 'monitor' | 'containers' | 'backup'
  | 'settings' | 'emergency-access' | 'logs' | 'about'
  | 'system-check' | 'install-log' | 'credentials' | 'modules';

const App: React.FC = () => {
  const [currentView, setCurrentView] = useState<View>('dashboard');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [backendInfo, setBackendInfo] = useState<{ backend: string } | null>(null);

  useEffect(() => {
    // Check authentication and backend
    api.health().then((response) => {
      if (response.status === 'success' && response.data) {
        setBackendInfo(response.data);
      }
    });
    const token = localStorage.getItem('auth_token');
    if (token) {
      api.validateSession().then((response) => {
        if (response.status === 'success') {
          setIsAuthenticated(true);
        }
      });
    }
  }, []);

  const renderView = () => {
    switch (currentView) {
      case 'dashboard': return <Dashboard />;
      case 'chat': return <Chat />;
      case 'models': return <Models />;
      case 'gpus': return <GPUs />;
      case 'nodes': return <Nodes />;
      case 'vpn': return <VPN />;
      case 'ask-someone': return <AskSomeone />;
      case 'good-answer': return <GoodAnswer />;
      case 'training': return <Training />;
      case 'marketplace': return <Marketplace />;
      case 'deploy': return <Deploy />;
      case 'queue': return <Queue />;
      case 'monitor': return <Monitor />;
      case 'containers': return <Containers />;
      case 'backup': return <Backup />;
      case 'settings': return <Settings />;
      case 'emergency-access': return <EmergencyAccess />;
      case 'logs': return <Logs />;
      case 'about': return <About />;
      case 'system-check': return <SystemCheck />;
      case 'install-log': return <InstallLog />;
      case 'credentials': return <Credentials />;
      case 'modules': return <Modules />;
      default: return <Dashboard />;
    }
  };

  if (!isAuthenticated) {
    return <LoginScreen onLogin={setIsAuthenticated} />;
  }

  return (
    <div className="app">
      <Sidebar currentView={currentView} onNavigate={setCurrentView} />
      <div className="main-content">
        <Header backend={backendInfo} />
        <div className="view-container">
          {renderView()}
        </div>
      </div>
    </div>
  );
};

// LoginScreen component (simplified)
const LoginScreen: React.FC<{ onLogin: (auth: boolean) => void }> = ({ onLogin }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleLogin = async () => {
    try {
      const response = await api.login(username, password);
      if (response.status === 'success') {
        localStorage.setItem('auth_token', response.data?.access_token || 'session');
        onLogin(true);
      } else {
        setError(response.message || 'Login failed');
      }
    } catch (err) {
      setError('Connection error');
    }
  };

  return (
    <div className="login-screen">
      <div className="login-box">
        <h1>NETTRADES</h1>
        <p>Sovereign AI Platform</p>
        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
        />
        {error && <div className="error">{error}</div>}
        <button onClick={handleLogin}>Login</button>
      </div>
    </div>
  );
};

export default App;