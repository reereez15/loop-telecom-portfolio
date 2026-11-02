import { useEffect, useState } from 'react'

function fmt(ms: number) {
  const total = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

// 로그인 후 경과 시간("접속 시간")을 1초마다 갱신해 보여준다.
// idleMinutes 동안 요청이 없으면 서버가 자동 로그아웃시키므로, 그 기준을 안내문(title)에 같이 적는다.
export default function SessionClock({ since, idleMinutes }: { since: string; idleMinutes: number }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  const elapsed = now - new Date(since).getTime()
  return (
    <li className="user-menu__meta user-menu__session" title={`${idleMinutes}분 이상 활동이 없으면 자동 로그아웃됩니다.`}>
      접속 시간 {fmt(elapsed)}
    </li>
  )
}
