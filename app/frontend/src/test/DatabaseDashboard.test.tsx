import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/context/ToastContext'
import { DataExplorerLayout } from '@/pages/DataExplorer/DataExplorerLayout'
import { DatabasePage } from '@/pages/Database/DatabasePage'
import { EntitiesTable } from '@/pages/DataExplorer/Tables/EntitiesTable'
import { maintenanceApi } from '@/lib/maintenance'
import { downloadBulkAudioZip, logsApi } from '@/lib/logs'
import { downloadEntitiesCsv, eventsApi } from '@/lib/events'

vi.mock('@/context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, username: 'admin', email: 'admin@localhost', is_admin: true, is_active: true },
    loading: false,
  }),
}))

vi.mock('@/lib/maintenance', () => ({
  maintenanceApi: {
    overview: vi.fn(),
  },
}))

vi.mock('@/lib/logs', () => ({
  buildListParams: vi.fn(() => new URLSearchParams('page=1&page_size=50')),
  logsApi: {
    list: vi.fn(),
    talkgroups: vi.fn(),
    activeDates: vi.fn(),
    delete: vi.fn(),
    bulkDelete: vi.fn(),
  },
  downloadLogsExport: vi.fn(),
  downloadBulkAudioZip: vi.fn(),
  downloadAudioFile: vi.fn(),
}))

vi.mock('@/lib/events', () => ({
  eventsApi: {
    monitors: vi.fn(),
    nerLabels: vi.fn(),
    entities: vi.fn(),
  },
  downloadEntitiesCsv: vi.fn(),
}))

function wrap(ui: React.ReactElement, initialEntries = ['/data/logs']) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <QueryClientProvider client={qc}>
        <ToastProvider>{ui}</ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('Database Workbench Suite', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders DataExplorerLayout sidebar with all 5 tables, live counts, and telemetry without Overview tab', async () => {
    vi.mocked(maintenanceApi.overview).mockResolvedValue({
      generated_at: '2026-11-24T19:00:00Z',
      logs_last_24h: 42,
      total_audio_duration_seconds: 7200,
      storage: {
        db_bytes: 1024 * 1024,
        wal_bytes: 65536,
        shm_bytes: 32768,
        total_sqlite_bytes: 1122304,
        journal_mode: 'wal',
        page_size: 4096,
        page_count: 256,
        freelist_count: 4,
        reclaimable_bytes: 16384,
        audio_files_count: 100,
        audio_bytes: 5 * 1024 * 1024,
        audio_layout: 'sharded',
        retention_days: 30,
      },
      tables: [
        { key: 'logs', label: 'Transmissions', route: '/data/logs', row_count: 150, secondary_label: null, secondary_value: null, oldest: null, newest: null },
        { key: 'spans', label: 'Span Store', route: '/data/spans', row_count: 120, secondary_label: null, secondary_value: null, oldest: null, newest: null },
        { key: 'entities', label: 'NER Entities', route: '/data/entities', row_count: 310, secondary_label: null, secondary_value: null, oldest: null, newest: null },
        { key: 'events', label: 'Events', route: '/data/events', row_count: 18, secondary_label: null, secondary_value: null, oldest: null, newest: null },
        { key: 'dataset', label: 'Fine-Tuning Dataset', route: '/data/dataset', row_count: 12, secondary_label: null, secondary_value: null, oldest: null, newest: null },
        { key: 'monitors', label: 'Monitors', route: '/events/monitors', row_count: 3, secondary_label: null, secondary_value: null, oldest: null, newest: null },
      ],
      ner: {
        pipeline_enabled: true,
        ner_only: true,
        ner_loaded: true,
        ner_model_path: './models/incident_ner_v1',
        covered_logs: 120,
        total_logs: 150,
        coverage_pct: 80.0,
        total_spans: 120,
        total_observations: 310,
        labels: [],
      },
      daily_volume: [],
      top_talkgroups_24h: [],
    })

    wrap(<DataExplorerLayout />)

    expect(screen.queryByRole('link', { name: /overview/i })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Transmissions/i })).toHaveAttribute('href', '/data/logs')
    expect(screen.getByRole('link', { name: /Span Store/i })).toHaveAttribute('href', '/data/spans')
    expect(screen.getByRole('link', { name: /NER Entities/i })).toHaveAttribute('href', '/data/entities')
    expect(screen.getByRole('link', { name: /Events/i })).toHaveAttribute('href', '/data/events')
    expect(screen.getByRole('link', { name: /Fine-Tuning Dataset/i })).toHaveAttribute('href', '/data/dataset')

    expect(await screen.findByText('NER-Only')).toBeInTheDocument()
    expect(screen.getByText('80.0%')).toBeInTheDocument()
    expect(screen.getByText('42 clips')).toBeInTheDocument()
    expect(screen.getByText('150')).toBeInTheDocument()
    expect(screen.getByText('310')).toBeInTheDocument()
  })

  it('supports cross-page row selection and bulk audio ZIP download in DatabasePage', async () => {
    vi.mocked(logsApi.activeDates).mockResolvedValue({ dates: ['2026-11-24'] })
    vi.mocked(logsApi.talkgroups).mockResolvedValue({ talkgroups: ['FIRE-DISP', 'EMS-TAC'] })
    vi.mocked(logsApi.list).mockResolvedValue({
      total: 2,
      page: 1,
      page_size: 50,
      total_pages: 1,
      logs: [
        {
          id: 101,
          timestamp: '2026-11-24T12:00:00',
          filename: 'clip_101.wav',
          talkgroup: 'FIRE-DISP',
          transcript: 'Engine 1 responding',
          duration: 6.2,
          file_size: 4096,
          confidence: 0.92,
          audio_path: 'audio_storage/2026/11/24/clip_101.wav',
          log_date: '2026-11-24',
          created_at: '2026-11-24T12:00:00Z',
          is_reviewed: false,
          corrected_transcript: null,
        },
        {
          id: 102,
          timestamp: '2026-11-24T12:05:00',
          filename: 'clip_102.wav',
          talkgroup: 'EMS-TAC',
          transcript: 'Medic 2 clear',
          duration: 4.1,
          file_size: 2048,
          confidence: 0.89,
          audio_path: 'audio_storage/2026/11/24/clip_102.wav',
          log_date: '2026-11-24',
          created_at: '2026-11-24T12:05:00Z',
          is_reviewed: false,
          corrected_transcript: null,
        },
      ],
    })
    vi.mocked(downloadBulkAudioZip).mockResolvedValue({ exportCount: 2, audioCount: 2 })

    wrap(<DatabasePage />, ['/data/logs'])

    const selectAll = await screen.findByLabelText('Select all entries on this page')
    fireEvent.click(selectAll)

    const zipBtn = await screen.findByRole('button', { name: /Download ZIP \(2\)/i })
    fireEvent.click(zipBtn)

    await waitFor(() => {
      expect(downloadBulkAudioZip).toHaveBeenCalledWith([101, 102])
    })
  })

  it('opens NER CSV Exporter modal in EntitiesTable and exports selected labels', async () => {
    vi.mocked(logsApi.activeDates).mockResolvedValue({ dates: ['2026-11-24'] })
    vi.mocked(eventsApi.monitors).mockResolvedValue([
      { id: 1, name: 'Fire Dept', enabled: true, talkgroup_ids: ['FIRE-DISP'], start_event_labels: ['EVT_TYPE'] },
    ])
    vi.mocked(eventsApi.nerLabels).mockResolvedValue({
      labels: ['ADDRESS', 'EVT_TYPE', 'LOC', 'STATUS', 'TIME', 'UNIT'],
    })
    vi.mocked(eventsApi.entities).mockResolvedValue({
      total: 1,
      items: [
        {
          id: 501,
          span_store_id: 12,
          monitor_id: 1,
          talkgroup: 'FIRE-DISP',
          log_entry_id: 101,
          ts: '2026-11-24T12:00:00Z',
          label: 'UNIT',
          canonical: 'Engine 1',
          raw: 'Engine 1',
        },
      ],
    })
    vi.mocked(downloadEntitiesCsv).mockResolvedValue({ rowCount: 15 })

    wrap(<EntitiesTable />, ['/data/entities'])

    const openBtn = await screen.findByRole('button', { name: 'Export NER CSV' })
    fireEvent.click(openBtn)

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    const downloadBtn = screen.getByRole('button', { name: 'Download CSV' })
    fireEvent.click(downloadBtn)

    await waitFor(() => {
      expect(downloadEntitiesCsv).toHaveBeenCalledWith(
        expect.objectContaining({
          labels: ['ADDRESS', 'EVT_TYPE', 'LOC', 'STATUS', 'TIME', 'UNIT'],
          deduplicate: true,
          include_counts: true,
          include_context: false,
        }),
      )
    })
  })
})
