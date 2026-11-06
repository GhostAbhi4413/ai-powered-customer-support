import { useState } from 'react'
import { Sparkles, ArrowUp, ShieldCheck, Check, X } from 'lucide-react'
import { request } from './api'
import { Busy, ErrorNotice, Status } from './components'

export default function Chat({ customerId, onChange }) {
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(null)
  const [retryId, setRetryId] = useState(null)
  async function send(event) {
    event.preventDefault()
    if (!text.trim() || busy || pending) return
    const message = text.trim()
    const id = retryId || crypto.randomUUID()
    setBusy(true); setError('')
    try {
      const data = await request('/agent/chat', { method: 'POST', body: { request_id: id, customer_id: Number(customerId), message } })
      setMessages(prev => [...prev, { role: 'user', text: message }, { role: 'assistant', text: data.message, tools: data.tools }])
      if (data.action?.state === 'pending') setPending(data.action)
      setText(''); setRetryId(null)
    } catch (e) { setError(e.message); setRetryId(id) } finally { setBusy(false) }
  }
  async function confirm(approve) {
    setBusy(true); setError('')
    try {
      const result = await request(`/agent/actions/${pending.action_id}/confirm`, { method: 'POST', body: { customer_id: Number(customerId), approve } })
      setMessages(prev => [...prev, { role: 'assistant', text: result.status === 'ok' ? 'Your change was completed successfully.' : result.detail, tools: [result] }])
      setPending(null)
      if (result.status === 'ok') onChange()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <section className="chat-card"><header className="chat-heading"><div className="spark"><Sparkles size={19} /></div><div><h2>Support assistant</h2><p>Help with every step of your order</p></div><span className="ai-label">AI</span></header>
    <div className="chat-content" aria-live="polite">
      {!messages.length && <div className="chat-welcome"><div className="welcome-icon"><Sparkles size={26} /></div><h3>A little help, right here.</h3><p>Ask about an order, track a delivery, or get help making a change.</p><div className="suggestions">{['What is the status of order 1?', 'Show my shipping details'].map(s => <button key={s} onClick={() => { setText(s); setRetryId(null) }}>{s}<ArrowUp size={13} /></button>)}</div></div>}
      {messages.map((m, i) => <div key={i} className={`message ${m.role}`}><span className="message-label">{m.role === 'user' ? 'You' : 'Support assistant'}</span><p>{m.text}</p>{m.tools?.length > 0 && <div className="tool-evidence">{m.tools.map((t, j) => <div key={j}><span>{t.tool.replaceAll('_', ' ')}</span><Status value={t.status} /></div>)}</div>}</div>)}
      {pending && <div className="approval"><h3><ShieldCheck size={18} />Review proposed change</h3><p>{pending.tool.replaceAll('_', ' ')}</p><pre>{JSON.stringify(pending.arguments, null, 2)}</pre><div className="flex gap-2"><button className="primary" disabled={busy} onClick={() => confirm(true)}><Check size={15} />Approve</button><button className="secondary" disabled={busy} onClick={() => confirm(false)}><X size={15} />Reject</button></div></div>}
    </div>
    <div className="chat-footer"><ErrorNotice message={error} />{busy && <p className="small"><Busy text="Working on your request…" /></p>}<form onSubmit={send}><textarea aria-label="Message support assistant" rows={2} maxLength={4000} value={text} disabled={busy || !!pending} onChange={e => { setText(e.target.value); setRetryId(null) }} placeholder="Ask about your order…" /><button aria-label="Send message" disabled={!text.trim() || busy || !!pending}><ArrowUp size={19} /></button></form><p><ShieldCheck size={12} />You approve every AI-proposed change.</p></div>
  </section>
}
