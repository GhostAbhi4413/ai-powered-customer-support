const base = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export async function request(path, { method = 'GET', body, timeout = 210000 } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const response = await fetch(`${base}${path}`, {
      method, signal: controller.signal,
      headers: { ...(body ? { 'Content-Type': 'application/json' } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    })
    let data
    try { data = await response.json() } catch { throw new Error('The server returned an unreadable response. Check the API connection.') }
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status}).`)
    return data
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The request timed out. Refresh before retrying any change.')
    if (error instanceof TypeError) throw new Error('Cannot reach the backend. Check that FastAPI is running.')
    throw error
  } finally { clearTimeout(timer) }
}
