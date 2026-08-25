with open("app/frontend/src/pages/CommandCenter/CommandCenterPage.tsx", "r") as f:
    content = f.read()

state_vars = """
  const [mapOptionsOpen, setMapOptionsOpen] = useState(false)
  const [mapOptions, setMapOptions] = useState({ showLabels: true, clusterPins: false })
"""

content = content.replace("  const [timeframe, setTimeframe] = useState<Timeframe>('24h')", "  const [timeframe, setTimeframe] = useState<Timeframe>('24h')\n" + state_vars)

dropdown_html = """          <div className="relative">
            <button
              type="button"
              className="ss-btn-ghost text-xs py-1 px-2.5 flex items-center gap-1"
              onClick={() => setMapOptionsOpen(!mapOptionsOpen)}
            >
              <span>⚙️</span> Map Options
            </button>
            {mapOptionsOpen && (
              <div className="absolute top-full right-0 mt-1 w-48 bg-gray-900 border border-white/10 rounded shadow-xl p-2 z-[9999] flex flex-col gap-2">
                <label className="flex items-center gap-2 text-xs text-gray-200 cursor-pointer">
                  <input type="checkbox" checked={mapOptions.showLabels} onChange={(e) => setMapOptions({ ...mapOptions, showLabels: e.target.checked })} />
                  Show Pin Labels
                </label>
                <label className="flex items-center gap-2 text-xs text-gray-200 cursor-pointer">
                  <input type="checkbox" checked={mapOptions.clusterPins} onChange={(e) => setMapOptions({ ...mapOptions, clusterPins: e.target.checked })} />
                  Cluster Pins
                </label>
              </div>
            )}
          </div>
"""

content = content.replace('        <div className="ss-cc-controls">', '        <div className="ss-cc-controls">\n' + dropdown_html)

with open("app/frontend/src/pages/CommandCenter/CommandCenterPage.tsx", "w") as f:
    f.write(content)
print("Patched dropdown.")
