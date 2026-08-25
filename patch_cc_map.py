with open("app/frontend/src/pages/CommandCenter/CommandCenterMap.tsx", "r") as f:
    content = f.read()

# Props definition
if "onRemoveGeocodeEvent?:" not in content:
    content = content.replace("onGeocodeEvent?: (eventId: string) => void", "onGeocodeEvent?: (eventId: string) => void\n  onRemoveGeocodeEvent?: (eventId: string) => void")

# Function signature
if "onRemoveGeocodeEvent," not in content:
    content = content.replace("  onGeocodeEvent,\n  isGeocoding,\n}: CommandCenterMapProps) {", "  onGeocodeEvent,\n  onRemoveGeocodeEvent,\n  isGeocoding,\n}: CommandCenterMapProps) {")
    content = content.replace("  onGeocodeEvent,\n  isGeocoding\n}: CommandCenterMapProps) {", "  onGeocodeEvent,\n  onRemoveGeocodeEvent,\n  isGeocoding\n}: CommandCenterMapProps) {")

# Add button
new_buttons = """                    <div className="flex items-center gap-3">
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

# Existing code:
#                     {onGeocodeEvent && (
#                       <button
#                         type="button"
#                         className="text-indigo-400 hover:text-indigo-300 font-medium underline transition"
#                         disabled={isGeocoding}
#                         onClick={(e) => {
#                           e.stopPropagation()
#                           onGeocodeEvent(ev.eventId)
#                         }}
#                       >
#                         {isGeocoding ? 'Resolving…' : 'Re-Geocode'}
#                       </button>
#                     )}

import re
content = re.sub(r"\{onGeocodeEvent && \([\s\S]*?\}\n                    \)\}", new_buttons, content)

with open("app/frontend/src/pages/CommandCenter/CommandCenterMap.tsx", "w") as f:
    f.write(content)
print("Patched Map component")
