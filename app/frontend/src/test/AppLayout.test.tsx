import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AppLayout } from '../components/layout/AppLayout'
import * as AuthContextModule from '../context/AuthContext'

describe('AppLayout full-bleed and standard main container behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: {
        id: 1,
        username: 'operator',
        email: 'operator@scanscribe.local',
        is_active: true,
        is_admin: false,
        created_at: '2026-01-01T00:00:00Z',
      },
      token: 'fake-token',
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    })
  })

  function renderLayoutAt(path: string) {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<div data-testid="command-center-child" />} />
            <Route path="/intel" element={<div data-testid="intel-child" />} />
            <Route path="/insights" element={<div data-testid="insights-child" />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
  }

  it('applies ss-app-main--fullbleed on the command center route (/)', () => {
    const { container } = renderLayoutAt('/')
    const main = container.querySelector('main')
    expect(main).toHaveClass('ss-app-main')
    expect(main).toHaveClass('ss-app-main--fullbleed')
  })

  it('applies ss-app-main--fullbleed on the intel route (/intel)', () => {
    const { container } = renderLayoutAt('/intel')
    const main = container.querySelector('main')
    expect(main).toHaveClass('ss-app-main')
    expect(main).toHaveClass('ss-app-main--fullbleed')
  })

  it('does not apply fullbleed on standard scrollable pages (/insights)', () => {
    const { container } = renderLayoutAt('/insights')
    const main = container.querySelector('main')
    expect(main).toHaveClass('ss-app-main')
    expect(main).not.toHaveClass('ss-app-main--fullbleed')
  })
})
