import re

with open("app/frontend/src/pages/CommandCenter/CommandCenterPage.tsx", "r") as f:
    content = f.read()

# 1. Add removeGeocodeMutation
new_mutation = """  const removeGeocodeMutation = useMutation({
    mutationFn: (eventId: string) => eventsApi.removeGeocode(eventId),
    onSuccess: (res) => {
      addToast(res.message || 'Pin removed', 'success')
      void queryClient.invalidateQueries({ queryKey: ['events-list'] })
    },
    onError: (e: unknown) => {
      addToast(errorMessage(e, 'Failed to remove pin'), 'error')
    },
  })

  const handleRemoveGeocode = useCallback(
    (eventId: string) => {
      removeGeocodeMutation.mutate(eventId)
    },
    [removeGeocodeMutation],
  )
"""

if "removeGeocodeMutation" not in content:
    content = content.replace("  const handleGeocode = useCallback(", new_mutation + "\n  const handleGeocode = useCallback(")
    with open("app/frontend/src/pages/CommandCenter/CommandCenterPage.tsx", "w") as f:
        f.write(content)
    print("Patched CommandCenterPage mutations")
else:
    print("Already patched mutations")
