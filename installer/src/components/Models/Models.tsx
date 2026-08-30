import React, { useState, useEffect } from 'react';
import { api } from '../../api/client';

interface Model {
  id: string;
  name: string;
  type: 'hf' | 'gguf';
  size_mb: number;
  path: string;
  status: 'downloaded' | 'downloading' | 'error';
}

export const Models: React.FC = () => {
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState<string | null>(null);

  useEffect(() => {
    fetchModels();
  }, []);

  const fetchModels = async () => {
    try {
      const response = await api.search('nettrades.model', []);
      if (response.status === 'success' && response.data) {
        setModels(response.data);
      }
    } catch (error) {
      console.error('Failed to fetch models:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async (modelName: string, modelType: string) => {
    setDownloading(modelName);
    try {
      // Call the backend to download the model
      const response = await api.createJob({
        type: 'download_model',
        model_name: modelName,
        model_type: modelType,
      });
      if (response.status === 'success') {
        await fetchModels();
      }
    } catch (error) {
      console.error('Failed to download model:', error);
    } finally {
      setDownloading(null);
    }
  };

  if (loading) {
    return <div className="loading">Loading models...</div>;
  }

  return (
    <div className="models-container">
      <div className="header-actions">
        <h2>Model Library</h2>
        <button className="btn-primary" onClick={fetchModels}>Refresh</button>
      </div>

      <div className="model-list">
        {models.length === 0 ? (
          <div className="empty-state">
            <p>No models available. Download a model to get started.</p>
          </div>
        ) : (
          models.map((model) => (
            <div key={model.id} className="model-item">
              <div className="model-info">
                <h4>{model.name}</h4>
                <div className="model-meta">
                  <span className="model-type">{model.type.toUpperCase()}</span>
                  <span className="model-size">{model.size_mb} MB</span>
                  <span className={`model-status status-${model.status}`}>{model.status}</span>
                </div>
              </div>
              <div className="model-actions">
                {model.status === 'downloaded' ? (
                  <button className="btn-secondary" disabled>Downloaded</button>
                ) : model.status === 'downloading' || downloading === model.name ? (
                  <button className="btn-secondary" disabled>Downloading...</button>
                ) : (
                  <button 
                    className="btn-primary" 
                    onClick={() => handleDownload(model.name, model.type)}
                  >
                    Download Model
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Available models to download */}
      <div className="available-models">
        <h3>Available Models</h3>
        <div className="model-grid">
          {[
            { name: 'DeepSeek-R1-Distill-Qwen-1.5B', type: 'gguf', size: 1040 },
            { name: 'deepseek-7b', type: 'hf', size: 14500 },
            { name: 'deepseek-r1-distill-qwen-7b-q4_k_m', type: 'gguf', size: 4360 },
          ].map((model) => (
            <div key={model.name} className="model-card">
              <h4>{model.name}</h4>
              <p>{model.type} • {model.size} MB</p>
              <button 
                className="btn-primary" 
                onClick={() => handleDownload(model.name, model.type)}
                disabled={downloading === model.name}
              >
                {downloading === model.name ? 'Downloading...' : 'Download'}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};