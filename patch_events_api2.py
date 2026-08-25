with open("app/frontend/src/lib/events.ts", "r") as f:
    content = f.read()

new_method = """  removeGeocode: (eventId: string) =>
    request<{ ok: boolean; message?: string }>(
      `${EVENTS_API}/events/${encodeURIComponent(eventId)}/remove-geocode`,
      { method: 'POST' },
    ),
"""

if "removeGeocode:" not in content:
    content = content.replace("  geocode: (eventId: string) =>", new_method + "  geocode: (eventId: string) =>")
    with open("app/frontend/src/lib/events.ts", "w") as f:
        f.write(content)
    print("Patched.")
else:
    print("Already exists.")
