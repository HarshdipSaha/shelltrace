import { useCallback, useEffect, useRef, useState } from 'react';
import { decideAlias, draftReport, getCase, health, injectDesignation, openCase, review, screenName, setWatch } from './api.js';
import AliasPanel from './components/AliasPanel.jsx';
import CaseHeader from './components/CaseHeader.jsx';
import EvidenceGraph from './components/EvidenceGraph.jsx';
import EvidenceLocker from './components/EvidenceLocker.jsx';
import EvalPage from './components/EvalPage.jsx';
import NameScreen from './components/NameScreen.jsx';
import Notifications from './components/Notifications.jsx';
import ReportPanel from './components/ReportPanel.jsx';
import ReviewPanel from './components/ReviewPanel.jsx';
import RulePackPanel from './components/RulePackPanel.jsx';
import SearchPanel from './components/SearchPanel.jsx';
import TimeSlider from './components/TimeSlider.jsx';
import Timeline from './components/Timeline.jsx';
import WatchBar from './components/WatchBar.jsx';

const INITIAL_FORM = {
  workspace: 'demo',
  asOf: '2024-01-01',
  maxHops: 6,
  packs: ['OFAC', 'EU', 'UK'],
  mode: 'playbook',
};

function App() {
  const [form, setForm] = useState(() => ({
    ...INITIAL_FORM,
    workspace: new URLSearchParams(window.location.search).get('ws') || INITIAL_FORM.workspace,
  }));
  const [entity, setEntity] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [service, setService] = useState({ loading: true, health: null, error: '' });
  const [selected, setSelected] = useState(null);
  const [route, setRoute] = useState(window.location.hash);
  const [notificationRefresh, setNotificationRefresh] = useState(0);
  const caseRequestId = useRef(0);
  const healthRequestId = useRef(0);

  useEffect(() => {
    const updateRoute = () => setRoute(window.location.hash);
    window.addEventListener('hashchange', updateRoute);
    return () => window.removeEventListener('hashchange', updateRoute);
  }, []);

  const checkHealth = useCallback(async () => {
    const requestId = ++healthRequestId.current;
    setService((current) => ({ ...current, loading: true, error: '' }));
    try {
      const data = await health();
      if (healthRequestId.current === requestId) {
        setService({ loading: false, health: data, error: '' });
      }
    } catch (reason) {
      if (healthRequestId.current === requestId) {
        setService({ loading: false, health: null, error: reason.message });
      }
    }
  }, []);

  useEffect(() => {
    checkHealth();
    return () => { healthRequestId.current += 1; };
  }, [checkHealth]);

  const updateForm = useCallback((updates) => {
    caseRequestId.current += 1;
    setLoading(false);
    setForm((current) => ({ ...current, ...updates }));
    setResult(null);
    setSelected(null);
    setError('');
  }, []);

  const selectEntity = useCallback((nextEntity) => {
    caseRequestId.current += 1;
    setLoading(false);
    setEntity(nextEntity);
    setResult(null);
    setSelected(null);
    setError('');
  }, []);

  const runCase = useCallback(async (overrides = {}) => {
    const nextForm = { ...form, ...overrides };
    const nextEntity = overrides.entity ?? entity;
    if (!nextEntity) {
      setError('Choose an entity before running an investigation.');
      return;
    }

    const requestId = ++caseRequestId.current;
    setForm(nextForm);
    setEntity(nextEntity);
    setResult(null);
    setLoading(true);
    setError('');
    setSelected(null);
    try {
      const caseResult = await openCase({
        workspace: nextForm.workspace,
        entity_id: nextEntity.id,
        as_of: nextForm.asOf,
        max_hops: Number(nextForm.maxHops),
        rulepacks: nextForm.packs,
        mode: nextForm.mode,
      });
      if (caseRequestId.current === requestId) setResult(caseResult);
    } catch (reason) {
      if (caseRequestId.current === requestId) {
        setResult(null);
        setError(reason.message || 'The investigation could not be completed.');
      }
    } finally {
      if (caseRequestId.current === requestId) setLoading(false);
    }
  }, [entity, form]);

  const changeCaseDate = useCallback((asOf) => runCase({ asOf }), [runCase]);
  const submitReview = useCallback((body) => {
    if (!result) throw new Error('Open a case before recording a review.');
    return review(form.workspace, result.case_id, body);
  }, [form.workspace, result]);
  const createReport = useCallback(() => {
    if (!result) throw new Error('Open a case before drafting a report.');
    return draftReport(form.workspace, result.case_id);
  }, [form.workspace, result]);
  const toggleWatch = useCallback((active) => {
    if (!result) throw new Error('Open a case before setting a watch.');
    return setWatch(form.workspace, result.case_id, active);
  }, [form.workspace, result]);
  const addDesignation = useCallback(async (body) => {
    const outcome = await injectDesignation({ ...body, workspace: form.workspace });
    setNotificationRefresh((value) => value + 1);
    return outcome;
  }, [form.workspace]);
  const runNameScreen = useCallback(() => {
    if (!result) throw new Error('Open a case before screening its name.');
    return screenName({
      workspace: form.workspace,
      entity_id: result.entity.id,
      as_of: result.as_of,
      rulepacks: result.rulepacks,
    });
  }, [form.workspace, result]);
  const decideAliasAndRefresh = useCallback(async (candidate, accept, reason, confirmMerge) => {
    await decideAlias(form.workspace, {
      a_id: candidate.a_id,
      b_id: candidate.b_id,
      accept,
      by: 'analyst-1',
      reason,
      confirm_merge: confirmMerge,
    });
    await runCase();
  }, [form.workspace, runCase]);
  const openNotificationCase = useCallback(async (item) => {
    const caseId = item.diff?.new_case_id || item.new_case_id || item.case_id;
    const requestId = ++caseRequestId.current;
    setLoading(true);
    setError('');
    try {
      const nextCase = await getCase(form.workspace, caseId);
      if (caseRequestId.current !== requestId) return;
      setResult(nextCase);
      setEntity(nextCase.entity);
      setSelected(null);
      setForm((current) => ({
        ...current,
        asOf: nextCase.as_of,
        maxHops: nextCase.max_hops,
        packs: nextCase.rulepacks,
        mode: nextCase.mode,
      }));
    } catch (cause) {
      if (caseRequestId.current === requestId) setError(cause?.message || 'The changed case could not be loaded.');
    } finally {
      if (caseRequestId.current === requestId) setLoading(false);
    }
  }, [form.workspace]);

  if (route === '#/eval') return <EvalPage workspace={form.workspace} />;

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="ShellTrace home">
          <span className="brand-mark" aria-hidden="true"><span /><span /><span /></span>
          <span className="brand-word">Shell<span>Trace</span></span>
        </a>
        <div className="topbar-title">
          <span>INVESTIGATION WORKSPACE</span>
          <strong>Sanctions exposure review</strong>
        </div>
        <a className="evaluation-link" href="#/eval">Evaluation</a>
        <div className="service-status" aria-live="polite">
          <span className={`status-dot ${service.health?.status === 'ok' ? 'status-dot--live' : ''}`} />
          <span>{service.loading ? 'Connecting to graph' : service.health?.status === 'ok' ? 'Graph connected' : 'Graph unavailable'}</span>
          <span className="status-divider" />
          <span className="mode-indicator">{service.health?.llm === 'deterministic' ? 'Playbook mode' : service.health?.llm || 'Service status'}</span>
        </div>
      </header>

      <div className="workspace-heading">
        <div>
          <p className="eyebrow">SHELLTRACE / CASE REVIEW</p>
          <h1>Investigate an entity</h1>
          <p className="heading-copy">Trace dated ownership and control evidence against selected sanctions regimes.</p>
        </div>
        {result && (
          <div className="case-reference">
            <span>CASE</span>
            <code>{result.case_id}</code>
          </div>
        )}
      </div>

      {service.error && (
        <div className="notice notice--error" role="status">{service.error}</div>
      )}
      {error && (
        <div className="notice notice--error" role="alert">
          <span>{error}</span>
          <button type="button" className="notice-dismiss" onClick={() => setError('')} aria-label="Dismiss error">×</button>
        </div>
      )}

      <div className="workspace-grid">
        <aside className="left-rail" aria-label="Case controls and audit timeline">
          <SearchPanel
            workspace={form.workspace}
            health={service.health}
            healthLoading={service.loading}
            healthError={service.error}
            entity={entity}
            asOf={form.asOf}
            maxHops={form.maxHops}
            packs={form.packs}
            mode={form.mode}
            loading={loading}
            onSelectEntity={selectEntity}
            onChange={updateForm}
            onRun={() => runCase()}
            onRetryHealth={checkHealth}
          />
          <Timeline result={result} selected={selected} onSelect={setSelected} />
          <WatchBar workspace={form.workspace} result={result} onWatch={toggleWatch} onInject={addDesignation} />
          <Notifications workspace={form.workspace} refreshSignal={notificationRefresh} onOpenCase={openNotificationCase} />
        </aside>

        <main className="main-column">
          <CaseHeader result={result} />
          <section className={`overview-panel ${result ? 'overview-panel--complete' : ''}`} aria-label="Investigation overview">
            <div className="panel-topline">
              <div>
                <p className="eyebrow">EVIDENCE SCOPE</p>
                <h2>{result ? result.entity.name : 'Ownership and control network'}</h2>
              </div>
              {result && <span className="snapshot-tag">{result.snapshot}</span>}
            </div>

            {result ? (
              <>
                <div className="subject-meta">
                  <span className="entity-kind">{result.entity.kind}</span>
                  {result.entity.country && <span>{result.entity.country}</span>}
                  <span>As of {result.as_of}</span>
                </div>
                <div className="overview-rule" />
                <div className="overview-metrics">
                  <div><span>HOP LIMIT</span><strong>{result.max_hops}</strong></div>
                  <div><span>RULE PACKS</span><strong>{result.rulepacks.length}</strong></div>
                  <div><span>TIMELINE STEPS</span><strong>{result.steps.length}</strong></div>
                  <div><span>EVIDENCE RECORDS</span><strong>{Object.keys(result.evidence || {}).length}</strong></div>
                </div>
                <p className="scope-note">
                  This view is bounded to the selected date and relationship scope. Review the timeline and cited records before drawing conclusions.
                </p>
              </>
            ) : (
              <div className="overview-empty">
                <div className="network-illustration" aria-hidden="true">
                  <span className="network-line network-line--one" />
                  <span className="network-line network-line--two" />
                  <span className="network-node network-node--one" />
                  <span className="network-node network-node--two" />
                  <span className="network-node network-node--three" />
                  <span className="network-node network-node--focus" />
                </div>
                <h3>Start with a company, LEI, or IMO</h3>
                <p>Choose a subject to open a dated case and review its evidence trail.</p>
              </div>
            )}
          </section>
          <EvidenceGraph result={result} onSelect={setSelected} />
          <TimeSlider result={result} loading={loading} onChangeAsOf={changeCaseDate} />
        </main>

        <aside className="right-rail" aria-label="Case context">
          <section className="context-card">
            <div className="context-icon" aria-hidden="true">◎</div>
            <p className="eyebrow">CASE CONTEXT</p>
            <h2>{result ? 'Bounded investigation' : 'Ready for review'}</h2>
            <p>{result
              ? `The case covers ${result.bounds.scope_nodes} entities within ${result.bounds.max_hops} relationship hops.`
              : 'Select a subject and set the investigation date and rule packs.'}</p>
            {result && <div className="context-packs">{result.rulepacks.map((pack) => <span key={pack}>{pack}</span>)}</div>}
          </section>

          <RulePackPanel result={result} />
          <NameScreen result={result} onScreen={runNameScreen} />
          <AliasPanel result={result} onDecide={decideAliasAndRefresh} />
          <ReportPanel result={result} onDraft={createReport} onSelect={setSelected} />
          <ReviewPanel result={result} onSubmit={submitReview} />
          <EvidenceLocker result={result} selectedKey={selected} />

          <section className="context-card context-card--quiet">
            <p className="eyebrow">DECISION STANDARD</p>
            <h2>Evidence first</h2>
            <p>Validated dispositions come from deterministic policy checks. Any agent proposal remains clearly labeled as a proposal.</p>
            <div className="context-rule"><span /> Policy validation active</div>
          </section>

          {result?.bounds?.truncated && (
            <div className="notice notice--warning" role="status">
              The investigated scope reached its size limit. Treat the result as incomplete.
            </div>
          )}
        </aside>
      </div>

      <footer className="app-footer">
        <span>ShellTrace · Synthetic investigation workspace</span>
        <span className="footer-disclaimer">For investigative use only — not legal advice.</span>
      </footer>
    </div>
  );
}

export default App;
