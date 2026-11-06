import { LoaderCircle, X, CircleAlert } from 'lucide-react'

export function Status({ value }) {
  return <span className={`status ${['delivered', 'completed', 'ok'].includes(value) ? 'good' : ['cancelled', 'rejected', 'error'].includes(value) ? 'muted' : ''}`}><span />{value.replaceAll('_', ' ')}</span>
}

export function Busy({ text = 'Loading…' }) { return <span className="inline-flex items-center gap-2"><LoaderCircle size={16} className="animate-spin" />{text}</span> }
export function ErrorNotice({ message }) { return message ? <div role="alert" className="notice error"><CircleAlert size={17} /><span>{message}</span></div> : null }
export function Modal({ title, children, close, busy }) {
  return <div className="modal-backdrop" onClick={busy ? undefined : close}><section className="modal" role="dialog" aria-modal="true" aria-label={title} onClick={e => e.stopPropagation()}><header><h2>{title}</h2><button className="icon-button" onClick={close} disabled={busy} aria-label="Close dialog"><X size={20} /></button></header>{children}</section></div>
}
export const money = (minor, currency) => new Intl.NumberFormat('en-IN', { style: 'currency', currency }).format(minor / 100)
export const date = value => value ? new Date(value.endsWith('Z') || value.includes('+') ? value : value.replace(' ', 'T') + 'Z').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : 'Not available'
