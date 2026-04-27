import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from '../App'

function renderApp(path = '/login') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => localStorage.clear())

describe('App routing', () => {
  it('renders the login form on /login', () => {
    renderApp('/login')
    expect(screen.getByRole('heading', { name: /scanscribe/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('redirects unauthenticated users to the login form', () => {
    renderApp('/')
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })
})
