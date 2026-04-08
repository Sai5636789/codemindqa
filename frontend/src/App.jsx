/**
 * App.jsx — Root Component
 *
 * Composes the full page layout:
 *   <Sidebar /> on the left   → repo management
 *   <ChatInterface /> on right → the Q&A chat
 *
 * State here is just `selectedRepo` — which repo the user has clicked.
 * This is lifted up so both components can read/write it.
 */

import { useState, useContext } from 'react'
import Sidebar from './components/Sidebar'
import ChatInterface from './components/ChatInterface'
import { AuthContext } from './context/AuthContext'
import Login from './pages/Login'
import Register from './pages/Register'

export default function App() {
  const [selectedRepo, setSelectedRepo] = useState(null)
  const { user, loading } = useContext(AuthContext)
  const [authView, setAuthView] = useState('login')

  if (loading) {
    return <div style={{height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text)'}}>Loading CodeMind...</div>
  }

  if (!user) {
    return authView === 'login' ? <Login setView={setAuthView} /> : <Register setView={setAuthView} />
  }

  return (
    <div className="app">
      {/* Left sidebar: repo indexing + selection */}
      <Sidebar
        selectedRepo={selectedRepo}
        onSelectRepo={setSelectedRepo}
      />

      {/* Right main panel: chat Q&A */}
      <ChatInterface
        selectedRepo={selectedRepo}
      />
    </div>
  )
}
