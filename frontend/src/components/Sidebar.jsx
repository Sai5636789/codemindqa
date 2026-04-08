/**
 * Sidebar Component
 *
 * Handles:
 *   1. IndexForm — enter GitHub URL + repo name → call POST /api/index
 *   2. RepoList  — shows all indexed repos, click to select for chatting
 *   3. Real-time progress polling — polls /api/repos every 3 seconds while
 *      a repo is in "running" state to show live progress
 *
 * WHY POLLING instead of WebSockets:
 *   Simpler implementation, FastAPI native support, and indexing only takes
 *   2-5 minutes — occasional polling is fine for this use case.
 */

import { useState, useEffect, useCallback, useContext } from 'react'
import axios from 'axios'
import { Trash2, RefreshCw, GitBranch, Zap, LogOut } from 'lucide-react'
import { AuthContext } from '../context/AuthContext'

const API_BASE = '/api'

export default function Sidebar({ selectedRepo, onSelectRepo }) {
  const [repos, setRepos]       = useState([])
  const [repoUrl, setRepoUrl]   = useState('')
  const [repoName, setRepoName] = useState('')
  const [githubPat, setGithubPat] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [indexing, setIndexing] = useState(false)
  const [error, setError]       = useState('')
  const { user, logout }        = useContext(AuthContext)

  // Auto-fill repo name from URL
  const handleUrlChange = (val) => {
    setRepoUrl(val)
    // Extract last path segment as default name (e.g. "flask" from ".../pallets/flask")
    const parts = val.trim().replace(/\/$/, '').split('/')
    if (parts.length >= 1) {
      setRepoName(parts[parts.length - 1].toLowerCase().replace(/[^a-z0-9_-]/g, '_'))
    }
  }

  // Fetch repo list from backend
  const fetchRepos = useCallback(async () => {
    try {
      const res = await axios.get(`${API_BASE}/repos`)
      setRepos(res.data.repos || [])
    } catch {
      // Silently fail during polling
    }
  }, [])

  // Poll every 3s when any repo is still running
  useEffect(() => {
    fetchRepos()
    const hasRunning = repos.some(r => r.status === 'running' || r.status.startsWith('parsing') || r.status === 'cloning' || r.status === 'embedding')
    const interval = setInterval(fetchRepos, hasRunning ? 3000 : 8000)
    return () => clearInterval(interval)
  }, [fetchRepos, repos.length])

  const handleIndex = async (e) => {
    e.preventDefault()
    if (!repoUrl.trim() || !repoName.trim()) return
    setError('')
    setIndexing(true)
    try {
      await axios.post(`${API_BASE}/repos/index`, {
        repo_url: repoUrl.trim(),
        repo_name: repoName.trim(),
        github_pat: githubPat.trim() || null,
      })
      setRepoUrl('')
      setRepoName('')
      fetchRepos()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start indexing')
    } finally {
      setIndexing(false)
    }
  }

  const handleDelete = async (e, name) => {
    e.stopPropagation()
    if (!confirm(`Delete '${name}' and all its indexed data?`)) return
    await axios.delete(`${API_BASE}/repos/${name}`)
    if (selectedRepo === name) onSelectRepo(null)
    fetchRepos()
  }

  return (
    <aside className="sidebar">
      {/* ── Logo ── */}
      <div className="sidebar-header" style={{ paddingBottom: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div className="logo">
            <div className="logo-icon">🧠</div>
            <span className="logo-text">CodeMind</span>
          </div>
          {user && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{user.username}</span>
              <button 
                onClick={logout}
                title="Logout"
                className="btn-ghost"
                style={{ padding: '4px', display: 'flex', alignItems: 'center', color: 'var(--error)' }}
              >
                <LogOut size={14} />
              </button>
            </div>
          )}
        </div>

        {/* ── Index Form ── */}
        <form className="index-form" onSubmit={handleIndex}>
          <label className="input-label">GitHub Repository URL</label>
          <input
            id="repo-url-input"
            className="input-field"
            placeholder="https://github.com/user/repo"
            value={repoUrl}
            onChange={e => handleUrlChange(e.target.value)}
          />
          <label className="input-label">Repo Name (short ID)</label>
          <input
            id="repo-name-input"
            className="input-field"
            placeholder="e.g. flask"
            value={repoName}
            onChange={e => setRepoName(e.target.value)}
          />
          <div style={{ marginTop: 8 }}>
            <span 
              onClick={() => setShowAdvanced(!showAdvanced)} 
              style={{ fontSize: 11, color: 'var(--accent)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}
            >
              {showAdvanced ? '▼' : '▶'} Advanced Settings
            </span>
            {showAdvanced && (
              <div style={{ marginTop: 8, padding: 8, background: 'rgba(255,255,255,0.03)', borderRadius: 6 }}>
                <label className="input-label" style={{ fontSize: 10 }}>GitHub PAT (For Private Repos)</label>
                <input
                  className="input-field"
                  placeholder="ghp_xxxxxxxxxxxx"
                  value={githubPat}
                  onChange={e => setGithubPat(e.target.value)}
                  type="password"
                  style={{ padding: '6px 10px', fontSize: 12 }}
                />
              </div>
            )}
          </div>
          {error && (
            <div style={{ fontSize: 12, color: 'var(--error)', marginTop: 2 }}>
              ⚠ {error}
            </div>
          )}
          <button
            id="index-btn"
            type="submit"
            className="btn-primary"
            disabled={indexing || !repoUrl.trim()}
          >
            {indexing ? (
              <><RefreshCw size={13} style={{ animation: 'spin 1s linear infinite' }} /> Indexing…</>
            ) : (
              <><Zap size={13} /> Index Repository</>
            )}
          </button>
        </form>
      </div>

      {/* ── Repo List ── */}
      <div className="repos-section">
        <div className="section-title">
          <GitBranch size={11} style={{ display:'inline', marginRight:4 }} />
          Indexed Repos ({repos.length})
        </div>

        {repos.length === 0 && (
          <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '8px 4px', lineHeight: 1.6 }}>
            No repos indexed yet. Enter a GitHub URL above to get started.
          </div>
        )}

        {repos.map(repo => {
          const isActive = selectedRepo === repo.name
          const isRunning = !['done', 'error'].includes(repo.status)
          return (
            <div
              key={repo.name}
              id={`repo-card-${repo.name}`}
              className={`repo-card ${isActive ? 'active' : ''}`}
              onClick={() => !isRunning && onSelectRepo(repo.name)}
              style={{ cursor: isRunning ? 'default' : 'pointer' }}
            >
              <div className="repo-name">
                <span className="status-dot" style={{
                  background: repo.status === 'done'
                    ? 'var(--success)'
                    : repo.status === 'error'
                    ? 'var(--error)'
                    : 'var(--warning)',
                  boxShadow: isRunning ? '0 0 6px var(--warning)' : undefined,
                  animation: isRunning ? 'pulse 1.2s infinite' : undefined,
                  display: 'inline-block',
                  width: 6, height: 6, borderRadius: '50%', marginRight: 7,
                }} />
                {repo.name}
              </div>
              <div className="repo-meta">
                {isRunning ? (
                  <>
                    <span style={{ color: 'var(--warning)' }}>{repo.status}</span>
                    {repo.files_processed > 0 && (
                      <span>· {repo.files_processed} files</span>
                    )}
                  </>
                ) : repo.status === 'error' ? (
                  <span style={{ color: 'var(--error)' }}>Error: {repo.error}</span>
                ) : (
                  <span>{repo.chunk_count?.toLocaleString()} chunks indexed</span>
                )}
              </div>

              {/* Progress bar during indexing */}
              {isRunning && (
                <div className="indexer-progress-bar">
                  <div className="indexer-progress-fill" style={{ width: '60%' }} />
                </div>
              )}

              {/* Delete / Re-Index buttons */}
              {!isRunning && (
                <div style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', display: 'flex', gap: '4px' }}>
                  <button
                    className="repo-delete btn-ghost"
                    onClick={(e) => {
                      e.stopPropagation();
                      setRepoUrl(repo.repo_url);
                      setRepoName(repo.name);
                      if (repo.is_private) setShowAdvanced(true);
                      alert("Form filled! Add your PAT if needed, and click 'Index Repository' to fetch the latest commits.");
                    }}
                    title="Re-Index (Incremental Update)"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    <RefreshCw size={12} />
                  </button>
                  <button
                    id={`delete-repo-${repo.name}`}
                    className="repo-delete btn-ghost"
                    onClick={e => handleDelete(e, repo.name)}
                    title="Delete repository"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Footer */}
      <div style={{
        padding: '12px 16px',
        borderTop: '1px solid var(--border)',
        fontSize: 11, color: 'var(--text-muted)',
        textAlign: 'center',
      }}>
        Powered by Meta LLaMA 3 + LangChain
      </div>
    </aside>
  )
}
