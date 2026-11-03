import { useEffect, useState } from 'react'
import { useAuth } from '../../app/providers/AuthProvider'

function fmt(ms: number) {
  const total = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

// 상단 바에 로그인 후 경과 시간("접속 시간")을 1초마다 갱신해 보여준다.
// idle_minutes 분 동안 아무 요청이 없으면 서버가 세션을 끊으므로, 그 기준을 안내문(title)에 적는다.
// (경과 시간이 그 값을 넘어도 계속 쓰고 있으면 로그아웃되지 않는다 — "활동이 없을 때" 기준이다.)
export default function SessionClock() {
  const { session } = useAuth()
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  if (!session) return null
  const elapsed = now - new Date(session.created_at).getTime()
  return (
    <span className="session-clock" title={`${session.idle_minutes}분 이상 활동이 없으면 자동 로그아웃됩니다.`}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
           strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
      <span className="session-clock__label">접속</span>
      <span className="session-clock__time">{fmt(elapsed)}</span>
    </span>
  )
}
