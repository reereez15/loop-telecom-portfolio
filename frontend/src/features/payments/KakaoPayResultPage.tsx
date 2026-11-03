import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom'
import Loading from '../../components/common/Loading'
import { ApiError, api } from '../../services/apiClient'

// 카카오페이 인증 후 돌아오는 화면. 두 경로를 공용으로 처리한다:
//   /billing/kakaopay/approve|cancel|fail?payment_id=..&pg_token=..     (요금 납부)
//   /membership/kakaopay/approve|cancel|fail?rank=..&pg_token=..      (멤버십 등급 구매 — tid 는 서버 쿠키에 있다)
export default function KakaoPayResultPage() {
  const { result } = useParams()
  const { pathname } = useLocation()
  const [params] = useSearchParams()
  const section = pathname.startsWith('/membership') ? 'membership' : 'billing'
  const [state, setState] = useState<{ ok: boolean; text: string } | null>(null)
  const sent = useRef(false)

  useEffect(() => {
    if (sent.current) return            // 개발 모드 이중 실행 방지 (서버도 같은 결과를 돌려줌)
    sent.current = true
    // 멤버십 등급 구매는 서버가 tid 를 HttpOnly 쿠키로 들고 있어 보낼 식별자가 없다. 요금 납부만 payment_id 를 쓴다.
    const base = section === 'membership' ? '/membership/upgrade' : '/payments'
    const ids = section === 'membership' ? {} : { payment_id: Number(params.get('payment_id')) }
    const run = async () => {
      try {
        if (result === 'approve') {
          await api(`${base}/kakaopay/approve`, { method: 'POST', body: { ...ids, pg_token: params.get('pg_token') ?? '' } })
          setState({ ok: true, text: section === 'membership' ? '카카오페이로 등급을 구매했습니다.' : '카카오페이 결제가 완료되었습니다.' })
        } else {
          await api(`${base}/kakaopay/abort`, { method: 'POST', body: { ...ids, reason: result === 'cancel' ? 'cancel' : 'fail' } })
          setState({ ok: false, text: result === 'cancel' ? '결제를 취소했습니다.' : '카카오페이 결제에 실패했습니다.' })
        }
      } catch (err) {
        setState({ ok: false, text: (err as ApiError).message })
      }
    }
    run()
  }, [params, result, section])

  const backTo = section === 'membership' ? '/membership' : '/billing'
  const backLabel = section === 'membership' ? '멤버십으로 돌아가기' : '요금 납부로 돌아가기'

  return (
    <section className="page">
      <h1 className="page__title">카카오페이 결제</h1>
      {!state ? <Loading label="결제를 확인하는 중" /> : (
        <div className={`notice ${state.ok ? 'notice--ok' : 'notice--warn'}`} role="status">{state.text}</div>
      )}
      <Link to={backTo} className="btn">{backLabel}</Link>
    </section>
  )
}
