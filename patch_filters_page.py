with open("app/frontend/src/pages/CommandCenter/CommandCenterPage.tsx", "r") as f:
    content = f.read()

state_imports = "import { useCallback, useEffect, useMemo, useState, useRef } from 'react'"
content = content.replace("import { CommandCenterFeed } from './CommandCenterFeed'", "import { CommandCenterFeed, type FilterMode, type Timeframe } from './CommandCenterFeed'")

state_vars = """
  // Filter state (hoisted so Map can share it)
  const [search, setSearch] = useState('')
  const [selectedMonitor, setSelectedMonitor] = useState<number | 'all'>('all')
  const [filterMode, setFilterMode] = useState<FilterMode>('open')
  const [timeframe, setTimeframe] = useState<Timeframe>('24h')

  // Transform raw event items into PipelineEvents with monitor names
"""

content = content.replace("  // Transform raw event items into PipelineEvents with monitor names\n", state_vars)

filter_logic = """  const filteredEvents = useMemo(() => {
    const now = Date.now()
    return pipelineEvents.filter((ev) => {
      // Monitor filter
      if (selectedMonitor !== 'all' && ev.monitorId !== selectedMonitor) return false
      // Filter mode
      if (filterMode === 'open' && ev.status !== 'open') return false
      if (filterMode === 'closed' && ev.status !== 'closed') return false
      if (filterMode === 'mapped' && (ev.latitude == null || ev.longitude == null)) return false
      
      // Timeframe filter
      const evTime = new Date(ev.incidentAt ?? ev.createdAt).getTime()
      if (timeframe === '24h' && now - evTime > 24 * 60 * 60 * 1000) return false
      if (timeframe === '3day' && now - evTime > 3 * 24 * 60 * 60 * 1000) return false
      if (timeframe === '7day' && now - evTime > 7 * 24 * 60 * 60 * 1000) return false
      
      // Text search
      if (search.trim()) {
        const q = search.toLowerCase()
        const textToSearch = [
          ev.eventId,
          ev.eventType,
          ev.broadcastType,
          ev.status,
          ev.location,
          ev.resolvedAddress,
          ev.units,
          ev.talkgroup,
          ev.summary,
          ev.originalTranscription,
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase()
        if (!textToSearch.includes(q)) return false
      }
      
      return true
    })
  }, [pipelineEvents, selectedMonitor, filterMode, timeframe, search])
"""

content = content.replace("  return (\n", filter_logic + "\n  return (\n")

# Replace Map props
content = content.replace(
    "        <CommandCenterMap\n          events={pipelineEvents}",
    "        <CommandCenterMap\n          events={filteredEvents}"
)

# Replace Feed props
feed_props = """        <CommandCenterFeed
          events={filteredEvents}
          rawEvents={pipelineEvents}
          monitors={monitors}
          selectedEventId={selectedEventId}
          onSelectEvent={(id) => setSelectedEventId(id)}
          onGeocodeEvent={handleGeocode}
          isGeocoding={geocodeMutation.isPending}
          search={search}
          setSearch={setSearch}
          selectedMonitor={selectedMonitor}
          setSelectedMonitor={setSelectedMonitor}
          filterMode={filterMode}
          setFilterMode={setFilterMode}
          timeframe={timeframe}
          setTimeframe={setTimeframe}
        />"""

import re
content = re.sub(r"        <CommandCenterFeed[\s\S]*?/>", feed_props, content)

with open("app/frontend/src/pages/CommandCenter/CommandCenterPage.tsx", "w") as f:
    f.write(content)
print("Patched CommandCenterPage for filters")
