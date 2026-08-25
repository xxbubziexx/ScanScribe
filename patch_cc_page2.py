with open("app/frontend/src/pages/CommandCenter/CommandCenterPage.tsx", "r") as f:
    content = f.read()

# Replace map usage
new_map = """        <CommandCenterMap
          events={pipelineEvents}
          selectedEventId={selectedEventId}
          onSelectEvent={(id) => setSelectedEventId(id)}
          onGeocodeEvent={handleGeocode}
          onRemoveGeocodeEvent={handleRemoveGeocode}
          isGeocoding={geocodeMutation.isPending}
        />"""

# It's currently:
#         <CommandCenterMap
#           events={pipelineEvents}
#           selectedEventId={selectedEventId}
#           onSelectEvent={(id) => setSelectedEventId(id)}
#           onGeocodeEvent={handleGeocode}
#           isGeocoding={geocodeMutation.isPending}
#         />
if "onRemoveGeocodeEvent" not in content:
    content = content.replace("        <CommandCenterMap\n          events={pipelineEvents}\n          selectedEventId={selectedEventId}\n          onSelectEvent={(id) => setSelectedEventId(id)}\n          onGeocodeEvent={handleGeocode}\n          isGeocoding={geocodeMutation.isPending}\n        />", new_map)
    with open("app/frontend/src/pages/CommandCenter/CommandCenterPage.tsx", "w") as f:
        f.write(content)
    print("Patched Map usage")
else:
    print("Map already patched")
