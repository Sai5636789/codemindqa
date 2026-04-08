import { useState, useContext } from 'react';
import { AuthContext } from '../context/AuthContext';
import { Zap } from 'lucide-react';

export default function Register({ setView }) {
  const { register } = useContext(AuthContext);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username || !password) return;
    setError('');
    setLoading(true);
    try {
      await register(username, email, password);
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="logo auth-logo-center">
          <div className="logo-icon" style={{ background: 'var(--accent)' }}>🚀</div>
          <span className="logo-text">CodeMind</span>
        </div>
        <h2 className="auth-title">Create Account</h2>
        <p className="auth-subtitle">Join CodeMind to start talking to your codebase.</p>

        <form onSubmit={handleSubmit} className="auth-form">
          <label className="input-label">Username</label>
          <input
            type="text"
            className="input-field"
            value={username}
            onChange={e => setUsername(e.target.value)}
            disabled={loading}
          />
          
          <label className="input-label" style={{ marginTop: '12px' }}>Email (Optional)</label>
          <input
            type="email"
            className="input-field"
            value={email}
            onChange={e => setEmail(e.target.value)}
            disabled={loading}
          />

          <label className="input-label" style={{ marginTop: '12px' }}>Password</label>
          <input
            type="password"
            className="input-field"
            value={password}
            onChange={e => setPassword(e.target.value)}
            disabled={loading}
          />

          {error && <div className="auth-error">⚠ {error}</div>}

          <button type="submit" className="btn-primary auth-submit" disabled={loading || !username || !password}>
            {loading ? 'Creating account...' : <><Zap size={14} /> Register</>}
          </button>
        </form>

        <div className="auth-footer">
          Already have an account? <span className="auth-link" onClick={() => setView('login')}>Login here</span>
        </div>
      </div>
    </div>
  );
}
