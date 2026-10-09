import React, { useEffect, useState } from 'react'
import { Box, Button, Stack, Typography } from '@mui/material'
import { api } from './api.js'

const S = { slide: { width: 1280, height: 720, bgcolor: '#fff', borderRadius: 1.5, p: '60px 72px', position: 'relative', overflow: 'hidden', display: 'flex', flexDirection: 'column' } }
const Kicker = ({ children, c = '#1a56db' }) => <Typography sx={{ fontSize: 14, fontWeight: 700, letterSpacing: 2, textTransform: 'uppercase', color: c, mb: 1.5 }}>{children}</Typography>
const H = ({ children, c }) => <Typography contentEditable suppressContentEditableWarning sx={{ fontSize: 40, fontWeight: 800, lineHeight: 1.15, mb: 3.5, letterSpacing: -0.5, color: c }}>{children}</Typography>
const Bul = ({ items, size = 24 }) => (
  <Box component="ul" contentEditable suppressContentEditableWarning sx={{ fontSize: size, lineHeight: 1.5, pl: 3.5, m: 0 }}>
    {items.map((x) => <li key={x} style={{ marginBottom: 12 }}>{x}</li>)}
  </Box>
)
const Foot = ({ n }) => <Box sx={{ position: 'absolute', left: 72, right: 72, bottom: 26, display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#94a3b8' }}><span>ACME AskHR Assist · AI-assisted, human-approved</span><span>{n}</span></Box>
const Big = ({ v, l, c }) => <Box sx={{ border: '1px solid #e2e8f0', borderRadius: 3, p: 3 }}><Typography sx={{ fontSize: 44, fontWeight: 800, color: c }}>{v}</Typography><Typography sx={{ fontSize: 16, color: '#64748b' }}>{l}</Typography></Box>
const Node = ({ t, s, bg = '#fff', bd = '#e2e8f0' }) => <Box sx={{ flex: 1, border: `2px solid ${bd}`, bgcolor: bg, borderRadius: 2.5, p: 1.5, textAlign: 'center' }}><Typography sx={{ fontWeight: 700, fontSize: 16 }}>{t}</Typography><Typography sx={{ fontSize: 12.5, color: '#475569', lineHeight: 1.35 }}>{s}</Typography></Box>
const Arr = () => <Typography sx={{ px: 0.5, color: '#94a3b8', fontSize: 20, alignSelf: 'center' }}>→</Typography>

export default function Present({ onClose }) {
  const [d, setD] = useState(null)
  const [i, setI] = useState(0)
  const [scale, setScale] = useState(1)
  useEffect(() => {
    Promise.all([api('/api/metrics'), api('/api/evals/last'), api('/api/health'), api('/api/ticket_stats'), api('/api/kb')]).then(async ([m, e, h, ts, kb]) => {
      const ev = e.rows ? e : await api('/api/evals', { limit: 200 })
      setD({ m: ev.rows ? await api('/api/metrics') : m, e: ev, h, ts, kb })
    })
    const fit = () => setScale(Math.min(window.innerWidth / 1340, (window.innerHeight - 60) / 760))
    fit(); window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [])
  const slides = []
  if (d) {
    const { m, e, h, ts, kb } = d
    const bc = m.business_case
    const pct = (x) => `${Math.round((x || 0) * 100)}%`
    const tot = ts.tickets || 1
    const rm = ts.resolution_minutes || {}
    const contra = (kb.conflicts || []).flatMap((c) => c.differences.map((x) => ({ ...x, topic: c.topic, country: c.country })))
    slides.push(
      <Box sx={{ ...S.slide, background: 'linear-gradient(135deg,#0f172a 0%,#1e3a8a 60%,#0f766e 100%)', color: '#fff', justifyContent: 'center' }}>
        <Kicker c="#5eead4">ACME HR Operations · Inquiry Management</Kicker>
        <H c="#fff">Real-time answers for Tier 1, prepared work for Tier 2, protected handling for Tier 3</H>
        <Typography contentEditable suppressContentEditableWarning sx={{ fontSize: 22, color: '#cbd5e1' }}>AskHR Assist · built and tested on 2 million of your historical tickets</Typography>
        <Typography contentEditable suppressContentEditableWarning sx={{ fontSize: 18, color: '#94a3b8', mt: 5 }}>Your Name · Forward Deployed Engineer</Typography>
      </Box>,
      <Box sx={S.slide}><Kicker>What we heard</Kicker><H>Your team today</H>
        <Bul size={22} items={['Every inquiry is triaged: Tier 1 simple (50%), Tier 2 changes (30%), Tier 3 sensitive, handled by specialist groups (20%)',
          '3-day SLA, maker/checker on changes, a human in the loop throughout', 'No way to get new analysts productive quickly; knowledge sits in PDFs, wikis and senior heads',
          'Quality is measured only by follow-up questions; there is no real quality measurement', 'First goal: inquiry management with real-time answers. Business goal: 50% efficiency, 20% lower cost']} />
        <Foot n={2} /></Box>,
      <Box sx={S.slide}><Kicker>What your data says</Kicker><H>{(tot / 1e6).toFixed(0)} million tickets, and they are highly repetitive</H>
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 2 }}>
          <Big v={`${Math.round(tot / 4 / 1000)}k`} l="tickets per year (2023-26)" />
          <Big v={rm['1'] ? `${rm['1'].median} min` : '—'} l="median wait for a Tier 1 answer" c="#d97706" />
          <Big v={rm['2'] ? `${Math.round(rm['2'].median / 60)} h` : '—'} l="median Tier 2 resolution" c="#d97706" />
          <Big v={rm['3'] ? `${Math.round(rm['3'].median / 60)} h` : '—'} l="median Tier 3 (p90 near the 3-day SLA)" c="#dc2626" />
        </Box>
        <Typography contentEditable suppressContentEditableWarning sx={{ fontSize: 22, mt: 4, fontWeight: 600 }}>34 question types cover 100% of tickets, and each type always lands in the same tier.</Typography>
        <Typography contentEditable suppressContentEditableWarning sx={{ fontSize: 19, color: '#475569', mt: 1 }}>Top asks: pay looks wrong · confidential complaint · extended leave · unknown deduction · employee handbook · who to contact · show my paystub · update bank details.</Typography>
        <Foot n={3} /></Box>,
      <Box sx={S.slide}><Kicker>The solution</Kicker><H>One governed path, matched to your tiers</H>
        <Stack direction="row" alignItems="stretch">
          <Node t="Inquiry" s="email · chat · case system · self-service" /><Arr />
          <Node t="Guardrails in" s="PII masking · injection screen" bg="#f0fdf4" bd="#86efac" /><Arr />
          <Node t="Triage" s="34 intents → tier, country" bg="#f0fdf4" bd="#86efac" /><Arr />
          <Node t="Ground" s="current country policy + employee's own HR records" bg="#eff6ff" bd="#93c5fd" /><Arr />
          <Node t="ADK agent" s={`${h.model} drafts with citations`} bg="#eff6ff" bd="#93c5fd" /><Arr />
          <Node t="Guardrails out" s="citations · grounded · no PII" bg="#f0fdf4" bd="#86efac" /><Arr />
          <Node t="Human" s="checker · specialist" bg="#fff7ed" bd="#fdba74" />
        </Stack>
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 2, mt: 3 }}>
          {[['Tier 1 · real time', 'Answer in seconds from current policy + own records (paystub, PTO, benefits), every sentence cited', '#dcfce7', '#166534'],
            ['Tier 2 · maker / checker', 'AI is the maker: pulls records, applies runbook rules, prepares the change. Analyst is the checker', '#ede9fe', '#5b21b6'],
            ['Tier 3 · specialist', 'Routed to ER, Payroll, Total Rewards or HRBP with a confidential brief. AI never replies alone', '#fef3c7', '#92400e']].map(([t, x, b, c]) => (
            <Box key={t} sx={{ bgcolor: b, color: c, borderRadius: 2, p: 2 }}><Typography sx={{ fontWeight: 800, fontSize: 19 }}>{t}</Typography><Typography contentEditable suppressContentEditableWarning sx={{ fontSize: 15.5, mt: 0.5 }}>{x}</Typography></Box>))}
        </Box><Foot n={4} /></Box>,
      <Box sx={S.slide}><Kicker>Live demo</Kicker><H>What you'll see, on real tickets</H>
        <Bul size={21} items={['T1: "Show me my most recent paystub" answered instantly from the payroll ledger + Ireland pay policy, with citations',
          'T1: "Parental leave in the UK": cites the 2025 policy (52 weeks), not the outdated wiki (48 weeks)',
          'T2: "Change my manager…": runbook checks catch a new manager who is an IC in another country before the checker approves',
          'T2: "Add my newborn": coverage upgrade prepared; name, date of birth and certificate requested',
          'T3: "My pay is significantly wrong": Payroll specialists get a confidential brief; employee gets an acknowledgement',
          'Evaluation on 1,000 real tickets · content-health findings · business impact']} /><Foot n={5} /></Box>,
      <Box sx={S.slide}><Kicker>Evidence</Kicker><H>Tested on {e.cases.toLocaleString()} real tickets against your tier labels</H>
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 2 }}>
          <Big v={pct(e.tier_accuracy)} l="tier accuracy vs HR labels" c="#16a34a" /><Big v={pct(e.tier3_recall)} l="sensitive (T3) recall" c="#16a34a" />
          <Big v={e.unsafe_auto} l="T2/T3 answered without a human" c={e.unsafe_auto ? '#dc2626' : '#16a34a'} /><Big v={pct(e.realtime_rate)} l="of all tickets answered in real time" />
          <Big v={pct(e.citations_valid)} l="citations valid" /><Big v={e.avg_groundedness} l="average groundedness" />
          <Big v={`${Math.round(e.latency_ms_p50)} ms`} l={`median response (was ${rm['1']?.median || 65} min for T1)`} /><Big v={pct(e.knowledge_gap_rate)} l="no policy exists: content backlog" c="#dc2626" />
        </Box><Foot n={6} /></Box>,
      <Box sx={S.slide}><Kicker>Found in your knowledge base</Kicker><H>Why answers are inconsistent today</H>
        <Bul size={20} items={[`${kb.stats.superseded_pages} legacy wiki pages are superseded by current policies; the copilot never cites them`,
          ...contra.map((x) => `${x.topic} (${x.country}): wiki says “${x.legacy.slice(0, 70)}…”, but policy says “${x.current.slice(0, 70)}…”`),
          ...(kb.content_issues || []).map((x) => `“${x.title}” contains the wrong content (job-requisition steps)`),
          'No current document answers "where is the handbook" or "who do I contact", roughly 13% of all tickets']} /><Foot n={7} /></Box>,
      <Box sx={S.slide}><Kicker>Business impact</Kicker><H>Against this year's targets</H>
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 2 }}>
          <Big v={`${bc.efficiency_gain_pct}%`} l="efficiency gain (target 50%)" c={bc.efficiency_gain_pct >= 50 ? '#16a34a' : '#d97706'} />
          <Big v={`${bc.capacity_freed_pct}%`} l={`capacity freed (target 20%) · ${bc.fte_capacity_freed} FTE`} c="#16a34a" />
          <Big v={`${Math.round(bc.realtime_tickets_year / 1000)}k`} l="tickets/yr answered in real time" />
          <Big v={`$${(bc.cost_saved_year / 1e6).toFixed(1)}M`} l="annual capacity value" />
        </Box>
        <Typography contentEditable suppressContentEditableWarning sx={{ fontSize: 18, color: '#475569', mt: 3 }}>
          Fixing the two missing answers lifts real-time coverage further and takes efficiency to the 50% target. Headcount impact comes through attrition and redeployment, and new analysts are productive from day one with cited answers. Volumes and mix are measured; effort minutes are assumptions to validate in the pilot.
        </Typography><Foot n={8} /></Box>,
      <Box sx={S.slide}><Kicker>Quality you can finally measure</Kicker><H>Every answer is scored, every week</H>
        <Box component="table" contentEditable suppressContentEditableWarning sx={{ fontSize: 18, borderCollapse: 'collapse', '& td': { borderBottom: '1px solid #e2e8f0', p: 1.1 }, '& td:first-of-type': { fontWeight: 700, width: 300 } }}>
          <tbody>
            <tr><td>Correct routing</td><td>Tier accuracy vs your labels; sensitive recall must stay 100%</td></tr>
            <tr><td>Grounded answers</td><td>Citation validity and groundedness on every draft, before it is sent</td></tr>
            <tr><td>Checker signal</td><td>Edit and reject rate by checkers = live quality score per question type</td></tr>
            <tr><td>Employee signal</td><td>Thumbs up/down and follow-up / reopen rate (your current measure)</td></tr>
            <tr><td>Speed</td><td>Time to answer per tier vs the 3-day SLA</td></tr>
            <tr><td>Content health</td><td>Knowledge gaps and policy contradictions become a weekly backlog for policy owners</td></tr>
          </tbody>
        </Box><Foot n={9} /></Box>,
      <Box sx={S.slide}><Kicker>Responsible AI</Kicker><H>Safe by design</H>
        <Bul size={20} items={['Grounded only in current, country-specific policy and the employee\'s own records; no evidence, no answer',
          'Every sentence cited; invalid citations block delivery', 'Least privilege: the agent searches and prepares, never writes. Changes need a checker',
          'Tier 3 never gets an automated reply: specialist team plus a confidential brief', 'PII masked before the model; prompt-injection screen; full hash-chained audit trail',
          'OpenTelemetry traces and MLflow evaluation runs on every model or prompt change']} /><Foot n={10} /></Box>,
      <Box sx={S.slide}><Kicker>Built on the approved stack</Kicker><H>Requirements traceability</H>
        <Box component="table" sx={{ fontSize: 17, borderCollapse: 'collapse', '& td': { borderBottom: '1px solid #e2e8f0', p: 1 }, '& td:first-of-type': { fontWeight: 700, width: 230 } }}>
          <tbody>
            <tr><td>AI agents</td><td>Google ADK agent with tools (search policies, look up records, propose change); MLflow + OpenTelemetry</td></tr>
            <tr><td>AI models</td><td>Gemini or Claude, or Gemma / Llama for on-premises; switched by config</td></tr>
            <tr><td>Guardrails</td><td>Input/output validators (Guardrails AI pattern); MLflow AI Gateway for model access</td></tr>
            <tr><td>Frontend · Backend</td><td>React + Material UI (responsive) · Python (FastAPI / AWS Lambda)</td></tr>
            <tr><td>Data</td><td>PostgreSQL + pgvector for the knowledge base; HR systems of record via read-only adapters</td></tr>
            <tr><td>Infrastructure</td><td>AWS serverless (Lambda, CloudFront, Aurora) via Terraform; Docker / Kubernetes / Helm; Git</td></tr>
          </tbody>
        </Box><Foot n={11} /></Box>,
      <Box sx={S.slide}><Kicker>Decision</Kicker><H>Approve a 6-week pilot</H>
        <Bul items={['Weeks 1-2: connect the live case system and HRIS read access; fix the 2 missing answers + 2 wiki contradictions',
          'Weeks 3-6: Tier 1 real-time for one country and two domains (Payroll, Time & Absence); T2 maker/checker with 10 analysts',
          'Success criteria: T1 answered in under 1 minute, 0 sensitive tickets without a specialist, checker edit rate under 15%',
          'Then scale by country and domain as the weekly quality scores hold']} size={21} />
        <Typography sx={{ fontSize: 26, fontWeight: 700, mt: 3 }}>Can we start Monday?</Typography><Foot n={12} /></Box>,
    )
  }
  useEffect(() => {
    const k = (ev) => {
      if (document.activeElement?.isContentEditable) return
      if (['ArrowRight', 'PageDown', ' '].includes(ev.key)) { ev.preventDefault(); setI((x) => Math.min(x + 1, slides.length - 1)) }
      if (['ArrowLeft', 'PageUp'].includes(ev.key)) setI((x) => Math.max(x - 1, 0))
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [slides.length])
  if (!slides.length) return <Typography sx={{ color: '#fff', p: 4 }}>Building deck from live data (running the evaluation on 1,000 tickets the first time takes ~20 seconds)…</Typography>
  return (
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
      <Box sx={{ transform: `scale(${scale})`, transformOrigin: 'center' }}>{slides[i]}</Box>
      <Stack direction="row" spacing={1} sx={{ position: 'fixed', bottom: 12 }} alignItems="center">
        <Button size="small" variant="contained" onClick={() => setI(Math.max(0, i - 1))}>◀</Button>
        <Typography sx={{ color: '#94a3b8', fontSize: 13 }}>{i + 1} / {slides.length} · click text to edit</Typography>
        <Button size="small" variant="contained" onClick={() => setI(Math.min(slides.length - 1, i + 1))}>▶</Button>
        <Button size="small" variant="outlined" sx={{ color: '#fff' }} onClick={onClose}>Exit</Button>
      </Stack>
    </Box>
  )
}
