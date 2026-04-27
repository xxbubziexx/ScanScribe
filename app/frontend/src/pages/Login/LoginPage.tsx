import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { errorMessage } from '@/types/api'

export function LoginPage() {
  const { token, login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (token) return <Navigate to="/" replace />

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
    } catch (err) {
      setError(errorMessage(err, 'Login failed'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="ss-auth-page">
      <div
        className="ss-auth-grid"
        style={{
          backgroundImage:
            'linear-gradient(#fff 1px,transparent 1px),linear-gradient(90deg,#fff 1px,transparent 1px)',
          backgroundSize: '40px 40px',
        }}
      />

      <div className="relative w-full max-w-sm">
        <div className="ss-auth-glow" />

        <div className="ss-auth-card">
          {/* Brand */}
          <div className="mb-8 text-center">
            <h1 className="text-2xl font-bold tracking-tight text-white">ScanScribe</h1>
            <p className="mt-1 text-sm text-gray-500">Audio Transcription System</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="username" className="ss-form-label">
                Username
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                autoFocus
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="ss-input"
              />
            </div>

            <div>
              <label htmlFor="password" className="ss-form-label">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="ss-input"
              />
            </div>

            {error && <p className="ss-form-error">{error}</p>}

            <button type="submit" disabled={loading} className="ss-btn-auth">
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <p className="ss-auth-hint">
            Don&apos;t have an account? <Link to="/register" className="ss-link-auth">Register</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
