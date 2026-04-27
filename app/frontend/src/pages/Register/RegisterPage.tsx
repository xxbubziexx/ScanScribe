import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { auth } from '@/lib/api'
import { errorMessage } from '@/types/api'

export function RegisterPage() {
  const { token } = useAuth()
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (token) return <Navigate to="/" replace />

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await auth.register(username, email, password)
      navigate('/login', { state: { registered: true } })
    } catch (err) {
      setError(errorMessage(err, 'Registration failed'))
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
          <div className="mb-8 text-center">
            <h1 className="text-2xl font-bold tracking-tight text-white">ScanScribe</h1>
            <p className="mt-1 text-sm text-gray-500">Create your account</p>
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
              <label htmlFor="email" className="ss-form-label">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
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
                autoComplete="new-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="ss-input"
              />
            </div>

            {error && <p className="ss-form-error">{error}</p>}

            <button type="submit" disabled={loading} className="ss-btn-auth">
              {loading ? 'Creating account…' : 'Create account'}
            </button>
          </form>

          <p className="ss-auth-hint">
            Already have an account? <Link to="/login" className="ss-link-auth">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
