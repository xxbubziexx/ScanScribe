import re

with open("app/frontend/src/pages/Events/EventsMonitorsPage.tsx", "r") as f:
    content = f.read()

# Add todayUnitsQuery
query_setup = """  const todayTalkgroupsQuery = useQuery({
    queryKey: ['logs-talkgroups-today'],
    queryFn: () => logsApi.talkgroups({ today: true }),
    staleTime: 60_000,
  })

  const todayUnitsQuery = useQuery({
    queryKey: ['events-units-today'],
    queryFn: () => eventsApi.todayUnits(),
    staleTime: 60_000,
  })"""

if "todayUnitsQuery" not in content:
    content = re.sub(
        r"  const todayTalkgroupsQuery = useQuery\({[^}]+}\)",
        query_setup,
        content,
        flags=re.MULTILINE
    )

    # Add copy function
    copy_fn = """  const copyTodayTalkgroup = async (val: string) => {
    const el = document.getElementById('new-monitor-tg') as HTMLTextAreaElement | null
    if (!el) return
    let current = el.value.trim()
    if (current && !current.endsWith('\n')) current += '\n'
    el.value = current + val
    setCreateTg(el.value)
  }

  const copyTodayUnit = async (val: string) => {
    const el = document.getElementById('new-monitor-known-units') as HTMLTextAreaElement | null
    if (!el) return
    let current = el.value.trim()
    if (current && !current.endsWith(',')) current += ', '
    el.value = current + val
    setCreateKnownUnits(el.value)
  }"""

    content = re.sub(
        r"  const copyTodayTalkgroup = async \(val: string\) => {[^}]+}[^}]+}",
        copy_fn,
        content,
        flags=re.MULTILINE
    )

    # Add the aside
    aside_block = """          </aside>

          <aside className="ss-events-monitor-today-tg" aria-label="Today's logged units">
            <div className="ss-events-monitor-today-tg-head">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-200/90">
                Today&apos;s logged units
              </p>
              <p className="mt-0.5 font-mono text-[10px] text-gray-500">
                {new Date().toLocaleDateString(undefined, {
                  weekday: 'short',
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </p>
            </div>
            <div className="ss-events-monitor-today-tg-scroll">
              {todayUnitsQuery.isPending ? (
                <p className="text-xs text-gray-500">Loading…</p>
              ) : todayUnitsQuery.isError ? (
                <p className="text-xs text-amber-200/90">{errorMessage(todayUnitsQuery.error, 'Could not load')}</p>
              ) : (todayUnitsQuery.data?.units ?? []).length === 0 ? (
                <p className="text-xs text-gray-500">None logged yet today.</p>
              ) : (
                <ul className="ss-events-monitor-today-tg-list">
                  {(todayUnitsQuery.data?.units ?? []).map((unit) => (
                    <li key={unit} className="ss-events-monitor-today-tg-row">
                      <span className="ss-events-monitor-today-tg-text">{unit}</span>
                      <button
                        type="button"
                        className="ss-events-monitor-today-tg-copy"
                        onClick={() => void copyTodayUnit(unit)}
                      >
                        Copy
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </aside>"""
    
    content = content.replace("          </aside>\n        </div>", aside_block + "\n        </div>")

    with open("app/frontend/src/pages/Events/EventsMonitorsPage.tsx", "w") as f:
        f.write(content)
    print("Patched React component.")
else:
    print("React component already patched.")
