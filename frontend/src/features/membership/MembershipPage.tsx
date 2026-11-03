import { Link } from 'react-router-dom'
import { useRef, useState } from 'react'
import ErrorState from '../../components/common/ErrorState'
import Loading from '../../components/common/Loading'
import Logo from '../../components/common/Logo'
import { ApiError, api } from '../../services/apiClient'
import type { Benefit, Membership, PointTransaction, Redemption } from '../../services/types'
import { dateTime, won } from '../../utils/format'
import { newIdempotencyKey } from '../../utils/idempotency'
import { useApi } from '../../utils/useApi'
import { customerMembershipName } from '../../utils/membership'

const KIND: Record<string, string> = { EARN: '적립', REDEEM: '사용', REVERSE: '취소' }
type Purchase = { id: number; name: string; amount: number; status: string }

type Message = { type: 'ok' | 'error'; text: string } | null

export default function MembershipPage() {
  const me = useApi<{ membership: Membership }>('/membership/me')
  const benefits = useApi<{ benefits: Benefit[] }>('/membership/benefits')
  const tx = useApi<{ transactions: PointTransaction[] }>('/membership/transactions')
  const used = useApi<{ redemptions: Redemption[] }>('/membership/redemptions')
  const catalog = useApi<{ tiers: { name: string; rank: number; earn_rate_bp: number; min_monthly_fee: number }[] }>('/membership/tiers')
  const purchases = useApi<{ purchases: Purchase[] }>('/membership/upgrades/me')
  const [paying, setPaying] = useState(false)
  const payBusy = useRef(false)
  const payKeys = useRef<Record<number, string>>({})
  const [joining, setJoining] = useState(false)
  const [message, setMessage] = useState<Message>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const keys = useRef<Record<number, string>>({}) // 혜택별 재시도용 키

  if (me.loading) return <Loading />
  if (me.error || !me.data) return <ErrorState error={me.error} onRetry={me.reload} />
  const m = me.data.membership
  const reloadAll = () => { me.reload(); benefits.reload(); tx.reload(); used.reload() }

  const join = async () => {
    if (joining) return
    setJoining(true)
    try { await api('/membership/join', { method: 'POST' }); reloadAll() }
    catch (err) { setMessage({ type: 'error', text: (err as ApiError).message }) }
    finally { setJoining(false) }
  }

  const redeem = async (b: Benefit) => {
    if (!window.confirm(`${b.name}에 ${b.required_points.toLocaleString()}P를 사용할까요?`)) return
    keys.current[b.id] ??= newIdempotencyKey()
    setBusyId(b.id); setMessage(null)
    try {
      const d = await api<{ redemption: Redemption }>(`/membership/benefits/${b.id}/redeem`, {
        method: 'POST', headers: { 'Idempotency-Key': keys.current[b.id] },
      })
      delete keys.current[b.id] // 성공했으니 다음 사용은 새 키
      setMessage({ type: 'ok', text: `사용 완료 · 쿠폰 번호 ${d.redemption.code}` })
      reloadAll()
    } catch (err) {
      const ex = err as ApiError
      // 결과를 모르는 경우(네트워크·5xx)만 같은 키로 재시도, 나머지는 새 요청
      if (ex.status !== 0 && ex.status < 500) delete keys.current[b.id]
      setMessage({ type: 'error', text: ex.message })
    } finally { setBusyId(null) }
  }

  const currentRank = m.joined ? Math.min(m.tier.rank, 2) : 0
  const currentName = m.joined ? customerMembershipName(m.tier.name, currentRank) : '일반유저'
  const tiers = (m.joined ? m.tiers : catalog.data?.tiers ?? [])
    .filter(t => t.rank >= 0 && t.rank < 3)
    .map(t => ({ ...t, name: customerMembershipName(t.name, t.rank) }))
  const currentRate = tiers.find(t => t.rank === currentRank)?.earn_rate_bp ?? (m.joined ? m.tier.earn_rate_bp : 0)
  const upgrade = async (rank: number, purchaseId?: number) => {
    if (payBusy.current) return
    if (!m.joined) { setMessage({ type: 'error', text: '먼저 무료 멤버십에 가입하세요.' }); return }
    payBusy.current = true; setPaying(true); setMessage(null)
    payKeys.current[rank] ??= newIdempotencyKey()
    try {
      const d = await api<{ purchase: Purchase; redirect_url: string | null }>(`/membership/upgrades/kakaopay/${purchaseId ? 'resume' : 'ready'}`, {
        method: 'POST', headers: { 'Idempotency-Key': payKeys.current[rank] },
        body: purchaseId ? { purchase_id: purchaseId } : { rank },
      })
      if (d.purchase.status === 'SUCCEEDED') { me.reload(); purchases.reload(); return }
      const url = new URL(d.redirect_url || '')
      if (url.protocol !== 'https:' || url.username || url.password) throw new Error('결제창 주소를 확인할 수 없습니다.')
      window.location.assign(url.href)
    } catch (err) {
      setMessage({ type: 'error', text: (err as Error).message }); purchases.reload()
    } finally { payBusy.current = false; setPaying(false) }
  }
  const cancelPurchase = async (id: number) => {
    if (payBusy.current) return
    payBusy.current = true; setPaying(true)
    try {
      await api('/membership/upgrades/kakaopay/abort', { method: 'POST', body: { purchase_id: id } })
      payKeys.current = {}; purchases.reload()
    } catch (err) { setMessage({ type: 'error', text: (err as Error).message }) }
    finally { payBusy.current = false; setPaying(false) }
  }
  const unresolved = purchases.data?.purchases.find(p => ['PENDING', 'PREPARING', 'APPROVING', 'REVIEW', 'REFUND_REQUIRED'].includes(p.status))

  return (
    <section className="page membership-page">
      <header className="page__header"><div><h1 className="page__title"><Logo variant="plus" size="md" /> 멤버십</h1><p className="muted">나의 포인트와 등급별 혜택을 한곳에서 확인하세요.</p></div></header>
      {message && <div className={`notice ${message.type === 'ok' ? 'notice--ok' : 'notice--warn'}`} role="status">{message.text}</div>}
      <div className="membership-columns">
        <div className="membership-content">
          <article className="panel panel--hero membership-points">
            <header className="panel__head"><h2>사용 가능한 포인트</h2><span className="tag tag--info">{currentName}{!m.joined && ' · 미가입'}</span></header>
            <p className="membership-points__balance">{m.joined ? m.point_balance.toLocaleString() : '0'}<small>P</small></p>
            <p className="muted">{m.joined ? `요금 납부 시 ${currentRate / 100}% 적립` : '무료로 가입하고 멤버십 혜택을 만나보세요.'}</p>
            {m.joined ? <Link to="/membership/shop" className="text-link">포인트 상점 가기 →</Link> : <button type="button" className="btn" disabled={joining} onClick={join}>{joining ? '가입 중' : '무료로 가입하기'}</button>}
          </article>

          <section aria-label="멤버십 등급 업그레이드" className="membership-upgrades">
            <header className="membership-section-head"><h2>나에게 맞는 멤버십</h2><p className="muted">Plus 14,900원 · VIP 29,900원. 한 번 결제하면 영구 유지됩니다.</p></header>
            {!m.joined && catalog.loading ? <Loading label="등급 안내 불러오는 중" /> : !m.joined && catalog.error ? <ErrorState error={catalog.error} onRetry={catalog.reload} /> : <div className="membership-upgrade-grid">
              {tiers.map(t => <article key={t.rank} className={`membership-upgrade-card ${m.joined && t.rank === currentRank ? 'membership-upgrade-card--current' : ''}`}>
                <header><h3>{t.name}</h3>{m.joined && t.rank === currentRank && <span className="tag tag--info">현재 등급</span>}</header>
                <p className="membership-upgrade-card__rate">{t.earn_rate_bp / 100}<span>% 적립</span></p>
                <p className="muted">요금 납부 시 포인트 적립</p>
                <span className="membership-upgrade-card__price">{t.rank === 0 ? '기본 멤버십' : `${won(t.rank === 1 ? 14900 : 29900)} · 1회 결제`}</span>
                <button type="button" className={t.rank > currentRank ? 'btn' : 'btn btn--ghost'} disabled={t.rank <= currentRank || paying || !!unresolved || purchases.loading || !!purchases.error} onClick={() => upgrade(t.rank)}>{t.rank === currentRank ? m.joined ? '이용 중' : '기본 등급' : t.rank < currentRank ? '하위 등급' : paying ? '결제 준비 중…' : '카카오페이로 업그레이드'}</button>
              </article>)}
            </div>}
            <p className="muted membership-payment-note">카카오페이 승인 완료 후 등급이 적용됩니다. 자동 갱신은 없으며 포인트는 차감하지 않습니다. Plus에서 VIP로 업그레이드할 때는 29,900원 전액을 결제합니다.</p>
            {purchases.error && <ErrorState error={purchases.error} onRetry={purchases.reload} />}
            {unresolved && <div className="notice notice--warn" role="status"><p>{unresolved.name} · {won(unresolved.amount)} · {unresolved.status === 'PENDING' ? '진행 중인 결제가 있습니다.' : '결제 결과를 확인 중입니다. 재결제하지 말고 관리자에게 문의하세요.'}</p>{unresolved.status === 'PENDING' && <><button className="btn btn--sm" disabled={paying} onClick={() => upgrade(unresolved.name === 'Plus' ? 1 : 2, unresolved.id)}>결제 이어하기</button> <button className="btn btn--ghost btn--sm" disabled={paying} onClick={() => cancelPurchase(unresolved.id)}>결제 취소</button></>}</div>}
          </section>

          {!m.joined ? <article className="panel"><h2>L∞P+ 회원이 되면</h2><ul className="checklist"><li>가입 즉시 1,000P 적립</li><li>등급에 따른 요금 납부 포인트 적립</li><li>편의점·카페·영화 혜택을 포인트로 사용</li></ul><p className="muted">가입 시 요금제의 월 요금으로 일반유저·Plus·VIP 등급을 정합니다. 가입비는 없습니다.</p></article> : <>
            <section><h2 className="membership-section-title">사용 가능한 혜택</h2>
              {benefits.loading ? <Loading label="혜택 불러오는 중" /> : benefits.error ? <ErrorState error={benefits.error} onRetry={benefits.reload} /> : !benefits.data?.benefits.length ? <p className="muted">현재 등록된 혜택이 없습니다.</p> : <div className="cards">
                {benefits.data.benefits.map(b => <article key={b.id} className={`card ${b.available ? '' : 'card--off'}`}><span className="muted">{b.partner}</span><strong>{b.name}</strong><span className="card__points">{b.required_points.toLocaleString()}P</span><span className="muted">월 {b.monthly_limit}회 · 이번 달 {b.used_this_month}회 사용</span><button className="btn" disabled={!b.available || busyId === b.id} onClick={() => redeem(b)}>{b.available ? busyId === b.id ? '처리 중' : '사용하기' : b.unavailable_reason?.replace(/Admin/gi, 'VIP')}</button></article>)}
              </div>}
            </section>
            <article className="panel"><h2>최근 사용한 혜택</h2>{used.loading ? <Loading label="사용 내역 불러오는 중" /> : used.error ? <ErrorState error={used.error} onRetry={used.reload} /> : used.data?.redemptions.length ? <ul className="list">{used.data.redemptions.slice(0, 4).map(r => <li key={r.id}><span>{r.benefit}</span><span className="mono">{r.code}</span></li>)}</ul> : <p className="muted">아직 사용한 혜택이 없습니다.</p>}</article>
            <section><h2 className="membership-section-title">포인트 내역</h2>{tx.loading ? <Loading label="포인트 내역 불러오는 중" /> : tx.error ? <ErrorState error={tx.error} onRetry={tx.reload} /> : !tx.data?.transactions.length ? <p className="muted">포인트 내역이 없습니다.</p> : <div className="table-wrap"><table className="table"><thead><tr><th>일시</th><th>내용</th><th>구분</th><th className="num">포인트</th><th className="num">잔액</th></tr></thead><tbody>{tx.data.transactions.map(t => <tr key={t.id}><td>{dateTime(t.created_at)}</td><td>{t.memo?.replace(/Admin/gi, 'VIP')}</td><td>{KIND[t.kind] ?? t.kind}</td><td className={`num ${t.amount < 0 ? 'minus' : 'plus'}`}>{t.amount > 0 ? '+' : ''}{t.amount.toLocaleString()}</td><td className="num">{t.balance_after.toLocaleString()}</td></tr>)}</tbody></table></div>}</section>
          </>}
        </div>
        <aside className="membership-rate-sidebar" aria-label="등급별 적립률 안내">
          <div className="panel"><h2>등급별 적립률</h2>{!m.joined && catalog.loading ? <Loading label="등급 불러오는 중" /> : !m.joined && catalog.error ? <ErrorState error={catalog.error} onRetry={catalog.reload} /> : <table className="table membership-rate-table"><thead><tr><th>등급</th><th className="num">납부 적립</th></tr></thead><tbody>{tiers.map(t => <tr key={t.rank} className={m.joined && t.rank === currentRank ? 'row--current' : ''}><td><strong>{t.name}</strong><small>{t.min_monthly_fee ? `가입 시 월 ${won(t.min_monthly_fee)} 이상` : '누구나 가입'}</small></td><td className="num">{t.earn_rate_bp / 100}%</td></tr>)}</tbody></table>}<p className="muted">요금 납부 금액을 기준으로 적립합니다. 소수점 이하는 버립니다.</p></div>
        </aside>
      </div>
    </section>
  )
}
