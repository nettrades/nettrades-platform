// ============================================================================
// NETTRADES AI Router – Chat Application
// Inspired by llama.cpp UI, ChatGPT, Claude, DeepSeek
// ============================================================================

// ─── State ────────────────────────────────────────────────────────────────────
const state = {
    conversations: [],
    currentConversationId: null,
    messages: [],
    isProcessing: false,
    isAuthenticated: false,
    authEnabled: false,
    user: null,
    modelName: 'DeepSeek-R1-Distill-Qwen-1.5B',
    backendStatus: 'connecting', // 'online' | 'offline' | 'connecting'
    threadId: null,
};

// ─── DOM References ──────────────────────────────────────────────────────────
const elements = {
    sidebar: document.getElementById('sidebar'),
    sidebarToggle: document.getElementById('sidebar-toggle'),
    mobileMenuBtn: document.getElementById('mobile-menu-btn'),
    conversationList: document.getElementById('conversation-list'),
    newChatBtn: document.getElementById('new-chat-btn'),
    chatTitle: document.getElementById('chat-title'),
    chatModel: document.getElementById('chat-model'),
    chatMessages: document.getElementById('chat-messages'),
    userInput: document.getElementById('user-input'),
    sendBtn: document.getElementById('send-btn'),
    statusText: document.getElementById('status-text-bottom'),
    statusDot: document.getElementById('status-dot'),
    statusTextTop: document.getElementById('status-text'),
    authBtn: document.getElementById('auth-btn'),
};

// ─── Utility ──────────────────────────────────────────────────────────────────
function generateId() {
    return Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
}

function formatDate(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    if (date.toDateString() === now.toDateString()) {
        return 'Today';
    }
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (date.toDateString() === yesterday.toDateString()) {
        return 'Yesterday';
    }
    return date.toLocaleDateString();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ─── Render Functions ──────────────────────────────────────────────────────

function renderConversations() {
    const list = elements.conversationList;
    list.innerHTML = '';
    state.conversations.forEach((conv) => {
        const item = document.createElement('div');
        item.className = `conversation-item${conv.id === state.currentConversationId ? ' active' : ''}`;
        item.dataset.id = conv.id;
        item.innerHTML = `
            <span class="conversation-title">${escapeHtml(conv.title || 'New Chat')}</span>
            <span class="conversation-date">${formatDate(conv.updatedAt || conv.createdAt)}</span>
        `;
        item.addEventListener('click', () => switchConversation(conv.id));
        list.appendChild(item);
    });
}

function renderMessages() {
    const container = elements.chatMessages;
    container.innerHTML = '';

    if (state.messages.length === 0) {
        // Show welcome message
        container.innerHTML = `
            <div class="welcome-message">
                <h1>🧠 <span>NETTRADES AI</span></h1>
                <p>Your Sovereign AI Platform. Ask me anything about GPU management, recruitment, or general knowledge.</p>
                <div class="features">
                    <span>⚡ Real-time streaming</span>
                    <span>🔒 Sovereign & secure</span>
                    <span>🖥️ GPU management</span>
                    <span>🤖 Multi-agent orchestration</span>
                </div>
            </div>
        `;
        return;
    }

    state.messages.forEach((msg, index) => {
        const div = document.createElement('div');
        div.className = `message ${msg.role}`;
        if (msg.role === 'assistant') {
            // Render markdown
            try {
                const html = marked.parse(msg.content);
                div.innerHTML = html;
                // Highlight code blocks
                div.querySelectorAll('pre code').forEach((block) => {
                    hljs.highlightElement(block);
                });
                // Render math (KaTeX)
                div.querySelectorAll('.math').forEach((el) => {
                    try {
                        katex.render(el.textContent, el, {
                            throwOnError: false,
                            displayMode: el.classList.contains('display'),
                        });
                    } catch (e) {
                        // Ignore
                    }
                });
            } catch (e) {
                div.textContent = msg.content;
            }
        } else {
            div.textContent = msg.content;
        }
        container.appendChild(div);
    });

    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
}

function showTypingIndicator() {
    const container = elements.chatMessages;
    // Remove existing indicator
    const existing = container.querySelector('.typing-indicator');
    if (existing) existing.remove();

    const div = document.createElement('div');
    div.className = 'typing-indicator';
    div.innerHTML = `
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function hideTypingIndicator() {
    const container = elements.chatMessages;
    const existing = container.querySelector('.typing-indicator');
    if (existing) existing.remove();
}

function updateStatus(status, text) {
    state.backendStatus = status;
    const dot = elements.statusDot;
    const statusText = elements.statusTextTop;
    const bottomText = elements.statusTextBottom;

    dot.className = 'status-dot';
    if (status === 'online') {
        dot.classList.add('online');
        statusText.textContent = text || 'Online';
        bottomText.textContent = 'Ready';
    } else if (status === 'offline') {
        dot.classList.add('offline');
        statusText.textContent = text || 'Offline';
        bottomText.textContent = '⚠️ Using fallback model';
    } else {
        dot.classList.add('connecting');
        statusText.textContent = text || 'Connecting...';
        bottomText.textContent = 'Connecting...';
    }
}

function updateAuthUI() {
    const btn = elements.authBtn;
    if (state.authEnabled) {
        if (state.isAuthenticated && state.user) {
            btn.textContent = `👤 ${state.user.name || state.user.email}`;
            btn.className = 'auth-btn authenticated';
            btn.onclick = () => logout();
            elements.userInput.disabled = false;
            elements.sendBtn.disabled = false;
        } else {
            btn.textContent = 'Login';
            btn.className = 'auth-btn';
            btn.onclick = () => login();
            elements.userInput.disabled = true;
            elements.sendBtn.disabled = true;
        }
    } else {
        btn.textContent = '🌐 Anonymous';
        btn.className = 'auth-btn';
        btn.disabled = true;
        elements.userInput.disabled = false;
        elements.sendBtn.disabled = false;
    }
}

// ─── Conversation Management ──────────────────────────────────────────────

function createConversation(title) {
    const conv = {
        id: generateId(),
        title: title || 'New Chat',
        messages: [],
        createdAt: Date.now(),
        updatedAt: Date.now(),
    };
    state.conversations.unshift(conv);
    state.currentConversationId = conv.id;
    state.messages = [];
    state.threadId = null;
    renderConversations();
    renderMessages();
    elements.chatTitle.textContent = conv.title;
    elements.userInput.focus();
    saveConversations();
    return conv;
}

function switchConversation(id) {
    const conv = state.conversations.find((c) => c.id === id);
    if (!conv) return;
    state.currentConversationId = id;
    state.messages = conv.messages || [];
    state.threadId = conv.threadId || null;
    elements.chatTitle.textContent = conv.title || 'New Chat';
    renderConversations();
    renderMessages();
    elements.userInput.focus();
}

function deleteConversation(id) {
    if (!confirm('Delete this conversation?')) return;
    state.conversations = state.conversations.filter((c) => c.id !== id);
    if (state.currentConversationId === id) {
        if (state.conversations.length > 0) {
            switchConversation(state.conversations[0].id);
        } else {
            createConversation();
        }
    }
    renderConversations();
    saveConversations();
}

function saveConversations() {
    try {
        localStorage.setItem('nettrades_conversations', JSON.stringify(state.conversations));
    } catch (e) {
        // Ignore
    }
}

function loadConversations() {
    try {
        const data = localStorage.getItem('nettrades_conversations');
        if (data) {
            state.conversations = JSON.parse(data);
            if (state.conversations.length > 0) {
                switchConversation(state.conversations[0].id);
                return;
            }
        }
    } catch (e) {
        // Ignore
    }
    createConversation();
}

// ─── API Calls ──────────────────────────────────────────────────────────────

async function sendMessage() {
    const text = elements.userInput.value.trim();
    if (!text || state.isProcessing) return;

    // Add user message
    state.messages.push({ role: 'user', content: text });
    renderMessages();
    elements.userInput.value = '';
    elements.userInput.style.height = 'auto';

    state.isProcessing = true;
    elements.sendBtn.disabled = true;
    elements.userInput.disabled = true;

    // Show typing indicator
    showTypingIndicator();

    try {
        const response = await fetch(`${API_BASE_URL}/api/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: text,
                thread_id: state.threadId,
            }),
        });

        hideTypingIndicator();

        if (!response.ok) {
            if (response.status === 401) {
                throw new Error('Authentication required. Please log in.');
            }
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        const data = await response.json();
        const reply = data.response || data.answer || data.message || 'No response content.';

        if (data.thread_id) {
            state.threadId = data.thread_id;
        }

        // Add assistant message
        state.messages.push({ role: 'assistant', content: reply });
        renderMessages();

        // Update conversation in list
        const conv = state.conversations.find((c) => c.id === state.currentConversationId);
        if (conv) {
            conv.messages = state.messages;
            conv.threadId = state.threadId;
            if (conv.title === 'New Chat' && text.length > 0) {
                conv.title = text.length > 30 ? text.substring(0, 30) + '...' : text;
                elements.chatTitle.textContent = conv.title;
            }
            conv.updatedAt = Date.now();
            renderConversations();
            saveConversations();
        }

        updateStatus('online', 'Online');

    } catch (error) {
        hideTypingIndicator();
        console.error('Error:', error);
        state.messages.push({
            role: 'assistant',
            content: `❌ Error: ${error.message}`,
            isError: true,
        });
        renderMessages();
        updateStatus('offline', 'Error');
    } finally {
        state.isProcessing = false;
        elements.sendBtn.disabled = false;
        elements.userInput.disabled = false;
        elements.userInput.focus();
        // Auto-resize textarea
        elements.userInput.style.height = 'auto';
    }
}

// ─── Auth Functions ──────────────────────────────────────────────────────────

async function login() {
    if (!state.authEnabled) return;
    window.location.href = `${API_BASE_URL}/api/auth/login`;
}

async function logout() {
    if (!state.authEnabled) return;
    window.location.href = `${API_BASE_URL}/api/auth/logout`;
}

async function checkAuth() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/auth/session`);
        if (response.ok) {
            const data = await response.json();
            state.isAuthenticated = data.authenticated || false;
            state.authEnabled = data.auth_enabled || false;
            state.user = data.user || null;
        }
    } catch (e) {
        // Ignore
    }
    updateAuthUI();
}

// ─── Backend Health Check ────────────────────────────────────────────────────

async function checkBackendHealth() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/health`);
        if (response.ok) {
            const data = await response.json();
            if (data.status === 'ok') {
                updateStatus('online', 'Online');
                return;
            }
        }
        updateStatus('offline', 'Offline');
    } catch (e) {
        updateStatus('offline', 'Offline');
    }
}

// ─── Event Handlers ──────────────────────────────────────────────────────────

// Auto-resize textarea
elements.userInput.addEventListener('input', () => {
    elements.userInput.style.height = 'auto';
    elements.userInput.style.height = elements.userInput.scrollHeight + 'px';
});

elements.userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

elements.sendBtn.addEventListener('click', sendMessage);

elements.newChatBtn.addEventListener('click', () => {
    createConversation();
    if (window.innerWidth <= 768) {
        closeSidebar();
    }
});

// Sidebar toggle (mobile)
elements.sidebarToggle.addEventListener('click', toggleSidebar);
elements.mobileMenuBtn.addEventListener('click', toggleSidebar);

// Close sidebar on overlay click
document.addEventListener('click', (e) => {
    if (window.innerWidth <= 768) {
        const overlay = document.querySelector('.sidebar-overlay');
        if (overlay && overlay.classList.contains('active') && !e.target.closest('.sidebar')) {
            closeSidebar();
        }
    }
});

function toggleSidebar() {
    const sidebar = elements.sidebar;
    sidebar.classList.toggle('open');
    let overlay = document.querySelector('.sidebar-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay';
        document.body.appendChild(overlay);
        overlay.addEventListener('click', closeSidebar);
    }
    overlay.classList.toggle('active');
}

function closeSidebar() {
    elements.sidebar.classList.remove('open');
    const overlay = document.querySelector('.sidebar-overlay');
    if (overlay) overlay.classList.remove('active');
}

// ─── Init ────────────────────────────────────────────────────────────────────

async function init() {
    // Set model name
    elements.chatModel.textContent = state.modelName;

    // Load conversations from localStorage
    loadConversations();

    // Check auth status
    await checkAuth();

    // Check backend health
    await checkBackendHealth();
    setInterval(checkBackendHealth, 30000);

    // Focus input
    elements.userInput.focus();

    // Update status
    updateStatus('connecting', 'Connecting...');

    console.log('🧠 NETTRADES AI Router initialized');
}

// Start the app
init();