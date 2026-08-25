with open("app/frontend/src/pages/CommandCenter/CommandCenterMap.tsx", "r") as f:
    content = f.read()

old_code = """                    {onGeocodeEvent && (
                      <button
                        type="button"
                        className="text-indigo-400 hover:text-indigo-300 font-medium underline transition"
                        disabled={isGeocoding}
                        onClick={(e) => {
                          e.stopPropagation()
                          onGeocodeEvent(ev.eventId)
                        }}
                      >
                        {isGeocoding ? 'Resolving…' : 'Re-Geocode'}
                      </button>
                    )}"""

new_code = """                    <div className="flex items-center gap-3">
                      {onRemoveGeocodeEvent && (
                        <button
                          type="button"
                          className="text-red-400 hover:text-red-300 font-medium underline transition"
                          onClick={(e) => {
                            e.stopPropagation()
                            onRemoveGeocodeEvent(ev.eventId)
                          }}
                        >
                          Remove Pin
                        </button>
                      )}
                      {onGeocodeEvent && (
                        <button
                          type="button"
                          className="text-indigo-400 hover:text-indigo-300 font-medium underline transition"
                          disabled={isGeocoding}
                          onClick={(e) => {
                            e.stopPropagation()
                            onGeocodeEvent(ev.eventId)
                          }}
                        >
                          {isGeocoding ? 'Resolving…' : 'Re-Geocode'}
                        </button>
                      )}
                    </div>"""

if old_code in content:
    content = content.replace(old_code, new_code)
    with open("app/frontend/src/pages/CommandCenter/CommandCenterMap.tsx", "w") as f:
        f.write(content)
    print("Replaced!")
else:
    print("Not found.")
