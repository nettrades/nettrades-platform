"use client";

import { useState, useEffect, useRef } from 'react';
import axios from 'axios';

export default function Home() {
  const [messages, setMessages] = useState<Array<{role: string, content: string}>>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [authEnabled, setAuthEnabled] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Load auth setting from environment (exposed via NEXT_PUBLIC_*)
    const enabled = process.env.NEXT_PUBLIC_AUTH_ENABLED === 'true';
    setAuthEnabled(enabled);

    // Try to restore thread from localStorage
    const storedThread = localStorage.getItem('threadId');
    if (storedThread) {
      setThreadId(storedThread);
      fetchHistory(storedThread);
    } else {
      const newThread = crypto.randomUUID();
      setThreadId(newThread);
      localStorage.setItem('threadId', newThread);
    }

    // If auth is enabled, try to load API key from localStorage or prompt user
    if (enabled) {
      const storedKey = localStorage.getItem('apiKey');
      if (storedKey) {
        setApiKey(storedKey);
      } else {
        // Prompt user for API key
        const key = prompt('Enter your API key:');
        if (key) {
          setApiKey(key);
          localStorage.setItem('apiKey', key);
        }
      }
    }
  }, []);

  const fetchHistory = async (tid: string) => {
    try {
      const res = await axios.get(`/api/history?session_id=${tid}`, {
        headers: authEnabled ? { 'X-API-Key': apiKey } : {},
      });
      if (res.data && res.data.length > 0) {
        const msgs = JSON.parse(res.data[0].messages);
        setMessages(msgs);
      }
    } catch (e) {
      console.warn('No history found or error fetching:', e);
    }
  };

  const sendMessage = async () => {
    if (!input.trim()) return;
    const userMsg = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await axios.post('/api/chat', {
        messages: [...messages, userMsg],
        thread_id: threadId,
      }, {
        headers: authEnabled ? { 'X-API-Key': apiKey } : {},
      });

      const assistantMsg = { role: 'assistant', content: res.data.analysis || 'No response' };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error: ' + String(err) }]);
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white p-4 flex flex-col">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold">NETTRADES AI Router</h1>
        {authEnabled && (
          <div className="text-sm text-gray-400">
            🔑 API Key: {apiKey ? '✓ Set' : '❌ Not set'}
          </div>
        )}
      </div>
      <div className="flex-1 overflow-y-auto space-y-2 mb-4">
        {messages.map((m, i) => (
          <div key={i} className={`p-2 rounded ${m.role === 'user' ? 'bg-blue-600' : 'bg-gray-700'}`}>
            <strong>{m.role}:</strong> {m.content}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <div className="flex gap-2">
        <input
          className="flex-1 p-2 rounded bg-gray-800 text-white border border-gray-600"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && sendMessage()}
          disabled={loading}
        />
        <button
          className="px-4 py-2 bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
          onClick={sendMessage}
          disabled={loading}
        >
          {loading ? '...' : 'Send'}
        </button>
      </div>
    </div>
  );
}