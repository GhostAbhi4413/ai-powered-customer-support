import { useEffect, useState } from 'react'
import { Package, Headphones, LayoutDashboard, ArrowUpRight, Truck, RefreshCw, MapPin, Undo2, Ban, ChevronRight, Settings2, CheckCircle2, Search } from 'lucide-react'
import { request } from './api'
import { Busy, ErrorNotice, Modal, Status, money, date } from './components'
import Chat from './Chat'

export default function App() {
  const [customerId, setCustomerId] = useState('1')
  const [activeId, setActiveId] = useState('1')
  const [customer, setCustomer] = useState(null)
  const [orders, setOrders] = useState([])
  const [order, setOrder] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [modal, setModal] = useState(null)
  const [actionError, setActionError] = useState('')
  const [saving, setSaving] = useState(false)
  const [address, setAddress] = useState('')
  const [reason, setReason] = useState('')
  const [quantities, setQuantities] = useState({})
  const [connection, setConnection] = useState(false)
  const [health, setHealth] = useState(false)

  const api = (path, options = {}) => request(path, options)
  async function load(id = activeId, selectedId = order?.id) {
    setBusy(true); setError('')
    try {
      const [c, list] = await Promise.all([api(`/customers/${id}`), api(`/customers/${id}/orders`)])
      const selected = list.find(o => o.id === selectedId) || list[0]
      const detail = selected ? await api(`/customers/${id}/orders/${selected.id}`) : null
      setCustomer(c); setOrders(list); setOrder(detail); setActiveId(id)
    } catch (e) { setError(e.message); setCustomer(null); setOrders([]); setOrder(null) } finally { setBusy(false) }
  }
  useEffect(() => { load('1'); request('/health', { timeout: 10000 }).then(() => setHealth(true)).catch(() => setHealth(false)) }, [])
  async function selectOrder(id) {
    setBusy(true); setError(''); setSuccess('')
    try { setOrder(await api(`/customers/${activeId}/orders/${id}`)) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  function openAction(type) {
    setModal(type); setActionError(''); setAddress(order.delivery_address); setReason(''); setQuantities({}); setSuccess('')
  }
  async function submitAction(event) {
    event.preventDefault()
    if (saving) return
    const base = `/customers/${activeId}/orders/${order.id}`
    let path, body, method = 'POST'
    if (modal === 'address') {
      if (!address.trim()) return setActionError('Enter a delivery address.')
      path = `${base}/delivery-address`; body = { delivery_address: address.trim() }; method = 'PATCH'
    } else if (modal === 'return') {
      const items = order.items.filter(i => Number(quantities[i.id]) > 0).map(i => ({ order_item_id: i.id, quantity: Number(quantities[i.id]) }))
      if (!reason.trim() || !items.length) return setActionError('Add a reason and select at least one item quantity.')
      if (items.some(i => !Number.isInteger(i.quantity) || i.quantity > order.items.find(o => o.id === i.order_item_id).quantity)) return setActionError('Choose a valid quantity for each item.')
      path = `${base}/returns`; body = { reason: reason.trim(), items }
    } else { path = `${base}/cancel` }
    setSaving(true); setActionError('')
    try {
      await api(path, { method, body })
      setModal(null); setSuccess(modal === 'return' ? 'Return request submitted. Your items are awaiting review.' : modal === 'address' ? 'Delivery address updated.' : 'Order cancelled successfully.')
      await load()
    } catch (e) { setActionError(e.message) } finally { setSaving(false) }
  }
  const total = order?.items.reduce((sum, i) => sum + i.quantity * i.unit_price_minor, 0) || 0
  return <div className="app-shell"><aside className="sidebar"><a className="brand" href="/"><span><Headphones size={23} /></span>support<span className="brand-light">desk</span><i /></a><p className="nav-label">YOUR WORKSPACE</p><nav><a className="nav-active" href="#orders"><LayoutDashboard size={18} />Overview<span>01</span></a><a href="#orders"><Package size={18} />Orders</a><a href="#assistant"><Headphones size={18} />Support assistant<ArrowUpRight size={14} /></a></nav><div className="sidebar-bottom"><div className="care-icon"><Headphones size={23} /></div><h3>Good support.<br />Less effort.</h3><p>Everything you need to keep your orders moving.</p><div className="sidebar-status"><span className={health ? 'dot' : 'dot offline'} />{health ? 'Backend connected' : 'Checking connection'}</div></div></aside>
    <main><header className="topbar"><div className="breadcrumb">Workspace<ChevronRight size={13} /><strong>Customer overview</strong></div><button className="connection-button" onClick={() => setConnection(!connection)}><Settings2 size={16} />Connection</button><div className="avatar">{customer?.name?.charAt(0) || 'C'}</div></header>
      <div className="page"><div className="page-heading"><div><p className="eyebrow">CUSTOMER CARE, SIMPLIFIED</p><h1>Every order. All taken care of.</h1><p>Track deliveries, make changes, and find the help you need.</p></div><button className="secondary" disabled={busy} onClick={() => load()}><RefreshCw size={15} />Refresh</button></div>
        {connection && <section className="connection-panel"><h2>Connect your workspace</h2><p>Load a customer by ID to view their orders and use the support assistant.</p><form onSubmit={e => { e.preventDefault(); if (/^[1-9]\d*$/.test(customerId)) { setConnection(false); setSuccess(''); load(customerId) } }}><label>Customer ID<input type="number" min="1" step="1" required value={customerId} onChange={e => setCustomerId(e.target.value)} /></label><button className="primary" disabled={busy}>Connect</button></form></section>}
        <ErrorNotice message={error} />{success && <div className="notice success" role="status"><CheckCircle2 size={18} />{success}</div>}
        <div className="summary-grid"><div className="summary-card"><span className="summary-icon"><Package size={20} /></span><div><p>Total orders</p><strong>{orders.length.toString().padStart(2, '0')}</strong></div><span className="summary-hint">All time</span></div><div className="summary-card"><span className="summary-icon"><Truck size={20} /></span><div><p>On the way</p><strong>{orders.filter(o => o.status === 'shipped').length.toString().padStart(2, '0')}</strong></div><span className="summary-hint">In transit</span></div><div className="summary-card"><span className="summary-icon"><CheckCircle2 size={20} /></span><div><p>Delivered</p><strong>{orders.filter(o => o.status === 'delivered').length.toString().padStart(2, '0')}</strong></div><span className="summary-hint">Completed</span></div></div>
        <div className="workspace-grid"><div id="orders" className="order-column"><section className="panel order-list"><div className="section-heading"><div><h2>Your orders <span className="count">{orders.length}</span></h2><p>{customer ? `${customer.name} · ${customer.email}` : 'Connect to view your customer details'}</p></div><Search size={18} /></div>{busy && <div className="loading-line"><Busy text="Loading orders…" /></div>}{!orders.length && !busy && <div className="empty"><Package size={25} /><h3>No orders to show</h3><p>{error ? 'Check your connection and try again.' : 'Orders for this customer will appear here.'}</p><button className="secondary" onClick={() => setConnection(true)}>Connect customer</button></div>}{orders.length > 0 && <div className="table-wrap"><table><thead><tr><th>Order</th><th>Placed on</th><th>Status</th><th /></tr></thead><tbody>{orders.map(o => <tr key={o.id} className={order?.id === o.id ? 'selected' : ''}><td><button disabled={busy} className="order-link" onClick={() => selectOrder(o.id)}><span className="package-small"><Package size={17} /></span>{o.order_number}</button></td><td>{date(o.created_at)}</td><td><Status value={o.status} /></td><td><button className="icon-button" disabled={busy} aria-label={`View ${o.order_number}`} onClick={() => selectOrder(o.id)}><ChevronRight size={17} /></button></td></tr>)}</tbody></table></div>}</section>
          {order && <section className="panel order-detail"><div className="section-heading"><div><p className="eyebrow">ORDER DETAILS</p><h2>{order.order_number}</h2></div><Status value={order.status} /></div><div className="item-list">{order.items.map(item => <div className="item" key={item.id}><span className="item-image"><Package size={26} strokeWidth={1.4} /></span><div><h3>{item.product_name}</h3><p>{item.sku} <span>·</span> Qty {item.quantity}</p></div><strong>{money(item.quantity * item.unit_price_minor, order.currency)}</strong></div>)}</div><div className="total"><span>Order total</span><strong>{money(total, order.currency)}</strong></div><div className="delivery-grid"><div><h3><MapPin size={16} />Delivery address</h3><p className="address">{order.delivery_address}</p></div><div><h3><Truck size={17} />Shipping details</h3>{order.shipments.length ? order.shipments.map(s => <div className="shipment" key={s.id}><strong>{s.carrier}</strong><p>{s.tracking_reference}</p><Status value={s.status} /><p className="small">{s.delivered_at ? `Delivered ${date(s.delivered_at)}` : s.estimated_delivery_at ? `Expected ${date(s.estimated_delivery_at)}` : 'Delivery estimate not available'}</p></div>) : <p>Shipping information will appear after dispatch.</p>}</div></div><div className="order-actions"><button className="secondary" disabled={busy} onClick={() => openAction('address')}><MapPin size={15} />Update address</button><button className="secondary" disabled={busy} onClick={() => openAction('return')}><Undo2 size={15} />Request return</button><button className="text-danger" disabled={busy} onClick={() => openAction('cancel')}><Ban size={15} />Cancel order</button></div>{order.returns.length > 0 && <div className="return-history"><h3>Return requests</h3>{order.returns.map(r => <div key={r.id}><span>#{r.id} · {r.reason}</span><Status value={r.status} /></div>)}</div>}</section>}
        </div><div id="assistant"><Chat key={activeId} customerId={activeId} onChange={() => load()} /></div></div><footer className="page-footer"><span><Headphones size={13} />A clearer view. A smoother experience.</span><span>Support Desk · Customer workspace</span></footer>
      </div>
    </main>
    {modal && <Modal title={modal === 'return' ? 'Request a return' : modal === 'address' ? 'Update delivery address' : 'Cancel this order?'} busy={saving} close={() => !saving && setModal(null)}><form onSubmit={submitAction}><p className="modal-description">{modal === 'return' ? 'Select the items you want to return. Eligibility and quantities are checked before your request is accepted.' : modal === 'address' ? 'Address changes are available before dispatch. Review the full address before saving.' : `We will check the purchase date, current status, shipping activity, and return records for ${order.order_number}.`}</p>{modal === 'address' && <label>Full delivery address<textarea rows={4} required maxLength={1000} value={address} onChange={e => setAddress(e.target.value)} /></label>}{modal === 'return' && <><label>Reason for return<textarea required maxLength={1000} rows={3} placeholder="Tell us what went wrong" value={reason} onChange={e => setReason(e.target.value)} /></label><div className="return-items">{order.items.map(i => <label key={i.id}><span>{i.product_name}<small>Purchased: {i.quantity}</small></span><input aria-label={`Return quantity for ${i.product_name}`} type="number" min="0" max={i.quantity} step="1" value={quantities[i.id] || 0} onChange={e => setQuantities(prev => ({ ...prev, [i.id]: e.target.value }))} /></label>)}</div></>}<ErrorNotice message={actionError} /><div className="modal-actions"><button type="button" className="secondary" onClick={() => setModal(null)} disabled={saving}>Keep order unchanged</button><button className={modal === 'cancel' ? 'danger' : 'primary'} disabled={saving}>{saving ? <Busy text="Saving…" /> : modal === 'return' ? 'Submit return request' : modal === 'address' ? 'Save address' : 'Confirm cancellation'}</button></div></form></Modal>}
  </div>
}
