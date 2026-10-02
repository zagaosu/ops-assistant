import { useEffect, useState } from 'react'
import './App.css'

type Ticket = {
  id: number
  title: string
  status: string
  priority: string
  created_at: string
  owner: string
}

type Session = {
  id: number
  title: string
  created_at: string
}

type Message = {
  role: string
  content: string
}

type Draft = {
  id: number
  title: string
  content: string
  version: number
  status: string
  created_ticket_id: number | null
  created_at: string
}

const STATUS_TEXT: Record<string, string> = {
  open: '待处理',
  in_progress: '处理中',
  closed: '已关闭',
}

const PRIORITY_TEXT: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
}

function App() {
  // 登录状态存在 localStorage：刷新页面后还在（这就是"刷新恢复"）
  const [token, setToken] = useState(localStorage.getItem('ops_token') || '')
  const [username, setUsername] = useState(localStorage.getItem('ops_username') || '')

  const [loginUser, setLoginUser] = useState('user1')
  const [loginPass, setLoginPass] = useState('ops123')
  const [loginError, setLoginError] = useState('')

  const [sessions, setSessions] = useState<Session[]>([])
  const [current, setCurrent] = useState<Session | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [chatError, setChatError] = useState('')

  const [tickets, setTickets] = useState<Ticket[]>([])
  const [statusFilter, setStatusFilter] = useState('all')
  const [priorityFilter, setPriorityFilter] = useState('all')
  const [ticketError, setTicketError] = useState('')

  const [drafts, setDrafts] = useState<Draft[]>([])
  const [draftTitle, setDraftTitle] = useState('')
  const [draftContent, setDraftContent] = useState('')
  const [draftMsg, setDraftMsg] = useState('')

  function logout() {
    localStorage.removeItem('ops_token')
    localStorage.removeItem('ops_username')
    setToken('')
    setUsername('')
    setSessions([])
    setCurrent(null)
    setMessages([])
  }

  // 统一请求入口：自动带令牌；遇到 401 自动登出
  async function api(path: string, options: RequestInit = {}) {
    const res = await fetch(path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {}),
      },
    })
    if (res.status === 401) {
      logout()
      throw new Error('unauthorized')
    }
    if (!res.ok) throw new Error(String(res.status))
    return res.json()
  }

  useEffect(() => {
    if (!token) return
    // 刷新后自动恢复：拿 localStorage 里的令牌重新拉数据
    api('/api/sessions').then((d) => setSessions(d.items)).catch(() => {})
    api('/api/tickets')
      .then((d) => {
        setTickets(d.items)
        setTicketError('') // 加载成功要把旧的错误提示擦掉
      })
      .catch(() => setTicketError('工单加载失败：确认后端在运行'))
    loadDrafts().catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  async function handleLogin() {
    setLoginError('')
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: loginUser, password: loginPass }),
      })
      if (res.status === 401) {
        setLoginError('用户名或密码错误')
        return
      }
      if (!res.ok) throw new Error(String(res.status))
      const d = await res.json()
      localStorage.setItem('ops_token', d.token)
      localStorage.setItem('ops_username', d.username)
      setToken(d.token)
      setUsername(d.username)
    } catch {
      setLoginError('登录失败：确认后端在 8000 端口运行')
    }
  }

  async function createSession() {
    try {
      const s = await api('/api/sessions', { method: 'POST', body: JSON.stringify({}) })
      setSessions((list) => [s, ...list])
      openSession(s)
    } catch {
      setChatError('创建会话失败')
    }
  }

  async function openSession(s: Session) {
    setCurrent(s)
    setChatError('')
    try {
      const d = await api(`/api/sessions/${s.id}`)
      setMessages(d.messages)
    } catch {
      setChatError('会话加载失败')
    }
  }

  async function handleAsk() {
    if (!current || !question.trim() || asking) return
    const q = question.trim()
    setQuestion('')
    setAsking(true)
    setChatError('')
    setMessages((m) => [...m, { role: 'user', content: q }])
    try {
      const d = await api(`/api/sessions/${current.id}/ask`, {
        method: 'POST',
        body: JSON.stringify({ question: q }),
      })
      setMessages((m) => [...m, { role: 'assistant', content: d.answer }])
      // 后端可能把会话标题改成了第一条问题，刷新一下列表
      api('/api/sessions')
        .then((r) => {
          setSessions(r.items)
          const updated = r.items.find((s: Session) => s.id === current.id)
          if (updated) setCurrent(updated)
        })
        .catch(() => {})
      // Agent 可能在对话里生成了草稿，刷新一下草稿区
      loadDrafts().catch(() => {})
    } catch {
      setChatError('提问失败：确认后端和 Ollama 都在运行')
    } finally {
      setAsking(false)
    }
  }

  // ---- 工单草稿 ----
  async function loadDrafts() {
    const d = await api('/api/drafts')
    setDrafts(d.items)
  }

  async function saveDraft() {
    if (!draftTitle.trim() || !draftContent.trim()) return
    setDraftMsg('')
    try {
      await api('/api/drafts', {
        method: 'POST',
        body: JSON.stringify({ title: draftTitle.trim(), content: draftContent.trim() }),
      })
      setDraftTitle('')
      setDraftContent('')
      await loadDrafts()
    } catch {
      setDraftMsg('存草稿失败')
    }
  }

  async function confirmDraft(d: Draft) {
    setDraftMsg('')
    try {
      const r = await api(`/api/drafts/${d.id}/confirm`, {
        method: 'POST',
        body: JSON.stringify({ version: d.version }),
      })
      setDraftMsg(
        r.already_confirmed
          ? `草稿 #${d.id} 之前已确认过 → 返回原工单 #${r.ticket.id}（没有重复建单）`
          : `草稿 #${d.id} 已建单 → 新工单 #${r.ticket.id}`,
      )
      await loadDrafts()
      const t = await api('/api/tickets')
      setTickets(t.items)
    } catch {
      setDraftMsg('确认失败')
    }
  }

  async function cancelDraft(d: Draft) {
    setDraftMsg('')
    try {
      await api(`/api/drafts/${d.id}/cancel`, { method: 'POST' })
      await loadDrafts()
    } catch {
      setDraftMsg('取消失败')
    }
  }

  // ---------- 未登录：登录卡片 ----------
  if (!token) {
    return (
      <main className="page">
        <div className="login-card">
          <h1>设备运维助手</h1>
          <p className="login-hint">测试账户：user1 / user2，密码都是 ops123</p>
          <input
            value={loginUser}
            onChange={(e) => setLoginUser(e.target.value)}
            placeholder="用户名"
          />
          <input
            type="password"
            value={loginPass}
            onChange={(e) => setLoginPass(e.target.value)}
            placeholder="密码"
            onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
          />
          <button onClick={handleLogin}>登录</button>
          {loginError && <p className="error">{loginError}</p>}
        </div>
      </main>
    )
  }

  // ---------- 已登录：会话 + 聊天 + 工单 ----------
  return (
    <main className="page">
      <div className="app-header">
        <h1>设备运维助手</h1>
        <div>
          <span className="who">{username}</span>
          <button className="ghost" onClick={logout}>退出登录</button>
        </div>
      </div>

      <div className="chat-layout">
        <aside className="session-list">
          <button className="new-session" onClick={createSession}>+ 新会话</button>
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`session-item ${current?.id === s.id ? 'active' : ''}`}
              onClick={() => openSession(s)}
            >
              <div className="session-title">{s.title}</div>
              <div className="session-time">{s.created_at}</div>
            </div>
          ))}
          {sessions.length === 0 && <p className="side-hint">还没有会话，点上面新建一个</p>}
        </aside>

        <section className="chat-panel">
          {!current && <p className="side-hint">左边选一个会话，或新建一个</p>}
          {current && (
            <>
              <div className="messages">
                {messages.map((m, i) => (
                  <div key={i} className={`msg msg-${m.role}`}>{m.content}</div>
                ))}
                {messages.length === 0 && <p className="side-hint">这个会话还没有消息</p>}
              </div>
              <div className="ask-row">
                <input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
                  placeholder="例如：还有哪些工单没关闭？"
                />
                <button onClick={handleAsk} disabled={asking}>
                  {asking ? '思考中…' : '发送'}
                </button>
              </div>
              {chatError && <p className="error">{chatError}</p>}
            </>
          )}
        </section>
      </div>

      <section className="drafts">
        <h2>工单草稿</h2>
        <div className="draft-form">
          <input
            value={draftTitle}
            onChange={(e) => setDraftTitle(e.target.value)}
            placeholder="标题，如：3 号泵水温过高"
          />
          <input
            value={draftContent}
            onChange={(e) => setDraftContent(e.target.value)}
            placeholder="现象 / 内容"
          />
          <button onClick={saveDraft}>存为草稿</button>
        </div>
        <p className="side-hint">也可以直接在对话里让 Agent 生成草稿（它会出现在这里）</p>
        {draftMsg && <p className="draft-msg">{draftMsg}</p>}
        <ul className="draft-list">
          {drafts.map((d) => (
            <li key={d.id}>
              <div className="draft-head">
                <span className="title">{d.title}</span>
                <span className={`status status-${d.status}`}>
                  {d.status === 'pending' ? '待确认' : d.status === 'confirmed' ? '已建单' : '已取消'}
                </span>
              </div>
              <p className="draft-content">{d.content}</p>
              {d.status === 'pending' && (
                <div className="draft-actions">
                  <button onClick={() => confirmDraft(d)}>确认建单</button>
                  <button className="ghost" onClick={() => cancelDraft(d)}>取消</button>
                </div>
              )}
              {d.status === 'confirmed' && (
                <span className="draft-note">已建单 #{d.created_ticket_id}——重复点"确认"不会新建</span>
              )}
              {d.status === 'cancelled' && (
                <span className="draft-note">已取消——没有写入任何工单</span>
              )}
            </li>
          ))}
          {drafts.length === 0 && <p className="side-hint">还没有草稿</p>}
        </ul>
      </section>

      <section className="tickets">
        <h2>工单列表</h2>
        <div className="ticket-filters">
          <button className={statusFilter === 'all' ? 'active' : ''} onClick={() => setStatusFilter('all')}>全部</button>
          <button className={statusFilter === 'open' ? 'active' : ''} onClick={() => setStatusFilter('open')}>待处理</button>
          <button className={statusFilter === 'closed' ? 'active' : ''} onClick={() => setStatusFilter('closed')}>已关闭</button>
        </div>
        <div className="ticket-filters">
          <button className={priorityFilter === 'all' ? 'active' : ''} onClick={() => setPriorityFilter('all')}>全部优先级</button>
          <button className={priorityFilter === 'high' ? 'active' : ''} onClick={() => setPriorityFilter('high')}>高</button>
          <button className={priorityFilter === 'medium' ? 'active' : ''} onClick={() => setPriorityFilter('medium')}>中</button>
          <button className={priorityFilter === 'low' ? 'active' : ''} onClick={() => setPriorityFilter('low')}>低</button>
        </div>
        {ticketError && <p className="error">{ticketError}</p>}
        <ul className="ticket-list">
          {tickets
            .filter((t) => statusFilter === 'all' || t.status === statusFilter)
            .filter((t) => priorityFilter === 'all' || t.priority === priorityFilter)
            .map((t) => (
            <li key={t.id}>
              <span className="title">#{t.id} {t.title}</span>
              <span className={`status status-${t.status}`}>
                {STATUS_TEXT[t.status] ?? t.status}
              </span>
              <span className={`priority priority-${t.priority}`}>
                {PRIORITY_TEXT[t.priority] ?? t.priority}
              </span>
              <span className="time">{t.created_at}</span>
              <span className="time">{t.owner}</span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  )
}

export default App
