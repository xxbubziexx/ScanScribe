with open("app/frontend/src/lib/events.ts", "r") as f:
    content = f.read()

new_method = """  todayUnits: () => request<{units: string[]}>(`${EVENTS_API}/units/today`),
"""

if "todayUnits" not in content:
    content = content.replace("export const eventsApi = {\n", "export const eventsApi = {\n" + new_method)
    with open("app/frontend/src/lib/events.ts", "w") as f:
        f.write(content)
    print("Patched.")
else:
    print("Already exists.")
