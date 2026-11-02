import { useEffect, useState } from 'react'

// 화면 테마: light / dark 중 선택. 선택은 이 브라우저에만 저장한다 (계정·서버와 무관). 기본값은 light.
export type ThemePref = 'light' | 'dark'
export type Theme = 'light' | 'dark'
const KEY = 'loop-theme'
const EVENT = 'loop-theme-change'

export function getPref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'dark' ? 'dark' : 'light'
  } catch { return 'light' }
}

export function applyTheme(pref: ThemePref = getPref()) {
  const root = document.documentElement
  root.dataset.theme = pref
  root.dataset.themePref = pref
}

export function setPref(pref: ThemePref) {
  try { localStorage.setItem(KEY, pref) } catch { /* 저장 불가 환경 */ }
  applyTheme(pref)
  window.dispatchEvent(new Event(EVENT))
}

// 컴포넌트용: 현재 선택(=적용) 테마
export function useTheme() {
  const [pref, setState] = useState<ThemePref>(getPref)
  useEffect(() => {
    const sync = () => { const p = getPref(); applyTheme(p); setState(p) }
    window.addEventListener(EVENT, sync)
    window.addEventListener('storage', sync)   // 다른 탭에서 바꾼 경우
    return () => { window.removeEventListener(EVENT, sync); window.removeEventListener('storage', sync) }
  }, [])
  return { pref, theme: pref, setPref }
}

// Grafana 임베드 주소에 현재 테마를 붙인다 (theme=light|dark)
export function withGrafanaTheme(url: string, theme: Theme) {
  try {
    const u = new URL(url)
    u.searchParams.set('theme', theme)
    return u.toString().replace(/kiosk=(&|$)/, 'kiosk$1')   // kiosk 는 값 없이 유지
  } catch { return url }
}
