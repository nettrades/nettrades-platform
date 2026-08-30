import React, { useState, useEffect } from 'react';
import { api } from '../../api/client';

interface GpuNode {
  id: string;
  name: string;
  model: string;
  vram_gb: number;
  price_per_hour: number;
  status: 'online' | 'offline' | 'busy';
  last_heartbeat: string;
}

export const GPUs: React.FC = () => {
  const [nodes, setNodes] = useState<GpuNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [showRegister, setShowRegister] = useState(false);
  const [newNode, setNewNode] = useState({
    name: '',
    model: '',
    vram_gb: 0,
    price_per_hour: 0,
  });

  useEffect(() => {
    fetchNodes();
    // Auto-refresh every 10 seconds
    const interval = setInterval(fetchNodes, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchNodes = async () => {
    try {
      const response = await api.getGpuNodes();
      if (response.status === 'success' && response.data) {
        setNodes(response.data);
      }
    } catch (error) {
      console.error('Failed to fetch GPU nodes:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async () => {
    try {
      const response = await api.registerGpuNode(newNode);
      if (response.status === 'success') {
        setShowRegister(false);
        setNewNode({ name: '', model: '', vram_gb: 0, price_per_hour: 0 });
        await fetchNodes();
      }
    } catch (error) {
      console.error('Failed to register GPU node:', error);
    }
  };

  if (loading) {
    return <div className="loading">Loading GPU nodes...</div>;
  }

  return (
    <div className="gpus-container">
      <div className="header-actions">
        <h2>GPU Nodes</h2>
        <button className="btn-primary" onClick={() => setShowRegister(true)}>
          Register GPU
        </button>
      </div>

      <div className="gpu-grid">
        {nodes.length === 0 ? (
          <div className="empty-state">
            <p>No GPU nodes registered.</p>
          </div>
        ) : (
          nodes.map((node) => (
            <div key={node.id} className="gpu-card">
              <div className="gpu-header">
                <h3>{node.name}</h3>
                <span className={`status status-${node.status}`}>{node.status}</span>
              </div>
              <div className="gpu-details">
                <p><strong>Model:</strong> {node.model}</p>
                <p><strong>VRAM:</strong> {node.vram_gb} GB</p>
                <p><strong>Price:</strong> ${node.price_per_hour}/hr</p>
                <p><strong>Last Heartbeat:</strong> {new Date(node.last_heartbeat).toLocaleString()}</p>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Register Modal */}
      {showRegister && (
        <div className="modal-overlay">
          <div className="modal">
            <h3>Register GPU Node</h3>
            <div className="form-group">
              <label>GPU Name</label>
              <input
                type="text"
                value={newNode.name}
                onChange={(e) => setNewNode({ ...newNode, name: e.target.value })}
                placeholder="e.g., RTX 4090"
              />
            </div>
            <div className="form-group">
              <label>GPU Model</label>
              <input
                type="text"
                value={newNode.model}
                onChange={(e) => setNewNode({ ...newNode, model: e.target.value })}
                placeholder="e.g., NVIDIA GeForce RTX 4090"
              />
            </div>
            <div className="form-group">
              <label>VRAM (GB)</label>
              <input
                type="number"
                value={newNode.vram_gb}
                onChange={(e) => setNewNode({ ...newNode, vram_gb: parseInt(e.target.value) || 0 })}
              />
            </div>
            <div className="form-group">
              <label>Price per Hour ($)</label>
              <input
                type="number"
                step="0.01"
                value={newNode.price_per_hour}
                onChange={(e) => setNewNode({ ...newNode, price_per_hour: parseFloat(e.target.value) || 0 })}
              />
            </div>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setShowRegister(false)}>Cancel</button>
              <button className="btn-primary" onClick={handleRegister}>Register</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};