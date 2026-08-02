// ============================================================================
// NETTRADES AI Router – Chat Application (Vanilla JS)
// ============================================================================

// App state
const state = {
    messages: [],
    isAuthenticated: false,
    authEnabled: false,
    user: null,
    isProcessing: false,
    threadId: null,
};

// DOM references
const chatContainer = document.getElementById('chat');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const statusEl = document.getElementById('status');
const authBtn = document.getElementById('auth-btn');
const authStatus = document.getElementById('auth-status');

// ============================================================================
// Auth State Management
// ============================================================================

// Try to load auth state from the server
const AUTH_STATE = window.__AUTH_STATE__ || { authenticated: false, auth_enabled: false };

state.isAuthenticated = AUTH_STATE.authenticated;
state.authEnabled = AUTH_STATE.auth_enabled;
state.user = AUTH_STATE.user || null;

function updateAuthUI() {
    if (state.authEnabled) {
        if (state.isAuthenticated && state.user) {
            authStatus.textContent = `👤 ${state.user.name || state.user.email}`;
            authStatus.className = 'status-badge authenticated';
            authBtn.textContent = 'Logout';
            authBtn.onclick = () => logout();
            userInput.disabled = false;
            sendBtn.disabled = false;
        } else {
            authStatus.textContent = '🔒 Not authenticated';
            authStatus.className = 'status-badge unauthenticated';
            authBtn.textContent = 'Login';
            authBtn.onclick = () => login();
            userInput.disabled = true;
            sendBtn.disabled = true;
        }
    } else {
        authStatus.textContent = '🌐 Anonymous mode';
        authStatus.className = 'status-badge anonymous';
        authBtn.textContent = 'Login (disabled)';
        authBtn.disabled = true;
        userInput.disabled = false;
        sendBtn.disabled = false;
    }
}

async function login() {
    if (!state.authEnabled) return;
    window.location.href = `${API_BASE_URL}/api/auth/login`;
}

async function logout() {
    if (!state.authEnabled) return;
    window.location.href = `${API_BASE_URL}/api/auth/logout`;
}

// ============================================================================
// Chat Functions
// ============================================================================

function addMessage(text, sender, isError = false) {
    const div = document.createElement('div');
    div.className = `message ${sender}${isError ? ' error' : ''}`;

    if (sender === 'assistant') {
        const html = marked.parse(text);
        div.innerHTML = html;
        // Highlight code blocks
        div.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightElement(block);
        });
    } else {
        div.textContent = text;
    }

    chatContainer.appendChild(div);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    state.messages.push({ role: sender, content: text });
}

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text || state.isProcessing) return;

    // Disable input
    state.isProcessing = true;
    userInput.disabled = true;
    sendBtn.disabled = true;
    statusEl.textContent = '⏳ Thinking...';

    // Add user message
    addMessage(text, 'user');
    userInput.value = '';

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

        if (!response.ok) {
            if (response.status === 401) {
                throw new Error('Authentication required. Please log in.');
            }
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        const data = await response.json();
        const reply = data.response || data.answer || data.message || 'No response content.';

        // Store thread_id for conversation continuity
        if (data.thread_id) {
            state.threadId = data.thread_id;
        }

        addMessage(reply, 'assistant');

    } catch (error) {
        console.error('Error:', error);
        addMessage(`❌ Error: ${error.message}`, 'error', true);
    } finally {
        state.isProcessing = false;
        userInput.disabled = !state.isAuthenticated && state.authEnabled;
        sendBtn.disabled = false;
        userInput.focus();
        statusEl.textContent = 'Ready';
        // Auto-resize textarea
        userInput.style.height = 'auto';
    }
}

// ============================================================================
// Event Handlers
// ============================================================================

// Auto-resize textarea
userInput.addEventListener('input', () => {
    userInput.style.height = 'auto';
    userInput.style.height = userInput.scrollHeight + 'px';
});

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

sendBtn.addEventListener('click', sendMessage);

// ============================================================================
// Initialize
// ============================================================================

function init() {
    updateAuthUI();

    // Add welcome message
    if (state.isAuthenticated || !state.authEnabled) {
        const greeting = state.user
            ? `👋 Hello, ${state.user.name || state.user.email}!`
            : '👋 Hello! I am the NETTRADES AI Router.';
        addMessage(`${greeting} How can I help you today?`, 'assistant');
        userInput.disabled = false;
        sendBtn.disabled = false;
    } else {
        addMessage('🔒 Please log in to continue.', 'assistant');
    }

    userInput.focus();
}

// Start the app
init();