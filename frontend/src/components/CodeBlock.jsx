/**
 * CodeBlock Component
 *
 * WHY: Code blocks in chat answers need syntax highlighting and a copy button.
 * react-syntax-highlighter uses Prism.js or Highlight.js under the hood —
 * it's the standard in the React ecosystem for this purpose.
 *
 * We detect the language from the markdown code fence (```python, ```js, etc.)
 * and pass it directly to SyntaxHighlighter.
 */

import { useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Copy, Check } from 'lucide-react'

export default function CodeBlock({ code, language = 'text' }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="code-block-wrapper">
      {/* Header: language label + copy button */}
      <div className="code-block-header">
        <span className="code-block-lang">{language || 'code'}</span>
        <button
          className={`copy-btn ${copied ? 'copied' : ''}`}
          onClick={handleCopy}
        >
          {copied ? (
            <><Check size={11} /> Copied!</>
          ) : (
            <><Copy size={11} /> Copy</>
          )}
        </button>
      </div>

      {/* The actual highlighted code */}
      <SyntaxHighlighter
        language={language}
        style={vscDarkPlus}
        customStyle={{
          margin: 0,
          borderRadius: 0,
          background: 'rgba(0,0,0,0.6)',
          fontSize: '12.5px',
          lineHeight: '1.6',
          padding: '14px 16px',
        }}
        showLineNumbers={code.split('\n').length > 5}
        wrapLongLines={false}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  )
}
