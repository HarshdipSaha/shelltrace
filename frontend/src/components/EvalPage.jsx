import { useEffect, useState } from 'react';
import { evalLatest } from '../api.js';

const asArray = (value) => Array.isArray(value) ? value : [];
const asEntries = (value) => value && typeof value === 'object' && !Array.isArray(value) ? Object.entries(value) : [];

function EmptyRow({ columns, children }) {
  return <tr><td colSpan={columns} className="eval-empty-row">{children}</td></tr>;
}

function EvalPage({ workspace = 'demo' }) {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    evalLatest()
      .then((data) => { if (active) setPayload(data); })
      .catch((cause) => { if (active) setError(cause?.message || 'Evaluation data is unavailable.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const golden = payload?.golden;
  const playbook = golden?.playbook || golden || {};
  const goldenCases = asArray(golden?.cases || golden?.results || playbook?.cases);
  const ablations = asEntries(golden?.ablations || playbook?.ablations);
  const agent = golden?.agent || playbook?.agent || {};
  const e3 = payload?.real_e3;
  const e3Rows = asArray(e3?.strata || e3?.by_name_visibility || e3?.recall_by_stratum);
  const latencyRows = asEntries(golden?.latency || payload?.latency || golden?.latency_by_tool);
  const snapshots = golden?.snapshot_versions || golden?.snapshots || payload?.snapshot_versions || {};
  const pass5 = agent?.disposition_pass5 ?? agent?.pass5 ?? agent?.pass_5 ?? '—';

  return (
    <main className="eval-page" aria-label="Evaluation results">
      <header className="eval-page-header">
        <div><p className="eyebrow">SHELLTRACE / QUALITY EVALUATION</p><h1>Evaluation</h1><p>Golden behavior, ablations, real-data recall, and latency at the recorded snapshots.</p></div>
        <a className="quiet-button" href={`/?ws=${encodeURIComponent(workspace)}`}>Back to investigations</a>
      </header>
      {loading && <p className="eval-status" role="status">Loading evaluation results…</p>}
      {error && <p className="inline-error" role="alert">{error}</p>}
      {!loading && !error && !payload?.available && (
        <p className="eval-status" role="status">Evaluation data will appear after the golden suite and real-data evaluation have run.</p>
      )}

      <section className="eval-section panel" aria-label="Golden results by category">
        <div className="section-heading"><div><p className="eyebrow">DETERMINISTIC CASES</p><h2>Golden results by category</h2></div><span className="eval-score">{playbook.correct ?? '—'} / {playbook.total ?? (goldenCases.length || '—')}</span></div>
        <div className="eval-table-wrap"><table><thead><tr><th>Category</th><th>Case</th><th>Expected</th><th>Got</th><th>Status</th></tr></thead><tbody>
          {goldenCases.length ? goldenCases.map((item, index) => <tr key={item.id || index}><td>{item.category || 'Uncategorized'}</td><td>{item.id || item.case_id || `Case ${index + 1}`}</td><td>{item.expected || item.expect_disposition || '—'}</td><td>{item.got || item.actual || item.disposition || '—'}</td><td>{item.correct == null ? '—' : item.correct ? 'PASS' : 'FAIL'}</td></tr>) : <EmptyRow columns={5}>No golden case rows are available yet.</EmptyRow>}
        </tbody></table></div>
      </section>

      <section className="eval-section panel" aria-label="Ablation comparison">
        <div className="section-heading"><div><p className="eyebrow">COMPONENT CONTRIBUTION</p><h2>Ablations</h2></div></div>
        <div className="eval-table-wrap"><table><thead><tr><th>Method</th><th>Correct</th><th>Total</th><th>Score</th></tr></thead><tbody>
          {ablations.length ? ablations.map(([name, value]) => {
            const correct = typeof value === 'number' ? value : value?.correct;
            const total = typeof value === 'object' ? value?.total : golden?.total ?? playbook?.total;
            return <tr key={name}><td>{name.replaceAll('_', ' ')}</td><td>{correct ?? '—'}</td><td>{total ?? '—'}</td><td>{correct != null && total ? `${Math.round((correct / total) * 100)}%` : value?.score ?? '—'}</td></tr>;
          }) : <EmptyRow columns={4}>Ablation results are not available yet.</EmptyRow>}
          {['name_only', 'path_only', 'multiplicative', 'er_off', 'time_off', 'playbook', 'agent'].some((key) => !ablations.some(([name]) => name === key)) && <EmptyRow columns={4}>Expected methods: name-only, path-only, multiplicative, ER-off, time-off, playbook, and agent.</EmptyRow>}
        </tbody></table></div>
      </section>

      <div className="eval-two-column">
        <section className="eval-section panel" aria-label="Agent repeatability">
          <div className="section-heading"><div><p className="eyebrow">REPEATABILITY</p><h2>Pass<sup>5</sup></h2></div></div>
          <dl className="eval-metrics"><div><dt>Validated disposition</dt><dd>{pass5}</dd></div><div><dt>Proposal agreement pass<sup>5</sup></dt><dd>{agent?.proposal_agreement_pass5 ?? agent?.proposal_pass5 ?? '—'}</dd></div><div><dt>Mean explore steps</dt><dd>{agent?.mean_explore_steps ?? '—'}</dd></div><div><dt>Mean model calls</dt><dd>{agent?.mean_model_calls ?? '—'}</dd></div><div><dt>Mean latency</dt><dd>{agent?.mean_latency_ms != null ? `${agent.mean_latency_ms} ms` : '—'}</dd></div></dl>
        </section>

        <section className="eval-section panel" aria-label="E3 recall by name visibility">
          <div className="section-heading"><div><p className="eyebrow">REAL-DATA EVALUATION</p><h2>E3 recall by name visibility</h2></div></div>
          <div className="eval-table-wrap"><table><thead><tr><th>Stratum</th><th>Recall</th><th>Hits / positives</th></tr></thead><tbody>
            {e3Rows.length ? e3Rows.map((row, index) => <tr key={row.name_visibility || row.stratum || index}><td>{row.name_visibility || row.stratum || row.name || '—'}</td><td>{row.recall ?? '—'}</td><td>{row.hits ?? row.correct ?? '—'} / {row.positives ?? row.total ?? '—'}</td></tr>) : <EmptyRow columns={3}>E3 recall results are not available yet.</EmptyRow>}
          </tbody></table></div>
        </section>
      </div>

      <section className="eval-section panel" aria-label="Tool latency">
        <div className="section-heading"><div><p className="eyebrow">PERFORMANCE</p><h2>Tool latency</h2></div></div>
        <div className="eval-table-wrap"><table><thead><tr><th>Tool</th><th>p50</th><th>p95</th><th>Samples</th></tr></thead><tbody>
          {latencyRows.length ? latencyRows.map(([tool, value]) => <tr key={tool}><td>{tool}</td><td>{value.p50_ms ?? value.p50 ?? '—'} ms</td><td>{value.p95_ms ?? value.p95 ?? '—'} ms</td><td>{value.n ?? value.samples ?? '—'}</td></tr>) : <EmptyRow columns={4}>Latency measurements are not available yet.</EmptyRow>}
        </tbody></table></div>
      </section>

      <footer className="eval-snapshots"><span>Snapshot versions</span>{asEntries(snapshots).length ? asEntries(snapshots).map(([name, version]) => <code key={name}>{name}: {version}</code>) : <code>Not recorded yet</code>}</footer>
    </main>
  );
}

export default EvalPage;
