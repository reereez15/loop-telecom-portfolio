import { Link } from 'react-router-dom'
import { useRef, useState } from 'react'
import ErrorState from '../../components/common/ErrorState'
import Loading from '../../components/common/Loading'
import Logo from '../../components/common/Logo'
import { ApiError, api } from '../../services/apiClient'
import type { Benefit, Membership, MembershipUpgrade, PointTransaction, Redemption } from '../../services/types'
import { dateTime, won } from '../../utils/format'
import { newIdempotencyKey } from '../../utils/idempotency'
import { useApi } from '../../utils/useApi'
import { customerMembershipName } from '../../utils/membership'

const KIND: Record<string, string> = { EARN: '적립', REDEEM: '사용', REVERSE: '취소' }
type Message = { type: 'ok' | 'error'; text: string } | null

export default function MembershipPage() {
  const me = useApi<{ membership: Membership }>('/membership/me')
  const benefits = useApi<{ benefits: Benefit[] }>('/membership/benefits')
  const tx = useApi<{ transactions: PointTransaction[] }>('/membership/transactions')
  const used = useApi<{ redemptions: Redemption[] }>('/membership/redemptions')
  const catalog = useApi<{ tiers: { name: string; rank: number; earn_rate_bp: number; min_monthly_fee: number; price: number }[] }>('/membership/tiers')
  const cards = useApi<{ cards: { number: string; result: string }[] }>('/payments/test-cards')
  const methods = useApi<{ mock_card: boolean; kakaopay: boolean }>('/payments/methods')
  const [joining, setJoining] = useState(false)
  const [message, setMessage] = useState<Message>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const keys = useRef<Record<number, string>>({}) // 혜택별 재시도용 키

  const [upgradingRank, setUpgradingRank] = useState<number | null>(null)
  const [card, setCard] = useState('4242424242424242')
  const [upgradeBusy, setUpgradeBusy] = useState(false)
  const upgradeKey = useRef<string>('')

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

  const openUpgrade = (rank: number) => {
    if (!m.joined) { setMessage({ type: 'error', text: '먼저 L∞P+ 멤버십에 가입하세요.' }); return }
    setUpgradingRank(rank); setMessage(null); upgradeKey.current = newIdempotencyKey()
  }

  const purchaseUpgrade = async (rank: number) => {
    setUpgradeBusy(true); setMessage(null)
    try {
      const d = await api<{ upgrade: MembershipUpgrade }>('/membership/upgrade', {
        method: 'POST', headers: { 'Idempotency-Key': upgradeKey.current },
        body: { tier_rank: rank, card_number: card },
      })
      const u = d.upgrade
      if (u.status === 'SUCCEEDED') {
        setMessage({ type: 'ok', text: `${u.to_tier_name} 등급으로 업그레이드되었습니다. (거래번호 ${u.transaction_ref})` })
        setUpgradingRank(null)
        reloadAll()
      } else {
        setMessage({ type: 'error', text: '결제가 승인되지 않았습니다. 다른 테스트 카드로 다시 시도해 보세요.' })
      }
      upgradeKey.current = newIdempotencyKey() // 결과가 확정됐으니 다음 시도는 새 결제
    } catch (err) {
      const ex = err as ApiError
      setMessage({ type: 'error', text: ex.message })
      // 결과를 모르는 경우(네트워크·5xx)는 같은 키로 다시 눌러야 중복 결제가 생기지 않는다
      if (ex.status !== 0 && ex.status < 500) upgradeKey.current = newIdempotencyKey()
    } finally { setUpgradeBusy(false) }
  }

  const kakaoPayUpgrade = async (rank: number) => {
    setUpgradeBusy(true); setMessage(null)
    try {
      const d = await api<{ redirect_url: string }>('/membership/upgrade/kakaopay/ready', {
        method: 'POST', headers: { 'Idempotency-Key': upgradeKey.current }, body: { tier_rank: rank },
      })
      window.location.assign(d.redirect_url)
    } catch (err) {
      setMessage({ type: 'error', text: (err as ApiError).message })
      setUpgradeBusy(false)
    }
  }

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
            <header className="membership-section-head"><h2>나에게 맞는 멤버십</h2><p className="muted">더 높은 적립률로 혜택을 넓혀보세요. 등급은 1회 결제로 바로 구매할 수 있습니다.</p></header>
            {!m.joined && catalog.loading ? <Loading label="등급 안내 불러오는 중" /> : !m.joined && catalog.error ? <ErrorState error={catalog.error} onRetry={catalog.reload} /> : <div className="membership-upgrade-grid">
              {tiers.map(t => {
                const isCurrent = t.rank === currentRank
                const isLower = t.rank < currentRank
                const purchasable = t.rank > currentRank
                const open = upgradingRank === t.rank
                return (
                  <article key={t.rank} className={`membership-upgrade-card ${isCurrent ? 'membership-upgrade-card--current' : ''}`}>
                    <header><h3>{t.name}</h3>{isCurrent && <span className="tag tag--info">현재 등급</span>}</header>
                    <p className="membership-upgrade-card__rate">{t.earn_rate_bp / 100}<span>% 적립</span></p>
                    <p className="muted">요금 납부 시 포인트 적립</p>
                    <span className="membership-upgrade-card__price">{t.rank === 0 ? '기본 멤버십' : `${won(t.price)} · 1회 결제`}</span>
                    {open ? (
                      <div className="membership-upgrade-form">
                        <label>테스트 카드
                          <select value={card} onChange={(e) => setCard(e.target.value)}>
                            {(cards.data?.cards ?? []).map((c) => (
                              <option key={c.number} value={c.number}>{c.number.replace(/(\d{4})(?=\d)/g, '$1 ')} · {c.result}</option>
                            ))}
                          </select>
                        </label>
                        <div className="row">
                          <button type="button" className="btn" disabled={upgradeBusy} onClick={() => purchaseUpgrade(t.rank)}>{upgradeBusy ? '처리 중' : `${won(t.price)} 결제`}</button>
                          {methods.data?.kakaopay && (
                            <button type="button" className="btn btn--kakao" disabled={upgradeBusy} onClick={() => kakaoPayUpgrade(t.rank)}>카카오페이</button>
                          )}
                          <button type="button" className="btn btn--ghost" disabled={upgradeBusy} onClick={() => setUpgradingRank(null)}>취소</button>
                        </div>
                        <p className="muted">모의 결제입니다. 실제 카드 정보를 입력하지 마세요.</p>
                      </div>
                    ) : (
                      <button type="button" className={purchasable ? 'btn' : 'btn btn--ghost'} disabled={!purchasable} onClick={() => openUpgrade(t.rank)}>
                        {isCurrent ? (m.joined ? '이용 중' : '기본 등급') : isLower ? '하위 등급' : '업그레이드하기'}
                      </button>
                    )}
                  </article>
                )
              })}
            </div>}
          </section>

          {!m.joined ? <article className="panel"><h2>L∞P+ 회원이 되면</h2><ul className="checklist"><li>가입 즉시 1,000P 적립</li><li>등급에 따른 요금 납부 포인트 적립</li><li>편의점·카페·영화 혜택을 포인트로 사용</li></ul><p className="muted">가입 시 요금제의 월 요금으로 일반유저·Plus·VIP 등급을 정합니다. 가입비는 없습니다. 가입 후에는 등급을 직접 구매해 바로 올릴 수도 있습니다.</p></article> : <>
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
