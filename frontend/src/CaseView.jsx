import React, { useEffect, useState } from 'react'
import {
  Accordion, AccordionDetails, AccordionSummary, Alert, AlertTitle, Box, Button, Card, CardContent, Chip, Divider,
  IconButton, Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, Tooltip, Typography,
} from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import CancelIcon from '@mui/icons-material/Cancel'
import SendIcon from '@mui/icons-material/Send'
import ThumbUpIcon from '@mui/icons-material/ThumbUp'
import ThumbDownIcon from '@mui/icons-material/ThumbDown'
import { api, ROUTES, STATUS } from './api.js'

export function RouteChip({ route, size = 'small' }) {
  const r = ROUTES[route] || { label: route, color: 'default' }
  return <Chip size={size} color={r.color} label={r.label} />
}

/** Renders text with [n] citations as clickable chips. */
export function CitedText({ text, onCite, active }) {
  const parts = String(text || '').split(/(\[\d+\])/g)
  return (
    <Typography component="div" sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.75 }}>
      {parts.map((p, i) => {
        const m = p.match(/^\[(\d+)\]$/)
        if (!m) return <span key={i}>{p}</span>
        const n = Number(m[1])
        return (
          <Chip key={i} label={n} size="small" color={active === n ? 'primary' : 'default'}
            onClick={() => onCite && onCite(n)} sx={{ height: 20, mx: 0.25, fontSize: 11, cursor: 'pointer' }} />
        )
      })}
    </Typography>
  )
}

function Checks({ title, checks }) {
  if (!checks || !checks.length) return null
  return (
    <Box sx={{ mb: 1.5 }}>
      <Typography variant="overline" color="text.secondary">{title}</Typography>
      {checks.map((c) => (
        <Stack key={c.name} direction="row" spacing={1} alignItems="flex-start" sx={{ py: 0.4 }}>
          {c.passed ? <CheckCircleIcon color="success" fontSize="small" /> : <CancelIcon color="error" fontSize="small" />}
          <Box>
            <Typography variant="body2" fontWeight={600}>{c.name}</Typography>
            <Typography variant="caption" color="text.secondary">{c.detail}</Typography>
          </Box>
        </Stack>
      ))}
    </Box>
  )
}

function Diff({ diff }) {
  if (!diff) return null
  const fmt = (v) => (v === null || v === undefined ? '—' : typeof v === 'object' ? JSON.stringify(v, null, 1) : String(v))
  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 1, mt: 1 }}>
      <Box sx={{ p: 1.5, borderRadius: 1, bgcolor: '#fdecea' }}>
        <Typography variant="caption" color="error">BEFORE · {diff.field}</Typography>
        <Typography component="pre" sx={{ m: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>{fmt(diff.before)}</Typography>
      </Box>
      <Box sx={{ p: 1.5, borderRadius: 1, bgcolor: '#e8f5e9' }}>
        <Typography variant="caption" color="success.main">AFTER (proposed){diff.effective ? ` · effective ${diff.effective}` : ''}</Typography>
        <Typography component="pre" sx={{ m: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>{fmt(diff.after)}</Typography>
      </Box>
    </Box>
  )
}

export default function CaseView({ caseId, result, onDone, notify }) {
  const [c, setC] = useState(null)
  const [text, setText] = useState('')
  const [note, setNote] = useState('')
  const [reviewer, setReviewer] = useState(() => { try { return localStorage.getItem('reviewer') || 'J. Analyst' } catch { return 'J. Analyst' } })
  const [active, setActive] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let live = true
    const load = async () => {
      const d = result ? { payload: result, status: null } : await api(`/api/cases/${caseId}`)
      if (!live) return
      setC(d); setText(d.final_text || d.payload.draft); setActive(null)
    }
    load().catch((e) => notify && notify(e.message))
    return () => { live = false }
  }, [caseId, result])

  if (!c) return <Typography color="text.secondary">Loading…</Typography>
  const p = c.payload
  const closed = ['SENT', 'APPLIED', 'REJECTED'].includes(c.status)
  const canSend = p.route === 'READY'

  const decide = async (decision) => {
    setBusy(true)
    try {
      try { localStorage.setItem('reviewer', reviewer) } catch { /* storage unavailable */ }
      const r = await api(`/api/cases/${p.case_id}/decision`, { decision, note, reviewer, final_text: text })
      notify && notify(`${decision === 'REJECT' ? 'Rejected' : r.status === 'APPLIED' ? 'Approved and applied to HR record' : 'Sent'} · audited`)
      onDone && onDone()
    } catch (e) { notify && notify(e.message) }
    setBusy(false)
  }
  const rate = async (rating) => {
    await api(`/api/cases/${p.case_id}/feedback`, { rating, comment: '' }).catch(() => {})
    notify && notify('Feedback recorded: improves the golden set')
  }

  return (
    <Box>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        <RouteChip route={p.route} size="medium" />
        <Chip label={p.triage.label} variant="outlined" />
        {p.triage.sensitive && <Chip color="warning" variant="outlined" label="Sensitive" />}
        {c.status && <Chip color={STATUS[c.status] || 'default'} label={c.status.replace('_', ' ')} variant="outlined" />}
        <Typography variant="caption" color="text.secondary">{p.case_id} · {p.engine} · {p.total_ms} ms · {p.policy_version}</Typography>
      </Stack>

      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
        {p.employee && <Chip variant="outlined" label={`${p.employee.name} · ${p.employee.level} · ${p.employee.country} · ${p.employee.department}`} />}
        <Chip variant="outlined" label={`Intent: ${p.triage.label}`} />
        {p.historical_tier && <Chip variant="outlined" color={p.historical_tier === p.triage.tier ? 'success' : 'error'} label={`Historical tier ${p.historical_tier} · AI tier ${p.triage.tier}`} />}
        {p.sla?.historical_median_min && <Chip color="primary" label={`Historically ~${p.sla.historical_median_min >= 120 ? Math.round(p.sla.historical_median_min / 60) + ' h' : p.sla.historical_median_min + ' min'} → now ${p.total_ms} ms`} />}
      </Stack>
      {p.route_reasons.map((r) => (
        <Alert key={r} severity={p.route === 'READY' ? 'success' : p.route === 'KNOWLEDGE_GAP' ? 'error' : 'warning'} sx={{ mb: 1 }}>{r}</Alert>
      ))}

      {/* decision-top */}
      <Box sx={{ my: 1.5 }}>
          {!closed ? (
            <Card variant="outlined"><CardContent>
              <Typography variant="overline" color="text.secondary">{p.route === 'TRANSACTION' ? 'Checker decision (maker/checker)' : 'Human decision'}</Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ my: 1 }}>
                <TextField size="small" label="Reviewer" value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
                <TextField size="small" fullWidth label={canSend ? 'Note (optional)' : 'Rationale (required)'} value={note} onChange={(e) => setNote(e.target.value)} />
              </Stack>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {canSend && <Button variant="contained" color="success" startIcon={<SendIcon />} disabled={busy} onClick={() => decide('SEND')}>Approve &amp; send</Button>}
                {!canSend && p.route !== 'KNOWLEDGE_GAP' && (
                  <Button variant="contained" disabled={busy} onClick={() => decide('APPROVE')}>
                    {p.transaction ? 'Checker: approve & apply' : 'Approve & send'}
                  </Button>)}
                {p.transaction && !p.transaction.valid && (
                  <Button variant="outlined" disabled={busy} onClick={() => decide('REQUEST_INFO')}>Request info from employee</Button>)}
                <Button variant="outlined" color="error" disabled={busy} onClick={() => decide('REJECT')}>Reject</Button>
                <Box sx={{ flex: 1 }} />
                <Tooltip title="Good draft"><IconButton onClick={() => rate(1)}><ThumbUpIcon /></IconButton></Tooltip>
                <Tooltip title="Bad draft"><IconButton onClick={() => rate(-1)}><ThumbDownIcon /></IconButton></Tooltip>
              </Stack>
            </CardContent></Card>
          ) : (
            <Alert severity={c.status === 'REJECTED' ? 'warning' : 'success'}>
              {c.status} by {c.reviewer}{c.note ? `: ${c.note}` : ''}{c.edited ? ' (draft edited by human)' : ''}
            </Alert>
          )}
      </Box>

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1.15fr 1fr' }, gap: 2, mt: 1 }}>
        <Stack spacing={2}>
          <Card variant="outlined"><CardContent>
            <Typography variant="overline" color="text.secondary">
              Inquiry · {p.channel}{p.employee_name ? ` · ${p.employee_name} (${p.employee_id})` : ''}
            </Typography>
            <Typography variant="subtitle1" fontWeight={600}>{p.subject}</Typography>
            <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', mt: 1 }}>{p.masked_question}</Typography>
            <Typography variant="caption" color="text.secondary">Shown with personal data masked, exactly as the model saw it.</Typography>
          </CardContent></Card>

          <Card variant="outlined"><CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="overline" color="text.secondary">AI draft · citations are clickable</Typography>
              {p.groundedness != null && <Chip size="small" label={`groundedness ${p.groundedness}`} color={p.groundedness >= 0.55 ? 'success' : 'warning'} variant="outlined" />}
            </Stack>
            <Box sx={{ p: 1.5, my: 1, bgcolor: '#f7f9fc', borderRadius: 1 }}>
              <CitedText text={text} onCite={setActive} active={active} />
            </Box>
            {!closed && (
              <TextField label="Edit before sending" multiline minRows={5} fullWidth value={text} onChange={(e) => setText(e.target.value)} />
            )}
            {p.internal_guidance?.length > 0 && (
              <Alert severity="info" sx={{ mt: 1.5 }}>
                <AlertTitle>Internal handling guidance (not sent)</AlertTitle>
                {p.internal_guidance.map((g, i) => <div key={i}>• {g.text} <b>[{g.doc}]</b></div>)}
              </Alert>
            )}
          </CardContent></Card>

          {p.brief && (
            <Card variant="outlined" sx={{ borderColor: 'warning.main' }}><CardContent>
              <Typography variant="overline" color="warning.main">Confidential brief for {p.brief.team}</Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>{p.brief.summary}</Typography>
              <Typography variant="body2"><b>Relevant policies:</b> {p.brief.relevant_policies.join(', ') || '—'}</Typography>
              <Typography variant="body2"><b>Records attached:</b> {p.brief.records_attached.join(', ') || '—'}</Typography>
              <Typography variant="body2"><b>SLA:</b> {p.brief.sla}</Typography>
              <Typography variant="caption" color="text.secondary">{p.brief.handling}</Typography>
            </CardContent></Card>
          )}

          {p.transaction && (
            <Card variant="outlined" sx={{ borderColor: 'secondary.main' }}><CardContent>
              <Typography variant="overline" color="secondary">Maker: AI-prepared work package · checker approval required before anything changes</Typography>
              <Typography variant="subtitle1" fontWeight={600}>{p.transaction.type.replaceAll('_', ' ')}</Typography>
              <Table size="small" sx={{ mt: 1 }}>
                <TableHead><TableRow><TableCell>Policy rule</TableCell><TableCell>Result</TableCell><TableCell>Source</TableCell></TableRow></TableHead>
                <TableBody>{p.transaction.validation.map((v) => (
                  <TableRow key={v.rule}>
                    <TableCell>{v.passed ? '✅' : '❌'} {v.rule}</TableCell>
                    <TableCell><Typography variant="caption">{v.detail}</Typography></TableCell>
                    <TableCell><Chip size="small" label={v.policy} variant="outlined" /></TableCell>
                  </TableRow>))}
                </TableBody>
              </Table>
              <Diff diff={p.transaction.diff} />
            </CardContent></Card>
          )}

        </Stack>

        <Stack spacing={2}>
          <Card variant="outlined"><CardContent>
            <Typography variant="overline" color="text.secondary">Sources ({p.sources.length}) · current {p.retrieval.country || ''} policies + employee's own records · superseded pages excluded</Typography>
            {p.sources.length === 0 && <Typography variant="body2" color="text.secondary">No passage met the relevance threshold.</Typography>}
            {p.sources.map((s, i) => (
              <Accordion key={s.id} disableGutters expanded={active === i + 1} onChange={(_, open) => setActive(open ? i + 1 : null)}
                sx={{ boxShadow: 'none', border: '1px solid', borderColor: active === i + 1 ? 'primary.main' : 'divider', mb: 1, '&:before': { display: 'none' } }}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
                    <Chip size="small" label={i + 1} color={p.cited.includes(i + 1) ? 'primary' : 'default'} />
                    <Typography variant="body2" noWrap>{s.meta?.type === 'record' ? '🗂 ' : '📄 '}<b>{s.meta?.type === 'record' ? s.title : s.doc_id}</b> {s.meta?.type === 'record' ? '' : s.title} › {s.section}{s.meta?.country ? ` · ${s.meta.country}` : ''}{s.meta?.effective_date ? ` · eff. ${s.meta.effective_date}` : ''}</Typography>
                    <Typography variant="caption" color="text.secondary">{s.score}</Typography>
                  </Stack>
                </AccordionSummary>
                <AccordionDetails><Typography variant="body2">{s.text}</Typography>
                  <Typography variant="caption" color="text.secondary">{s.source}</Typography></AccordionDetails>
              </Accordion>
            ))}
          </CardContent></Card>

          <Card variant="outlined"><CardContent>
            <Checks title="Input guardrails" checks={p.guardrails.input} />
            <Checks title="Output guardrails" checks={p.guardrails.output} />
            <Divider sx={{ my: 1 }} />
            <Typography variant="overline" color="text.secondary">Agent trace (also exported to OpenTelemetry / MLflow)</Typography>
            <Table size="small"><TableBody>{p.trace.map((t) => (
              <TableRow key={t.step}><TableCell sx={{ width: 140 }}><b>{t.step}</b></TableCell>
                <TableCell><Typography variant="caption">{t.summary}</Typography></TableCell>
                <TableCell align="right"><Typography variant="caption">{t.ms} ms</Typography></TableCell></TableRow>))}
            </TableBody></Table>
          </CardContent></Card>
        </Stack>
      </Box>
    </Box>
  )
}
