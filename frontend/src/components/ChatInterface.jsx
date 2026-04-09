/**
 * ChatInterface Component
 *
 * The main Q&A chat panel.
 *
 * WHAT IT DOES:
 *   - Renders the conversation history (list of MessageBubble components)
 *   - Handles user input (textarea, send on Enter)
 *   - Calls POST /api/chat with the question + selected repo
 *   - Shows typing indicator while waiting for LLaMA 3 response
 *   - Displays quick-start question buttons when chat is empty
 *   - Auto-scrolls to bottom on new messages
 *
 * SESSION ID:
 *   Each browser session gets a unique ID stored in sessionStorage.
 *   This keeps conversation memory separate per tab / per user.
 *
 * TEXTAREA AUTO-RESIZE:
 *   The input grows to fit the user's message (up to max-height: 140px
 *   set in CSS), then shows a scrollbar. This is standard chat UX.
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import axios from 'axios'
import MessageBubble from './MessageBubble'
import { Send, Bot, AlertCircle } from 'lucide-react'

// Using global axios.defaults.baseURL configured in AuthContext

// We will track sessionId in state so it properly links to backend history


// Suggested questions shown when chat is empty
const QUICK_QUESTIONS = [
  '🏗️  Explain the overall architecture of this codebase',
  '🔐  How does authentication/authorization work?',
  '🗺️  What are the main entry points of this application?',
  '📦  What are the key classes/modules and what do they do?',
  '🔄  Explain the data flow for a typical request',
]

export default function ChatInterface({ selectedRepo }) {
  const [messages, setMessages]   = useState([])
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState('')
  const [sessionId, setSessionId] = useState(null)
  const messagesEndRef             = useRef(null)
  const textareaRef                = useRef(null)

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Auto-resize textarea
  const handleInputChange = (e) => {
    setInput(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = e.target.scrollHeight + 'px'
  }

  // Fetch history when user changes repo
  useEffect(() => {
    setMessages([])
    setError('')
    setSessionId(null)
    if (!selectedRepo) return

    const fetchHistory = async () => {
      setLoading(true)
      try {
        const res = await axios.get(`/api/chat/history/${selectedRepo}`)
        const history = res.data.history
        if (history && history.length > 0) {
          // Resume the most recent session
          const latestSession = history[0]
          setSessionId(latestSession.session_id)
          setMessages(latestSession.messages.map(m => ({
            role: m.role === 'user' ? 'user' : 'bot',
            content: m.content,
            citations: m.citations || [],
            timestamp: latestSession.created_at
          })))
        }
      } catch (err) {
        console.error("Failed to load history", err)
      } finally {
        setLoading(false)
      }
    }
    fetchHistory()
  }, [selectedRepo])

  const sendMessage = useCallback(async (question) => {
    const q = (question || input).trim()
    if (!q || loading) return
    if (!selectedRepo) { setError('Select a repository first.'); return }

    // Add user message to UI immediately (optimistic update)
    const userMsg = { role: 'user', content: q, timestamp: Date.now() }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setError('')
    setLoading(true)

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }

    try {
      const res = await axios.post("/api/chat", {
        question: q,
        repo_name: selectedRepo,
        session_id: sessionId,
      })

      if (!sessionId && res.data.session_id) {
        setSessionId(res.data.session_id)
      }

      const botMsg = {
        role: 'bot',
        content: res.data.answer,
        citations: res.data.citations || [],
        model: res.data.model,
        timestamp: Date.now(),
      }
      setMessages(prev => [...prev, botMsg])
    } catch (err) {
      const errText = err.response?.data?.detail || 'Something went wrong. Check that the backend is running and your GROQ_API_KEY is set.'
      setMessages(prev => [...prev, {
        role: 'bot',
        content: `❌ Error: ${errText}`,
        citations: [],
        timestamp: Date.now(),
      }])
    } finally {
      setLoading(false)
    }
  }, [input, loading, selectedRepo])

  // Send on Enter (Shift+Enter = new line)
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="main">
      {/* ── Header ── */}
      <div className="main-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {selectedRepo ? (
            <div className="repo-selected-badge">
              <GitBranchIcon size={14} />
              Asking about: <strong style={{ color: '#fff' }}>{selectedRepo}</strong>
            </div>
          ) : (
            <span style={{ fontSize: 14, color: 'var(--text-muted)' }}>
              ← Select a repository to start asking questions
            </span>
          )}
        </div>
        <div className="model-badge">🦙 Meta LLaMA 3 · Groq</div>
      </div>

      {/* ── Messages ── */}
      <div id="messages-container" className="messages-container">
        {messages.length === 0 && !loading ? (
          /* Empty state — shown before any message is sent */
          <div className="empty-state">
            <div className="empty-icon">🧠</div>
            <h1 className="empty-title">CodeMind</h1>
            <p className="empty-subtitle">
              {selectedRepo
                ? `Ask anything about the <strong>${selectedRepo}</strong> codebase. LLaMA 3 will answer with exact file paths and code citations.`
                : 'Index a GitHub repository from the sidebar, then ask questions about its code.'}
            </p>

            {selectedRepo && (
              <div className="quick-questions">
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>
                  Try these questions:
                </div>
                {QUICK_QUESTIONS.map((q, i) => (
                  <button
                    key={i}
                    id={`quick-q-${i}`}
                    className="quick-q-btn"
                    onClick={() => sendMessage(q.slice(3).trim())} // strip emoji prefix
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          /* Message list */
          messages.map((msg, i) => (
            <MessageBubble key={i} message={msg} />
          ))
        )}

        {/* Typing indicator — shown while LLaMA 3 is generating */}
        {loading && (
          <div className="message bot">
            <div className="avatar bot">🤖</div>
            <div className="message-content">
              <div className="message-bubble">
                <div className="typing-indicator">
                  <div className="typing-dot" />
                  <div className="typing-dot" />
                  <div className="typing-dot" />
                </div>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* ── Error notice ── */}
      {error && (
        <div style={{
          padding: '8px 24px',
          background: 'rgba(239, 68, 68, 0.1)',
          borderTop: '1px solid rgba(239, 68, 68, 0.3)',
          fontSize: 13, color: 'var(--error)',
          display: 'flex', alignItems: 'center', gap: 6,
        }}>
          <AlertCircle size={14} /> {error}
        </div>
      )}

      {/* ── Input area ── */}
      <div className="input-area">
        <div className="input-bar">
          <textarea
            id="chat-input"
            ref={textareaRef}
            className="chat-input"
            placeholder={
              selectedRepo
                ? `Ask about ${selectedRepo}… (Enter to send, Shift+Enter for new line)`
                : 'Select a repository first…'
            }
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={loading || !selectedRepo}
            rows={1}
          />
          <button
            id="send-btn"
            className="send-btn"
            onClick={() => sendMessage()}
            disabled={loading || !input.trim() || !selectedRepo}
            title="Send message"
          >
            <Send size={16} />
          </button>
        </div>
        <div className="input-hint">
          Powered by Meta LLaMA 3 via Groq · LangChain RAG · ChromaDB
        </div>
      </div>
    </div>
  )
}

// Inline mini icon component (avoids another import)
function GitBranchIcon({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="6" y1="3" x2="6" y2="15"></line>
      <circle cx="18" cy="6" r="3"></circle>
      <circle cx="6" cy="18" r="3"></circle>
      <path d="M18 9a9 9 0 0 1-9 9"></path>
    </svg>
  )
}
