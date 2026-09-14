import { describe, it, expect, vi } from 'vitest'
import L from 'leaflet'
import { ensurePopupInView } from '../pages/CommandCenter/CommandCenterMap'

describe('CommandCenterMap ensurePopupInView', () => {
  function createMapAndPopup() {
    const container = document.createElement('div')
    document.body.appendChild(container)

    const map = L.map(container, {
      center: [37.9227, -90.5405],
      zoom: 15,
    })

    const popupEl = document.createElement('div')
    container.appendChild(popupEl)

    const panBySpy = vi.spyOn(map, 'panBy').mockImplementation(() => map)

    const cleanup = () => {
      map.remove()
      container.remove()
    }

    return { map, container, popupEl, panBySpy, cleanup }
  }

  it('does not pan if popup is already fully inside map container with padding', () => {
    const { map, container, popupEl, panBySpy, cleanup } = createMapAndPopup()

    vi.spyOn(container, 'getBoundingClientRect').mockReturnValue({
      top: 0,
      bottom: 600,
      left: 0,
      right: 400,
      width: 400,
      height: 600,
      x: 0,
      y: 0,
      toJSON: () => {},
    })

    vi.spyOn(popupEl, 'getBoundingClientRect').mockReturnValue({
      top: 100,
      bottom: 450,
      left: 30,
      right: 370,
      width: 340,
      height: 350,
      x: 30,
      y: 100,
      toJSON: () => {},
    })

    const panned = ensurePopupInView(map, popupEl, { padding: 20 })
    expect(panned).toBe(false)
    expect(panBySpy).not.toHaveBeenCalled()

    cleanup()
  })

  it('pans map down when popup top is clipped above map container', () => {
    const { map, container, popupEl, panBySpy, cleanup } = createMapAndPopup()

    vi.spyOn(container, 'getBoundingClientRect').mockReturnValue({
      top: 0,
      bottom: 600,
      left: 0,
      right: 400,
      width: 400,
      height: 600,
      x: 0,
      y: 0,
      toJSON: () => {},
    })

    // Popup top is -30, so with 20px padding it overflows by -50px
    vi.spyOn(popupEl, 'getBoundingClientRect').mockReturnValue({
      top: -30,
      bottom: 350,
      left: 30,
      right: 370,
      width: 340,
      height: 380,
      x: 30,
      y: -30,
      toJSON: () => {},
    })

    const panned = ensurePopupInView(map, popupEl, { padding: 20, animate: true })
    expect(panned).toBe(true)
    expect(panBySpy).toHaveBeenCalledWith([0, -50], { animate: true })

    cleanup()
  })

  it('pans map up when popup bottom is clipped below map container', () => {
    const { map, container, popupEl, panBySpy, cleanup } = createMapAndPopup()

    vi.spyOn(container, 'getBoundingClientRect').mockReturnValue({
      top: 0,
      bottom: 600,
      left: 0,
      right: 400,
      width: 400,
      height: 600,
      x: 0,
      y: 0,
      toJSON: () => {},
    })

    // Popup bottom is 610, bottom boundary is 600 - 20 = 580, headroom at top is 200 - 20 = 180
    vi.spyOn(popupEl, 'getBoundingClientRect').mockReturnValue({
      top: 200,
      bottom: 610,
      left: 30,
      right: 370,
      width: 340,
      height: 410,
      x: 30,
      y: 200,
      toJSON: () => {},
    })

    const panned = ensurePopupInView(map, popupEl, { padding: 20, animate: true })
    expect(panned).toBe(true)
    expect(panBySpy).toHaveBeenCalledWith([0, 30], { animate: true })

    cleanup()
  })

  it('pans horizontally if popup is clipped on the left', () => {
    const { map, container, popupEl, panBySpy, cleanup } = createMapAndPopup()

    vi.spyOn(container, 'getBoundingClientRect').mockReturnValue({
      top: 0,
      bottom: 600,
      left: 0,
      right: 400,
      width: 400,
      height: 600,
      x: 0,
      y: 0,
      toJSON: () => {},
    })

    // Popup left is -10, allowed left is 20
    vi.spyOn(popupEl, 'getBoundingClientRect').mockReturnValue({
      top: 100,
      bottom: 450,
      left: -10,
      right: 330,
      width: 340,
      height: 350,
      x: -10,
      y: 100,
      toJSON: () => {},
    })

    const panned = ensurePopupInView(map, popupEl, { padding: 20, animate: false })
    expect(panned).toBe(true)
    expect(panBySpy).toHaveBeenCalledWith([-30, 0], { animate: false })

    cleanup()
  })

  it('returns false without panning if element has zero width or height', () => {
    const { map, container, popupEl, panBySpy, cleanup } = createMapAndPopup()

    vi.spyOn(container, 'getBoundingClientRect').mockReturnValue({
      top: 0,
      bottom: 600,
      left: 0,
      right: 400,
      width: 400,
      height: 600,
      x: 0,
      y: 0,
      toJSON: () => {},
    })

    vi.spyOn(popupEl, 'getBoundingClientRect').mockReturnValue({
      top: 0,
      bottom: 0,
      left: 0,
      right: 0,
      width: 0,
      height: 0,
      x: 0,
      y: 0,
      toJSON: () => {},
    })

    const panned = ensurePopupInView(map, popupEl)
    expect(panned).toBe(false)
    expect(panBySpy).not.toHaveBeenCalled()

    cleanup()
  })
})
