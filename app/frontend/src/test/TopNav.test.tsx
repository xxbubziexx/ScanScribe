import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { TopNav } from '../components/layout/TopNav'
import * as AuthContextModule from '../context/AuthContext'

describe('TopNav mobile navigation drawer', () => {
  const mockLogout = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    document.body.style.overflow = ''
  })

  function renderNav(isAdmin = true) {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: {
        id: 1,
        username: 'admin',
        email: 'admin@scanscribe.local',
        is_active: true,
        is_admin: isAdmin,
        created_at: '2026-01-01T00:00:00Z',
      },
      token: 'fake-token',
      isLoading: false,
      login: vi.fn(),
      logout: mockLogout,
    })

    return render(
      <MemoryRouter initialEntries={['/']}>
        <TopNav />
      </MemoryRouter>,
    )
  }

  it('toggles mobile drawer when clicking the menu button', () => {
    renderNav(true)

    const menuBtn = screen.getByRole('button', { name: /open navigation drawer/i })
    expect(menuBtn).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    // Open menu
    fireEvent.click(menuBtn)
    const drawer = screen.getByRole('dialog', { name: /navigation drawer/i })
    expect(drawer).toBeInTheDocument()

    // Check that standard navigation items are rendered, but admin items are restricted on mobile
    const mobileNav = within(drawer).getByRole('navigation', { name: /mobile main navigation/i })
    expect(within(mobileNav).getByRole('link', { name: /command center/i })).toBeInTheDocument()
    expect(within(mobileNav).getByRole('link', { name: /audio feed/i })).toBeInTheDocument()
    expect(within(mobileNav).getByRole('link', { name: /insights/i })).toBeInTheDocument()
    expect(within(mobileNav).getByRole('link', { name: /events/i })).toBeInTheDocument()
    expect(within(mobileNav).queryByRole('link', { name: /database/i })).not.toBeInTheDocument()
    expect(within(mobileNav).queryByRole('link', { name: /users/i })).not.toBeInTheDocument()
    expect(within(mobileNav).queryByRole('link', { name: /settings/i })).not.toBeInTheDocument()

    // Check user card
    expect(within(drawer).getByText('Administrator')).toBeInTheDocument()

    // Close menu via close button
    const closeBtn = within(drawer).getByRole('button', { name: /close menu/i })
    fireEvent.click(closeBtn)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('closes mobile drawer on Escape key press', () => {
    renderNav(false)

    const menuBtn = screen.getByRole('button', { name: /open navigation drawer/i })
    fireEvent.click(menuBtn)
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('triggers logout from the drawer footer button', () => {
    renderNav(true)

    const menuBtn = screen.getByRole('button', { name: /open navigation drawer/i })
    fireEvent.click(menuBtn)

    const drawer = screen.getByRole('dialog', { name: /navigation drawer/i })
    const logoutBtn = within(drawer).getByRole('button', { name: /log out/i })
    fireEvent.click(logoutBtn)

    expect(mockLogout).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
