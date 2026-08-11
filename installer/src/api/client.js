// =============================================================================
// API Client – Connects Launcher to Backend Services
// =============================================================================

const axios = require('axios');

class NettradesAPI {
    constructor(serverUrl = 'http://localhost') {
        this.serverUrl = serverUrl;
        this.odooProxy = `${serverUrl}:8090`;
        this.langgraph = `${serverUrl}:8000`;
        this.ui = `${serverUrl}:3002`;
    }

    // ─── Odoo Proxy API ───
    async getGPUNodes() {
        return this._get(`${this.odooProxy}/api/v1/gpu/nodes`);
    }

    async registerGPU(data) {
        return this._post(`${this.odooProxy}/api/v1/gpu/register`, data);
    }

    async scanNetwork() {
        return this._post(`${this.odooProxy}/api/v1/admin/scan_network`);
    }

    async installNode(host, token) {
        return this._post(`${this.odooProxy}/api/v1/admin/install_node`, { host, token });
    }

    // ─── LangGraph API ───
    async chat(messages, model, stream = false) {
        return this._post(`${this.langgraph}/runs/stream`, {
            input: { messages },
            config: { configurable: { thread_id: crypto.randomUUID() } }
        }, stream);
    }

    async askSomeone(question, category, urgency) {
        return this._post(`${this.langgraph}/runs/stream`, {
            input: {
                question,
                category,
                urgency,
                action: 'ask_someone'
            }
        });
    }

    async goodAnswer(question, answer, rating) {
        return this._post(`${this.langgraph}/runs/stream`, {
            input: {
                question,
                answer,
                rating,
                action: 'good_answer'
            }
        });
    }

    // ─── GPU Management Agent ───
    async getGPUClusterStatus() {
        return this._post(`${this.langgraph}/runs/stream`, {
            input: { action: 'gpu_status' }
        });
    }

    // ─── Training ───
    async startTraining(dataset, model, method) {
        return this._post(`${this.langgraph}/runs/stream`, {
            input: {
                dataset,
                model,
                method,
                action: 'start_training'
            }
        });
    }

    // ─── Private Methods ───
    async _get(url) {
        const response = await axios.get(url);
        return response.data;
    }

    async _post(url, data, stream = false) {
        if (stream) {
            return axios.post(url, data, { responseType: 'stream' });
        }
        const response = await axios.post(url, data);
        return response.data;
    }
}

module.exports = NettradesAPI;