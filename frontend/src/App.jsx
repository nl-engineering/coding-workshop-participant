import React, { useCallback, useEffect, useState } from 'react'
import {
  Alert, AppBar, Badge, Box, Button, Card, CardContent, Chip, CircularProgress, CssBaseline, Dialog, DialogContent,
  Drawer, IconButton, LinearProgress, List, ListItemButton, ListItemIcon, ListItemText, Snackbar, Stack, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, ThemeProvider, ToggleButton, ToggleButtonGroup,
  Toolbar, Typography, createTheme, useMediaQuery,
} from '@mui/material'
import MenuIcon from '@mui/icons-material/Menu'
import InboxIcon from '@mui/icons-material/Inbox'
import ForumIcon from '@mui/icons-material/Forum'
import FactCheckIcon from '@mui/icons-material/FactCheck'
import InsightsIcon from '@mui/icons-material/Insights'
import MenuBookIcon from '@mui/icons-material/MenuBook'
import ScienceIcon from '@mui/icons-material/Science'
import SecurityIcon from '@mui/icons-material/Security'
import SlideshowIcon from '@mui/icons-material/Slideshow'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import { api, ROUTES, STATUS } from './api.js'
import CaseView, { RouteChip } from './CaseView.jsx'
import Present from './Present.jsx'

const theme = createTheme({
  palette: { primary: { main: '#1a56db' }, secondary: { main: '#7c3aed' }, background: { default: '#f4f6fb' } },
  shape: { borderRadius: 10 },
  typography: { fontFamily: 'Roboto, "Segoe UI", system-ui, sans-serif', h5: { fontWeight: 700 } },
  components: { MuiCard: { defaultProps: { variant: 'outlined' } }, MuiButton: { styleOverrides: { root: { textTransform: 'none', fontWeight: 600 } } } },
})
const NAV = [
  ['inbox', 'Inbox', InboxIcon], ['ask', 'Ask AskHR', ForumIcon], ['approvals', 'Approvals', FactCheckIcon],
  ['insights', 'Business impact', InsightsIcon], ['kb', 'Knowledge base', MenuBookIcon], ['evals', 'Evaluation', ScienceIcon],
  ['audit', 'Audit trail', SecurityIcon],
]
const W = 232

function Page({ title, sub, action, children }) {
  return (
    <Box>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={1} sx={{ mb: 2 }}>
        <Box><Typography variant="h5">{title}</Typography>{sub && <Typography color="text.secondary">{sub}</Typography>}</Box>
        {action}
      </Stack>
      {children}
    </Box>
  )
}

function Kpi({ label, value, sub, color }) {
  return (
    <Card><CardContent>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="h4" fontWeight={700} color={color}>{value}</Typography>
      {sub && <Typography variant="caption" color="text.secondary">{sub}</Typography>}
    </CardContent></Card>
  )
}

function Bar({ parts }) {
  const t = parts.reduce((s, p) => s + p[1], 0) || 1
  return (
    <Box>
      <Box sx={{ display: 'flex', height: 14, borderRadius: 7, overflow: 'hidden', bgcolor: '#e5e7eb', my: 1 }}>
        {parts.map(([l, v, c]) => <Box key={l} sx={{ width: `${(v / t) * 100}%`, bgcolor: c }} />)}
      </Box>
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
        {parts.map(([l, v, c]) => (
          <Typography key={l} variant="caption"><Box component="span" sx={{ display: 'inline-block', width: 10, height: 10, bgcolor: c, borderRadius: 0.5, mr: 0.5 }} />{l} · {v}</Typography>
        ))}
      </Stack>
    </Box>
  )
}

// ---------------------------------------------------------------- pages
function Inbox({ open, notify, refresh }) {
  const [rows, setRows] = useState([])
  const [cases, setCases] = useState([])
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => Promise.all([api('/api/inquiries'), api('/api/cases')]).then(([i, c]) => { setRows(i); setCases(c) }), [])
  useEffect(() => { load().catch((e) => notify(e.message)) }, [load])
  const byInq = Object.fromEntries(cases.filter((c) => c.inquiry_id).map((c) => [c.inquiry_id, c]))
  const runAll = async () => { setBusy(true); try { const r = await api('/api/process_all', {}); notify(`Triaged ${r.processed} inquiries`); await load(); refresh() } catch (e) { notify(e.message) } setBusy(false) }
  const runOne = async (id) => { try { const r = await api('/api/process', { inquiry_id: id }); await load(); refresh(); open(r.case_id) } catch (e) { notify(e.message) } }
  return (
    <Page title="Inquiry inbox" sub="Real tickets from the legacy case system: one per question type (34 types cover 100% of 2M tickets). Triaged, answered with citations, routed by tier."
      action={<Button variant="contained" onClick={runAll} disabled={busy}>{busy ? 'Triaging…' : 'Triage all with AI'}</Button>}>
      {busy && <LinearProgress sx={{ mb: 1 }} />}
      <TableContainer component={Card}>
        <Table size="small">
          <TableHead><TableRow><TableCell>Ticket</TableCell><TableCell>Channel</TableCell><TableCell>Subject</TableCell>
            <TableCell>HR tier</TableCell><TableCell>AI route</TableCell><TableCell>Status</TableCell></TableRow></TableHead>
          <TableBody>{rows.map((q) => {
            const c = byInq[q.id]
            return (
              <TableRow key={q.id} hover sx={{ cursor: 'pointer' }} onClick={() => (c ? open(c.id) : runOne(q.id))}>
                <TableCell>{q.id}</TableCell><TableCell><Chip size="small" label={q.channel} variant="outlined" /></TableCell>
                <TableCell><Typography variant="body2" fontWeight={500}>{q.subject}</Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: { xs: 'none', md: 'block' } }}>{q.body.slice(0, 90)}…</Typography></TableCell>
                <TableCell>T{q.tier || '?'} · {q.country}</TableCell>
                <TableCell>{c ? <RouteChip route={c.route} /> : <Chip size="small" label="Run" onClick={(e) => { e.stopPropagation(); runOne(q.id) }} />}</TableCell>
                <TableCell>{c ? <Chip size="small" variant="outlined" color={STATUS[c.status] || 'default'} label={c.status.replace('_', ' ')} /> : '—'}</TableCell>
              </TableRow>)
          })}</TableBody>
        </Table>
      </TableContainer>
    </Page>
  )
}

function Ask({ notify, refresh }) {
  const [q, setQ] = useState('')
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [emp, setEmp] = useState('')
  const examples = ['What is the parental leave policy in United Kingdom?', 'How many days off does a Director in India get per year?',
    'What health plans are available to me in Singapore?', 'Where can I find the employee handbook?']
  const go = async (text) => {
    setBusy(true); setRes(null)
    try { setRes(await api('/api/process', { text: text || q, channel: 'analyst self-service', employee_id: emp })) } catch (e) { notify(e.message) }
    setBusy(false)
  }
  return (
    <Page title="Ask AskHR" sub="Self-service for analysts: ask any policy question and get a cited answer in seconds instead of searching wikis and PDFs.">
      <Card sx={{ mb: 2 }}><CardContent>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <TextField label="On behalf of employee ID (optional)" value={emp} onChange={(e) => setEmp(e.target.value.trim())} sx={{ minWidth: 220 }} />
          <TextField fullWidth label="Ask a policy or process question" value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && q.trim()) go() }} />
          <Button variant="contained" onClick={() => go()} disabled={busy || !q.trim()}>Ask</Button>
        </Stack>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1.5 }}>
          {examples.map((x) => <Chip key={x} label={x} variant="outlined" onClick={() => { setQ(x); go(x) }} />)}
        </Stack>
      </CardContent></Card>
      {busy && <LinearProgress />}
      {res && <CaseView result={res} notify={notify} onDone={refresh} />}
    </Page>
  )
}

function Queue({ open, notify, filter, setFilter }) {
  const [rows, setRows] = useState([])
  useEffect(() => { api('/api/cases?status=PENDING_APPROVAL,DRAFT_READY,NEEDS_SME').then(setRows).catch((e) => notify(e.message)) }, [])
  const shown = rows.filter((r) => filter === 'all' || r.route === filter)
  return (
    <Page title="Approvals & work queue" sub="Human-in-the-loop: sensitive answers and every HR data change wait here for a named approver.">
      <ToggleButtonGroup size="small" exclusive value={filter} onChange={(_, v) => v && setFilter(v)} sx={{ mb: 2, flexWrap: 'wrap' }}>
        <ToggleButton value="all">All ({rows.length})</ToggleButton>
        {Object.entries(ROUTES).map(([k, v]) => <ToggleButton key={k} value={k}>{v.label} ({rows.filter((r) => r.route === k).length})</ToggleButton>)}
      </ToggleButtonGroup>
      <TableContainer component={Card}><Table size="small">
        <TableHead><TableRow><TableCell>Case</TableCell><TableCell>Subject</TableCell><TableCell>Category</TableCell><TableCell>Route</TableCell><TableCell>Received</TableCell></TableRow></TableHead>
        <TableBody>{shown.map((c) => (
          <TableRow key={c.id} hover sx={{ cursor: 'pointer' }} onClick={() => open(c.id)}>
            <TableCell>{c.id}</TableCell><TableCell>{c.subject}</TableCell>
            <TableCell>{c.category.replace('_', ' ')}{c.sensitive ? ' 🔒' : ''}</TableCell>
            <TableCell><RouteChip route={c.route} /></TableCell><TableCell><Typography variant="caption">{c.created_at.slice(0, 16).replace('T', ' ')}</Typography></TableCell>
          </TableRow>))}
          {!shown.length && <TableRow><TableCell colSpan={5}><Typography color="text.secondary" sx={{ p: 2 }}>Queue is clear.</Typography></TableCell></TableRow>}
        </TableBody></Table></TableContainer>
    </Page>
  )
}

function Insights({ notify }) {
  const [m, setM] = useState(null)
  const [ts, setTs] = useState(null)
  const [gaps, setGaps] = useState([])
  useEffect(() => { Promise.all([api('/api/metrics'), api('/api/gaps'), api('/api/ticket_stats')]).then(([a, b, c]) => { setM(a); setGaps(b); setTs(c) }).catch((e) => notify(e.message)) }, [])
  if (!m) return <CircularProgress />
  const bc = m.business_case, a = bc.assumptions
  const tierN = ts?.tier || {}, tot = ts?.tickets || 1
  const rm = ts?.resolution_minutes || {}
  const fmt = (x) => (x >= 120 ? `${Math.round(x / 60)} h` : `${x} min`)
  return (
    <Page title="Business impact" sub="Baseline measured on 2,000,000 historical tickets (2023-2026). Effort assumptions are shown below; confirm them with HR.">
      <Typography variant="overline">Today (measured)</Typography>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, gap: 2, mb: 2 }}>
        <Kpi label="Tickets per year" value={(bc.tickets_per_year / 1000).toFixed(0) + 'k'} sub={ts ? `${(tot / 1e6).toFixed(1)}M tickets analysed` : ''} />
        <Kpi label="Tier mix T1 / T2 / T3" value={`${Math.round(100 * (tierN['1'] || 0) / tot)} / ${Math.round(100 * (tierN['2'] || 0) / tot)} / ${Math.round(100 * (tierN['3'] || 0) / tot)}`} sub="% of tickets" />
        <Kpi label="Median wait T1 / T2 / T3" value={rm['1'] ? `${fmt(rm['1'].median)}` : '—'} sub={rm['2'] ? `T2 ${fmt(rm['2'].median)} · T3 ${fmt(rm['3'].median)}` : ''} />
        <Kpi label="Escalated / still open" value={ts?.status ? `${Math.round(100 * ts.status.escalated / tot)}% / ${Math.round(100 * ts.status.open / tot)}%` : '—'} sub="of all tickets" />
      </Box>
      <Typography variant="overline">With AskHR Assist</Typography>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, gap: 2 }}>
        <Kpi label="Efficiency gain (target 50%)" value={`${bc.efficiency_gain_pct}%`} color={bc.efficiency_gain_pct >= 50 ? 'success.main' : 'warning.main'} sub={`${(bc.hours_today / 1000).toFixed(0)}k → ${(bc.hours_with_ai / 1000).toFixed(0)}k analyst hours/yr`} />
        <Kpi label="Capacity freed (target 20%)" value={`${bc.capacity_freed_pct}%`} color={bc.capacity_freed_pct >= 20 ? 'success.main' : 'warning.main'} sub={`${bc.fte_capacity_freed} of ${bc.fte_today} FTE`} />
        <Kpi label="Answered in real time" value={(bc.realtime_tickets_year / 1000).toFixed(0) + 'k/yr'} sub={`${Math.round(bc.realtime_share_t1 * 100)}% of T1 · seconds instead of ~65 min`} color="success.main" />
        <Kpi label="Annual cost avoided" value={`$${(bc.cost_saved_year / 1e6).toFixed(1)}M`} sub={`at $${a.loaded_cost_per_hour}/hr loaded`} />
      </Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2, mt: 2 }}>
        <Card><CardContent><Typography variant="overline">Routing in this session ({m.cases} inquiries)</Typography>
          <Bar parts={[['T1 real-time', m.by_route.READY, '#16a34a'], ['T2 maker/checker', m.by_route.TRANSACTION, '#7c3aed'], ['T3 specialist', m.by_route.NEEDS_APPROVAL, '#f59e0b'], ['Knowledge gap', m.by_route.KNOWLEDGE_GAP, '#dc2626']]} />
          <Typography variant="body2" sx={{ mt: 1.5 }}>Quality signals: {m.decided} decided · {m.edited} edited by checker · {m.rejected} rejected · feedback {m.feedback_avg ?? '—'} ({m.feedback_n})</Typography>
        </CardContent></Card>
        <Card><CardContent><Typography variant="overline">Analyst hours per year by tier</Typography>
          {['1', '2', '3'].map((t) => (
            <Stack key={t} direction="row" alignItems="center" spacing={1} sx={{ my: 0.5 }}><Typography variant="body2" sx={{ width: 40 }}>T{t}</Typography>
              <LinearProgress variant="determinate" value={(bc.by_tier[t].hours_ai / bc.by_tier[t].hours_today) * 100} sx={{ flex: 1, height: 10, borderRadius: 5 }} />
              <Typography variant="caption" sx={{ width: 140 }}>{(bc.by_tier[t].hours_today / 1000).toFixed(0)}k → {(bc.by_tier[t].hours_ai / 1000).toFixed(0)}k hrs</Typography></Stack>))}
        </CardContent></Card>
      </Box>
      <Card sx={{ mt: 2 }}><CardContent>
        <Typography variant="overline">Knowledge gaps: questions no current policy answers ({gaps.length})</Typography>
        {gaps.slice(0, 6).map((g) => <Alert key={g.id} severity="error" sx={{ mt: 1 }}>{g.question} <i>({g.category})</i></Alert>)}
        {!gaps.length && <Typography color="text.secondary">None yet.</Typography>}
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>Writing the handbook and HR-contact answers alone moves about 13% of all tickets to real time.</Typography>
      </CardContent></Card>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 2 }}>
        Analyst effort per ticket today (assumption): T1 {a.effort_min_today['1']} · T2 {a.effort_min_today['2']} · T3 {a.effort_min_today['3']} min. With copilot: T1 {a.effort_min_with_ai['1']} (QA sampling) · T2 {a.effort_min_with_ai['2']} (checker) · T3 {a.effort_min_with_ai['3']} (specialist with brief) min. {a.productive_hours_per_fte} h/FTE. Volumes and mix measured.
      </Typography>
    </Page>
  )
}

function Knowledge({ notify }) {
  const [kb, setKb] = useState(null)
  const [q, setQ] = useState('')
  const [hits, setHits] = useState(null)
  const [country, setCountry] = useState('all')
  useEffect(() => { api('/api/kb').then(setKb).catch((e) => notify(e.message)) }, [])
  const search = async () => setHits(await api(`/api/search?q=${encodeURIComponent(q)}`))
  const docs = (kb?.documents || []).filter((d) => country === 'all' || d.country === country || (!d.country && country === 'global'))
  return (
    <Page title="Knowledge base & content health" sub={kb ? `${kb.stats.documents} documents · ${kb.stats.chunks} passages · ${kb.stats.countries.length} countries · ${kb.stats.store} · HR records: ${kb.hris?.employees?.toLocaleString() || 0} employees` : ''}
      action={<Button variant="outlined" onClick={async () => { await api('/api/reindex', {}); notify('Re-indexed'); setKb(await api('/api/kb')) }}>Re-index</Button>}>
      {kb && <Card sx={{ mb: 2, borderColor: 'error.main' }}><CardContent>
        <Typography variant="overline" color="error">Content health: issues found automatically</Typography>
        <Alert severity="warning" sx={{ mt: 1 }}><b>{kb.stats.superseded_pages} legacy wiki pages</b> are superseded by current policy PDFs. They are excluded from answers.</Alert>
        {kb.conflicts.filter((c) => c.differences.length).map((c) => c.differences.map((d, i) => (
          <Alert key={c.legacy_doc + i} severity="error" sx={{ mt: 1 }}>
            <b>Contradiction · {c.topic} ({c.country})</b><br />Legacy wiki ({c.legacy_date}): “{d.legacy}”<br />Current policy ({c.current_date}): “{d.current}”
          </Alert>)))}
        {kb.content_issues.map((x) => <Alert key={x.doc} severity="error" sx={{ mt: 1 }}><b>Wrong content · {x.title}</b>: {x.issue}</Alert>)}
      </CardContent></Card>}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mb: 2 }}>
        <TextField size="small" fullWidth label="Test retrieval (hybrid vector + keyword)" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search()} />
        <Button variant="contained" onClick={search}>Search</Button>
      </Stack>
      {hits && <Card sx={{ mb: 2 }}><CardContent>{hits.map((h) => (
        <Box key={h.id} sx={{ mb: 1 }}><Chip size="small" label={h.score} sx={{ mr: 1 }} /><b>{h.doc_id}</b> {h.meta?.country ? `(${h.meta.country})` : ''} › {h.section}
          <Typography variant="body2" color="text.secondary">{h.text}</Typography></Box>))}</CardContent></Card>}
      <ToggleButtonGroup size="small" exclusive value={country} onChange={(_, v) => v && setCountry(v)} sx={{ mb: 2, flexWrap: 'wrap' }}>
        {['all', ...(kb?.stats.countries || []), 'global'].map((c) => <ToggleButton key={c} value={c}>{c}</ToggleButton>)}
      </ToggleButtonGroup>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr 1fr' }, gap: 2 }}>
        {docs.map((d) => (
          <Card key={d.doc_id} sx={{ opacity: d.superseded || d.flagged ? 0.6 : 1 }}><CardContent>
            <Stack direction="row" spacing={0.5} sx={{ mb: 0.5 }} flexWrap="wrap" useFlexGap>
              <Chip size="small" label={d.type} />{d.country && <Chip size="small" label={d.country} variant="outlined" />}
              {d.superseded && <Chip size="small" color="warning" label="superseded" />}{d.flagged && <Chip size="small" color="error" label="wrong content" />}
            </Stack>
            <Typography variant="subtitle2" fontWeight={600}>{d.topic || d.title}</Typography>
            <Typography variant="caption" color="text.secondary">{d.domain} · {d.effective_date || 'no date'} · {d.sections.length} passages</Typography>
          </CardContent></Card>))}
      </Box>
    </Page>
  )
}

function Evals({ notify }) {
  const [e, setE] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api('/api/evals/last').then((r) => r.rows && setE(r)).catch(() => {}) }, [])
  const run = async () => { setBusy(true); try { setE(await api('/api/evals', { limit: 200 })) } catch (x) { notify(x.message) } setBusy(false) }
  const pct = (x) => (x == null ? '—' : `${Math.round(x * 100)}%`)
  return (
    <Page title="Evaluation on real tickets" sub="1,000 randomly sampled historical tickets with the tier HR Ops assigned. Logged to MLflow. Release is blocked unless tier-3 recall is 100% and no tier-2/3 ticket is auto-answered."
      action={<Button variant="contained" onClick={run} disabled={busy}>{busy ? 'Running 200 tickets…' : 'Run evaluation'}</Button>}>
      {busy && <LinearProgress />}
      {e && <>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, gap: 2 }}>
          <Kpi label="Tier accuracy vs HR labels" value={pct(e.tier_accuracy)} sub={`T1 ${pct(e.by_tier[1].accuracy)} · T2 ${pct(e.by_tier[2].accuracy)} · T3 ${pct(e.by_tier[3].accuracy)}`} />
          <Kpi label="T3 sensitive recall (gate 100%)" value={pct(e.tier3_recall)} color={e.tier3_recall === 1 ? 'success.main' : 'error.main'} />
          <Kpi label="Unsafe auto-answers (gate 0)" value={e.unsafe_auto} color={e.unsafe_auto ? 'error.main' : 'success.main'} />
          <Kpi label="Answered in real time" value={pct(e.realtime_rate)} sub={`grounded T1: ${pct(e.grounded_t1)}`} color="success.main" />
          <Kpi label="Citations valid" value={pct(e.citations_valid)} />
          <Kpi label="Avg groundedness" value={e.avg_groundedness ?? '—'} />
          <Kpi label="Knowledge gaps" value={pct(e.knowledge_gap_rate)} sub="content backlog" color="error.main" />
          <Kpi label="Latency p50 / p95" value={`${Math.round(e.latency_ms_p50)} ms`} sub={`p95 ${Math.round(e.latency_ms_p95)} ms · ${e.model}`} />
        </Box>
        <TableContainer component={Card} sx={{ mt: 2 }}><Table size="small">
          <TableHead><TableRow><TableCell>Ticket</TableCell><TableCell>Country</TableCell><TableCell>HR tier</TableCell><TableCell>AI route</TableCell><TableCell /><TableCell>Groundedness</TableCell><TableCell>Was</TableCell></TableRow></TableHead>
          <TableBody>{e.rows.slice(0, 60).map((r) => (
            <TableRow key={r.id}><TableCell>{r.id} · {r.subject}</TableCell><TableCell>{r.country}</TableCell><TableCell>T{r.tier}</TableCell>
              <TableCell><RouteChip route={r.route} /></TableCell><TableCell>{r.tier_ok ? '✅' : '❌'}</TableCell>
              <TableCell>{r.groundedness ?? '—'}</TableCell><TableCell><Typography variant="caption">{r.historical_min ? `${r.historical_min} min` : r.tier ? 'open/escalated' : ''}</Typography></TableCell></TableRow>))}
          </TableBody></Table></TableContainer>
      </>}
    </Page>
  )
}

function Audit({ notify }) {
  const [rows, setRows] = useState([])
  const [v, setV] = useState(null)
  const load = () => Promise.all([api('/api/audit'), api('/api/audit/verify')]).then(([a, b]) => { setRows(a); setV(b) }).catch((e) => notify(e.message))
  useEffect(() => { load() }, [])
  return (
    <Page title="Audit trail" sub="Append-only, SHA-256 hash-chained record of every AI and human action. Any edit breaks the chain."
      action={<Button variant="outlined" onClick={() => { load(); notify('Chain re-verified') }}>Verify chain</Button>}>
      {v && <Alert severity={v.valid ? 'success' : 'error'} sx={{ mb: 2 }}>{v.valid ? `Chain intact · ${v.entries} entries · head ${v.head}` : `Tampering detected at entry #${v.broken_at}`}</Alert>}
      <TableContainer component={Card}><Table size="small">
        <TableHead><TableRow><TableCell>#</TableCell><TableCell>Time (UTC)</TableCell><TableCell>Case</TableCell><TableCell>Actor</TableCell><TableCell>Action</TableCell><TableCell>Detail</TableCell></TableRow></TableHead>
        <TableBody>{rows.map((r) => (
          <TableRow key={r.seq}><TableCell>{r.seq}</TableCell><TableCell>{r.ts.slice(0, 19).replace('T', ' ')}</TableCell><TableCell>{r.case_id}</TableCell>
            <TableCell>{r.actor}</TableCell><TableCell><Chip size="small" label={r.action} color={r.actor.startsWith('human') ? 'primary' : 'default'} /></TableCell>
            <TableCell><Typography variant="caption" sx={{ wordBreak: 'break-all' }}>{r.detail}</Typography></TableCell></TableRow>))}
        </TableBody></Table></TableContainer>
    </Page>
  )
}

// ---------------------------------------------------------------- shell
export default function App() {
  const mobile = useMediaQuery(theme.breakpoints.down('md'))
  const [view, setView] = useState('inbox')
  const [caseId, setCaseId] = useState(null)
  const [navOpen, setNavOpen] = useState(false)
  const [msg, setMsg] = useState('')
  const [health, setHealth] = useState(null)
  const [pending, setPending] = useState(0)
  const [filter, setFilter] = useState('all')
  const [present, setPresent] = useState(false)
  const [tick, setTick] = useState(0)
  const refresh = useCallback(() => setTick((t) => t + 1), [])
  useEffect(() => { api('/api/health').then(setHealth).catch((e) => setMsg(`Backend not reachable: ${e.message}`)) }, [])
  useEffect(() => { api('/api/cases?status=PENDING_APPROVAL').then((r) => setPending(r.length)).catch(() => {}) }, [tick, caseId])
  const go = (v) => { setView(v); setCaseId(null); setNavOpen(false) }

  const nav = (
    <Box sx={{ width: W, bgcolor: '#0f172a', color: '#cbd5e1', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ p: 2.5 }}><Typography fontWeight={700} color="#fff">AskHR Assist</Typography>
        <Typography variant="caption" color="#94a3b8">ACME HR Operations · real-time T1, maker/checker T2, specialist T3</Typography></Box>
      <List sx={{ px: 1 }}>{NAV.map(([k, label, Icon]) => (
        <ListItemButton key={k} selected={view === k && !caseId} onClick={() => go(k)} sx={{ borderRadius: 2, mb: 0.5, '&.Mui-selected': { bgcolor: '#1e293b', color: '#fff' } }}>
          <ListItemIcon sx={{ color: 'inherit', minWidth: 36 }}>{k === 'approvals' ? <Badge badgeContent={pending} color="warning"><Icon fontSize="small" /></Badge> : <Icon fontSize="small" />}</ListItemIcon>
          <ListItemText primary={label} />
        </ListItemButton>))}
      </List>
      <Box sx={{ px: 2 }}><Button fullWidth variant="contained" startIcon={<SlideshowIcon />} onClick={() => { setPresent(true); setNavOpen(false) }}>Present</Button></Box>
      <Box sx={{ mt: 'auto', p: 2, fontSize: 12, color: '#94a3b8', lineHeight: 1.8 }}>
        {health && <>Model: <b style={{ color: '#e2e8f0' }}>{health.model}</b><br />Agent: {health.adk ? 'Google ADK' : 'pipeline (ADK not installed)'}<br />
          Vectors: {health.kb.store}<br />Policy: {health.policy}<br />Tracing: {health.telemetry.opentelemetry ? 'OpenTelemetry' : 'in-app'}{health.telemetry.mlflow ? ' + MLflow' : ''}</>}
      </Box>
    </Box>
  )
  const props = { notify: setMsg, refresh, open: (id) => setCaseId(id) }
  return (
    <ThemeProvider theme={theme}><CssBaseline />
      <Box sx={{ display: 'flex', minHeight: '100vh' }}>
        {mobile ? (
          <>
            <AppBar position="fixed" color="inherit" elevation={0} sx={{ borderBottom: 1, borderColor: 'divider' }}>
              <Toolbar><IconButton edge="start" onClick={() => setNavOpen(true)}><MenuIcon /></IconButton><Typography fontWeight={700}>AskHR Assist</Typography></Toolbar>
            </AppBar>
            <Drawer open={navOpen} onClose={() => setNavOpen(false)}>{nav}</Drawer>
          </>
        ) : (
          <Drawer variant="permanent" sx={{ width: W, '& .MuiDrawer-paper': { width: W, border: 0 } }}>{nav}</Drawer>
        )}
        <Box component="main" sx={{ flex: 1, minWidth: 0, p: { xs: 2, md: 3 }, mt: mobile ? 7 : 0 }}>
          {caseId ? (
            <Page title="Case review" action={<Button startIcon={<ArrowBackIcon />} onClick={() => { setCaseId(null); refresh() }}>Back</Button>}>
              <CaseView caseId={caseId} notify={setMsg} onDone={() => { setCaseId(null); refresh() }} />
            </Page>
          ) : (
            <Box key={`${view}-${tick}`}>
              {view === 'inbox' && <Inbox {...props} />}
              {view === 'ask' && <Ask {...props} />}
              {view === 'approvals' && <Queue {...props} filter={filter} setFilter={setFilter} />}
              {view === 'insights' && <Insights {...props} />}
              {view === 'kb' && <Knowledge {...props} />}
              {view === 'evals' && <Evals {...props} />}
              {view === 'audit' && <Audit {...props} />}
            </Box>
          )}
        </Box>
      </Box>
      <Dialog fullScreen open={present} onClose={() => setPresent(false)}>
        <DialogContent sx={{ p: 0, bgcolor: '#0f172a' }}>{present && <Present onClose={() => setPresent(false)} />}</DialogContent>
      </Dialog>
      <Snackbar open={!!msg} autoHideDuration={3500} onClose={() => setMsg('')} message={msg} />
    </ThemeProvider>
  )
}
