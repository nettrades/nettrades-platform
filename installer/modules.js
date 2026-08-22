// =============================================================================
// FILE: installer/modules.js
// PURPOSE: Module definitions for modular installation
// =============================================================================

const MODULES = {
    core: {
        id: 'core',
        name: '🖥️ Core Platform',
        description: 'Odoo, PostgreSQL, LangGraph, and core services',
        size: '~5 GB',
        time: '15 min',
        dependencies: [],
        adminRequired: true,
        required: true,
        features: ['Odoo 19', 'PostgreSQL 17', 'LangGraph', 'API Gateway'],
        icon: '🏗️'
    },
    'gpu-inference': {
        id: 'gpu-inference',
        name: '🎮 GPU Inference',
        description: 'NVIDIA Dynamo + vLLM for GPU-accelerated inference',
        size: '~8 GB',
        time: '20 min',
        dependencies: ['core'],
        adminRequired: true,
        required: false,
        features: ['NVIDIA Dynamo', 'vLLM', 'Model Management', 'GPU Scheduling'],
        icon: '⚡'
    },
    'cpu-fallback': {
        id: 'cpu-fallback',
        name: '💻 CPU Fallback',
        description: 'llama.cpp for CPU inference (zero-dependency)',
        size: '~2 GB',
        time: '5 min',
        dependencies: ['core'],
        adminRequired: false,
        required: false,
        features: ['llama.cpp', 'CPU Inference', 'GGUF Models'],
        icon: '🖥️'
    },
    'ai-services': {
        id: 'ai-services',
        name: '🤖 AI Services',
        description: 'Ask Someone, Good Answer, Training, and agents',
        size: '~1 GB',
        time: '10 min',
        dependencies: ['core', 'gpu-inference'],
        adminRequired: false,
        required: false,
        features: ['Ask Someone', 'Good Answer', 'Fine-Tuning', 'Agent Management'],
        icon: '🧠'
    },
    monitoring: {
        id: 'monitoring',
        name: '📊 Monitoring',
        description: 'Prometheus, Grafana, Loki, Tempo',
        size: '~2 GB',
        time: '5 min',
        dependencies: ['core'],
        adminRequired: false,
        required: false,
        features: ['Prometheus', 'Grafana', 'Loki Logs', 'Tempo Traces'],
        icon: '📈'
    },
    'gpu-marketplace': {
        id: 'gpu-marketplace',
        name: '💰 GPU Marketplace',
        description: 'Buy and sell GPU compute on the network',
        size: '~500 MB',
        time: '3 min',
        dependencies: ['core'],
        adminRequired: false,
        required: false,
        features: ['GPU Listings', 'Booking', 'Billing'],
        icon: '💵'
    },
    bridge: {
        id: 'bridge',
        name: '🔀 Bridge Router',
        description: 'Hub-and-spoke routing between nodes',
        size: '~200 MB',
        time: '2 min',
        dependencies: ['core'],
        adminRequired: true,
        required: false,
        features: ['Request Routing', 'Node Discovery', 'Load Balancing'],
        icon: '🌉'
    },
    'node-agent': {
        id: 'node-agent',
        name: '🖥️ Node Agent',
        description: 'GPU node agent for distributed inferencing',
        size: '~100 MB',
        time: '2 min',
        dependencies: ['core'],
        adminRequired: false,
        required: false,
        features: ['GPU Discovery', 'Registration', 'Heartbeat'],
        icon: '📡'
    }
};

const DEPENDENCY_MAP = {
    core: [],
    'gpu-inference': ['core'],
    'cpu-fallback': ['core'],
    'ai-services': ['core', 'gpu-inference'],
    monitoring: ['core'],
    'gpu-marketplace': ['core'],
    bridge: ['core'],
    'node-agent': ['core']
};

function getModule(id) {
    return MODULES[id] || null;
}

function getModuleDependencies(id) {
    return DEPENDENCY_MAP[id] || [];
}

function getInstallableModules() {
    return Object.keys(MODULES);
}

function isAdminRequired(id) {
    return MODULES[id]?.adminRequired || false;
}

function getModuleSize(id) {
    return MODULES[id]?.size || 'Unknown';
}

function getModuleTime(id) {
    return MODULES[id]?.time || 'Unknown';
}

module.exports = {
    MODULES,
    DEPENDENCY_MAP,
    getModule,
    getModuleDependencies,
    getInstallableModules,
    isAdminRequired,
    getModuleSize,
    getModuleTime
};