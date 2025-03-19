// Store conversation history
let conversation = [];

// DOM elements
const messageForm = document.getElementById('message-form');
const messageInput = document.getElementById('message-input');
const messagesContainer = document.getElementById('messages');

// Initialize event listeners
messageForm.addEventListener('submit', handleSubmit);

/**
 * Handle form submission
 * @param {Event} e - The submit event
 */
async function handleSubmit(e) {
    e.preventDefault();
    
    const message = messageInput.value.trim();
    if (!message) return;
    
    // Add user message to UI
    addMessageToUI('user', message);
    messageInput.value = '';
    
    // Show loading indicator
    const loadingId = showLoading();
    
    try {
        // Send message to API
        const response = await fetch('/assistant', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: message,
                conversation: conversation
            })
        });
        
        if (!response.ok) {
            throw new Error(`API request failed with status ${response.status}`);
        }
        
        const data = await response.json();
        
        // Update conversation history
        conversation = data.conversation;
        
        // Remove loading indicator
        hideLoading(loadingId);
        
        // Add assistant response to UI
        addMessageToUI('assistant', data.response);
        
    } catch (error) {
        console.error('Error:', error);
        hideLoading(loadingId);
        addMessageToUI('system', `Error: ${error.message || 'Failed to get response from assistant'}`);
    }
}

/**
 * Add a message to the UI
 * @param {string} role - The role of the message sender (user, assistant, system)
 * @param {string} content - The message content
 */
function addMessageToUI(role, content) {
    const messageElement = document.createElement('div');
    messageElement.classList.add('message', role);
    
    // Format the timestamp
    const timestamp = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    
    // Format the content (handle markdown-like formatting)
    const formattedContent = formatMessageContent(content);
    
    messageElement.innerHTML = `
        <div class="message-content">${formattedContent}</div>
        <div class="message-timestamp">${timestamp}</div>
    `;
    
    messagesContainer.appendChild(messageElement);
    scrollToBottom();
}

/**
 * Format message content with basic markdown-like formatting
 * @param {string} content - The raw message content
 * @returns {string} - Formatted HTML content
 */
function formatMessageContent(content) {
    // Handle code blocks (```code```)
    content = content.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
    
    // Handle inline code (`code`)
    content = content.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Handle line breaks
    content = content.replace(/\n/g, '<br>');
    
    return content;
}

/**
 * Show loading indicator
 * @returns {number} - The ID of the loading indicator
 */
function showLoading() {
    const id = Date.now();
    const loadingElement = document.createElement('div');
    loadingElement.classList.add('message', 'assistant', 'loading');
    loadingElement.id = `loading-${id}`;
    loadingElement.innerHTML = `
        <div class="message-content">
            <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;
    
    messagesContainer.appendChild(loadingElement);
    scrollToBottom();
    return id;
}

/**
 * Hide loading indicator
 * @param {number} id - The ID of the loading indicator to hide
 */
function hideLoading(id) {
    const loadingElement = document.getElementById(`loading-${id}`);
    if (loadingElement) {
        loadingElement.remove();
    }
}

/**
 * Scroll to the bottom of the messages container
 */
function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

/**
 * Clear the conversation history
 */
function clearConversation() {
    conversation = [];
    while (messagesContainer.firstChild) {
        messagesContainer.removeChild(messagesContainer.firstChild);
    }
    addMessageToUI('system', 'Conversation cleared. How can I help you today?');
}

// Add a clear button to the UI
function addClearButton() {
    const header = document.querySelector('header');
    const clearButton = document.createElement('button');
    clearButton.textContent = 'Clear Chat';
    clearButton.classList.add('clear-button');
    clearButton.style.position = 'absolute';
    clearButton.style.right = '15px';
    clearButton.style.top = '15px';
    clearButton.style.padding = '5px 10px';
    clearButton.style.backgroundColor = 'rgba(255, 255, 255, 0.2)';
    clearButton.style.border = 'none';
    clearButton.style.borderRadius = '4px';
    clearButton.style.color = 'white';
    clearButton.style.cursor = 'pointer';
    clearButton.addEventListener('click', clearConversation);
    header.style.position = 'relative';
    header.appendChild(clearButton);
}

// Initialize the UI
document.addEventListener('DOMContentLoaded', function() {
    addClearButton();
});
