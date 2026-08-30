import React from 'react';

interface SidebarProps {
  currentView: string;
  onNavigate: (view: string) => void;
}

const menuItems = [
  { id: 'dashboard', label: 'Dashboard', icon: '📊' },
  { id: 'chat', label: 'AI Chat', icon: '💬' },
  { id: 'models', label: 'Models', icon: '🧠' },
  { id: 'gpus', label: 'GPUs', icon: '🎮' },
  { divider: true },
  { id: 'nodes', label: 'Nodes', icon: '🖥️' },
  { id: 'vpn', label: 'VPN', icon: '🔒' },
  { divider: true },
  { id: 'ask-someone', label: 'Ask Someone', icon: '🙋' },
  { id: 'good-answer', label: 'Good Answer', icon: '⭐' },
  { id: 'training', label: 'Training', icon: '📚' },
  { id: 'marketplace', label: 'Marketplace', icon: '🏪' },
  { divider: true },
  { id: 'deploy', label: 'Deploy', icon: '🚀' },
  { id: 'queue', label: 'Queue', icon: '📋' },
  { id: 'monitor', label: 'Monitor', icon: '📈' },
  { id: 'containers', label: 'Containers', icon: '🐳' },
  { id: 'backup', label: 'Backup', icon: '💾' },
  { divider: true },
  { id: 'settings', label: 'Settings', icon: '⚙️' },
  { id: 'emergency-access', label: 'Emergency Access', icon: '🆘' },
  { id: 'logs', label: 'Logs', icon: '📜' },
  { id: 'about', label: 'About', icon: 'ℹ️' },
  { divider: true },
  { id: 'system-check', label: 'System Check', icon: '✅' },
  { id: 'install-log', label: 'Install Log', icon: '📝' },
  { id: 'credentials', label: 'Credentials', icon: '🔑' },
  { id: 'modules', label: 'Modules', icon: '🧩' },
];

export const Sidebar: React.FC<SidebarProps> = ({ currentView, onNavigate }) => {
  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h2>NETTRADES</h2>
        <span className="version">v1.0.0</span>
      </div>
      <nav className="sidebar-nav">
        {menuItems.map((item, index) => {
          if ('divider' in item) {
            return <hr key={`divider-${index}`} className="sidebar-divider" />;
          }
          return (
            <button
              key={item.id}
              className={`sidebar-item ${currentView === item.id ? 'active' : ''}`}
              onClick={() => onNavigate(item.id)}
            >
              <span className="icon">{item.icon}</span>
              <span className="label">{item.label}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
};