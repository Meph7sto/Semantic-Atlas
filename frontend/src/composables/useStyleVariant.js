import { computed, ref, watch } from 'vue'

const STYLE_VARIANT_STORAGE_KEY = 'semantic-atlas.style.variant'
const STYLE_VARIANTS = new Set(['classic', 'new'])

const getInitialStyleVariant = () => {
  if (typeof window === 'undefined') return 'classic'

  try {
    const savedVariant = window.localStorage.getItem(STYLE_VARIANT_STORAGE_KEY)
    return STYLE_VARIANTS.has(savedVariant) ? savedVariant : 'classic'
  } catch {
    return 'classic'
  }
}

const styleVariant = ref(getInitialStyleVariant())

if (typeof window !== 'undefined') {
  watch(
    styleVariant,
    value => {
      try {
        window.localStorage.setItem(STYLE_VARIANT_STORAGE_KEY, value)
      } catch {
        // Ignore storage failures; the in-memory switch still works.
      }
    },
    { immediate: true }
  )
}

export function useStyleVariant() {
  const setStyleVariant = value => {
    if (STYLE_VARIANTS.has(value)) {
      styleVariant.value = value
    }
  }

  const toggleStyleVariant = () => {
    styleVariant.value = styleVariant.value === 'new' ? 'classic' : 'new'
  }

  return {
    isNewStyle: computed(() => styleVariant.value === 'new'),
    setStyleVariant,
    styleVariant,
    toggleStyleVariant
  }
}
