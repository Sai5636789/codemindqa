/**
 * MessageBubble Component
 *
 * Renders a single chat message (either from user or bot).
 *
 * KEY FEATURE: Bot messages render as full Markdown.
 * LLaMA 3 responds with markdown (bold, code fences, lists, headers).
 * We use react-markdown with remark-gfm (GitHub Flavored Markdown)
 * so that code blocks automatically become <CodeBlock /> with syntax highlighting.
 *
 * WHY react-markdown instead of dangerouslySetInnerHTML:
 * - Safe (no XSS risk from LLM output)
 * - Code blocks get routed to our custom CodeBlock component
 * - Proper rendering of tables, checkboxes, strikethrough (GFM)
 */

import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import CodeBlock from './CodeBlock'
import { ChevronDown, ChevronUp, FileCode } from 'lucide-react'

export default function MessageBubble({ message }) {
  const [citationsOpen, setCitationsOpen] = useState(false)
  const isBot = message.role === 'bot'

  return (
    <div className={`message ${message.role}`}>
      {/* Avatar */}
      <div className={`avatar ${message.role}`}>
        {isBot ? '🤖' : '👤'}
      </div>

      <div className="message-content">
        {/* Bubble */}
        <div className={`message-bubble`}>
          {isBot ? (
            // Bot messages: render as Markdown with custom code block renderer
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                // Override the default <code> renderer
                code({ node, inline, className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className || '')
                  const code = String(children).replace(/\n$/, '')

                  if (!inline && (match || code.includes('\n'))) {
                    // Multi-line code block → use our CodeBlock with syntax highlighting
                    return (
                      <CodeBlock
                        code={code}
                        language={match ? match[1] : 'text'}
                      />
                    )
                  }
                  // Inline code → plain styled span
                  return <code className={className} {...props}>{children}</code>
                },
              }}
            >
              {message.content}
            </ReactMarkdown>
          ) : (
            // User messages: plain text (simpler, no XSS surface)
            <span style={{ whiteSpace: 'pre-wrap' }}>{message.content}</span>
          )}
        </div>

        {/* Citations panel (only for bot messages with citations) */}
        {isBot && message.citations && message.citations.length > 0 && (
          <div className="citations-panel">
            <button
              className="citations-toggle"
              onClick={() => setCitationsOpen(o => !o)}
            >
              <FileCode size={12} />
              {message.citations.length} source{message.citations.length > 1 ? 's' : ''} retrieved
              {citationsOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>

            {citationsOpen && (
              <div className="citations-list">
                {message.citations.map((cite, i) => (
                  <div className="citation-item" key={i}>
                    <span className="citation-file">📄 {cite.file}</span>
                    {cite.start_line && (
                      <span className="citation-lines">
                        L{cite.start_line}–{cite.end_line}
                      </span>
                    )}
                    {cite.function && (
                      <span className="citation-fn">{cite.function}()</span>
                    )}
                    <span style={{ marginLeft: 'auto', color: 'var(--accent-3)', fontSize: 10 }}>
                      {(cite.score * 100).toFixed(0)}% match
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Timestamp */}
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 5, paddingLeft: 4 }}>
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  )
}
