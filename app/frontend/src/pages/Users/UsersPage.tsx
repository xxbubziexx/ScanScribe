import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { usersApi } from '@/lib/users'
import { errorMessage } from '@/types/api'
import type { UserResponse } from '@/types/api'

function formatCreated(iso: string) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}

export function UsersPage() {
  const { user } = useAuth()
  const { addToast } = useToast()
  const queryClient = useQueryClient()
  const isAdmin = user?.is_admin === true

  const [searchInput, setSearchInput] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(searchInput), 400)
    return () => window.clearTimeout(t)
  }, [searchInput])

  const listQuery = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.list(),
    enabled: isAdmin,
    staleTime: 30_000,
  })

  const allRows = listQuery.data ?? []
  const adminCount = useMemo(() => allRows.filter((u) => u.is_admin).length, [allRows])

  const rows = useMemo(() => {
    const q = debouncedSearch.trim().toLowerCase()
    if (!q) return allRows
    return allRows.filter(
      (u) =>
        u.username.toLowerCase().includes(q) || u.email.toLowerCase().includes(q),
    )
  }, [allRows, debouncedSearch])

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['users-list'] })

  const promoteMut = useMutation({
    mutationFn: (id: number) => usersApi.promote(id),
    onSuccess: (r) => {
      addToast(r.message, 'success')
      invalidate()
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Promote failed'), 'error'),
  })

  const demoteMut = useMutation({
    mutationFn: (id: number) => usersApi.demote(id),
    onSuccess: (r) => {
      addToast(r.message, 'success')
      invalidate()
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Demote failed'), 'error'),
  })

  const toggleMut = useMutation({
    mutationFn: (id: number) => usersApi.toggleActive(id),
    onSuccess: (r) => {
      addToast(r.message, 'success')
      invalidate()
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Update failed'), 'error'),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => usersApi.delete(id),
    onSuccess: (r) => {
      addToast(r.message, 'success')
      invalidate()
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Delete failed'), 'error'),
  })

  if (!isAdmin) {
    return (
      <div className="flex h-64 items-center justify-center rounded-xl border border-white/10">
        <p className="text-center text-sm text-gray-500">
          Admin access is required to manage users.
        </p>
      </div>
    )
  }

  return (
    <div className="ss-db-page">
      <h1 className="ss-db-title">Users</h1>
      <p className="mb-4 text-sm text-gray-500">Manage accounts and admin roles.</p>

      <div className="ss-db-filters">
        <div className="min-w-0 flex-1">
          <label className="ss-form-label" htmlFor="users-search">
            Search
          </label>
          <input
            id="users-search"
            type="search"
            className="ss-input"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Username or email…"
            autoComplete="off"
          />
        </div>
      </div>

      {listQuery.isError && (
        <p className="ss-form-error mb-4" role="alert">
          { errorMessage(listQuery.error, 'Failed to load users') }
        </p>
      )}

      {listQuery.isLoading && <p className="text-sm text-gray-500">Loading…</p>}

      {!listQuery.isLoading && !listQuery.isError && rows.length === 0 && (
        <p className="ss-empty not-italic">
          {allRows.length === 0 ? 'No users yet.' : 'No users match this search.'}
        </p>
      )}

      {!listQuery.isLoading && !listQuery.isError && rows.length > 0 && (
        <div className="ss-db-table-wrap">
          <table className="ss-db-table min-w-[720px]">
            <thead>
              <tr>
                <th className="ss-db-th">User</th>
                <th className="ss-db-th">Email</th>
                <th className="ss-db-th">Status</th>
                <th className="ss-db-th">Role</th>
                <th className="ss-db-th">Created</th>
                <th className="ss-db-th text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <UserRow
                  key={row.id}
                  row={row}
                  currentUserId={user?.id ?? -1}
                  adminCount={adminCount}
                  promotePending={promoteMut.isPending}
                  demotePending={demoteMut.isPending}
                  togglePending={toggleMut.isPending}
                  deletePending={deleteMut.isPending}
                  onPromote={() => promoteMut.mutate(row.id)}
                  onDemote={() => demoteMut.mutate(row.id)}
                  onToggleActive={() => toggleMut.mutate(row.id)}
                  onDelete={() => {
                    if (!window.confirm(`Delete user “${row.username}”? This cannot be undone.`)) return
                    deleteMut.mutate(row.id)
                  }}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function UserRow({
  row,
  currentUserId,
  adminCount,
  promotePending,
  demotePending,
  togglePending,
  deletePending,
  onPromote,
  onDemote,
  onToggleActive,
  onDelete,
}: {
  row: UserResponse
  currentUserId: number
  adminCount: number
  promotePending: boolean
  demotePending: boolean
  togglePending: boolean
  deletePending: boolean
  onPromote: () => void
  onDemote: () => void
  onToggleActive: () => void
  onDelete: () => void
}) {
  const isSelf = row.id === currentUserId
  const soleAdmin = row.is_admin && adminCount <= 1
  const demoteDisabled = isSelf && soleAdmin
  const busy = promotePending || demotePending || togglePending || deletePending

  return (
    <tr>
      <td className="ss-db-td font-medium text-gray-200">{row.username}</td>
      <td className="ss-db-td max-w-[14rem] truncate text-gray-400">{row.email}</td>
      <td className="ss-db-td">
        {row.is_active ? (
          <span className="ss-badge-ok text-xs">active</span>
        ) : (
          <span className="ss-badge-bad text-xs">inactive</span>
        )}
      </td>
      <td className="ss-db-td">
        {row.is_admin ? (
          <span className="ss-pill-admin text-xs">admin</span>
        ) : (
          <span className="text-xs text-gray-500">user</span>
        )}
      </td>
      <td className="ss-db-td tabular-nums text-gray-500">{formatCreated(row.created_at)}</td>
      <td className="ss-db-td">
        <div className="ss-db-actions">
          {!row.is_admin ? (
            <button
              type="button"
              className="ss-text-link"
              disabled={busy}
              onClick={onPromote}
            >
              Make admin
            </button>
          ) : (
            <button
              type="button"
              className="ss-text-link"
              disabled={busy || demoteDisabled}
              title={
                demoteDisabled ? 'Cannot remove the last admin role from yourself' : undefined
              }
              onClick={onDemote}
            >
              Remove admin
            </button>
          )}
          <button
            type="button"
            className="ss-btn-filter-clear"
            disabled={busy || isSelf}
            title={isSelf ? 'You cannot deactivate your own account' : undefined}
            onClick={onToggleActive}
          >
            {row.is_active ? 'Deactivate' : 'Activate'}
          </button>
          <button
            type="button"
            className="ss-btn-danger-soft px-2 py-0.5 text-xs"
            disabled={busy || isSelf}
            title={isSelf ? 'You cannot delete your own account' : undefined}
            onClick={onDelete}
          >
            Delete
          </button>
        </div>
      </td>
    </tr>
  )
}
