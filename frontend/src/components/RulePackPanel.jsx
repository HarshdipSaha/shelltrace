const clamp = (value) => Math.max(0, Math.min(100, Number(value) || 0));

const percent = (value) => {
  if (value == null) return '?';
  return Number.isInteger(Number(value)) ? `${Number(value)}` : Number(value).toFixed(1);
};

const decisiveLabel = (kind) => {
  if (kind === 'counterfactual') return 'records the verdict depends on';
  if (kind === 'unknown_or_conflict') return 'unknown or conflicting stakes';
  return 'no counterfactual record';
};

function RulePackPanel({ result }) {
  if (!result) return null;

  const packs = result.rulepacks
    .map((id) => result.packs?.[id])
    .filter(Boolean);

  return (
    <section className="rule-pack-panel panel" aria-label="Rule pack intervals">
      <div className="section-heading rule-pack-heading">
        <div>
          <p className="eyebrow">REGIME COMPARISON</p>
          <h2>Rule-pack intervals</h2>
        </div>
        <span className="rule-pack-date">{result.as_of}</span>
      </div>
      <div className="rule-pack-list">
        {packs.map((pack) => {
          const id = pack.rulepack;
          const low = clamp(pack.lo ?? 0);
          const high = clamp(pack.hi ?? 100);
          const start = Math.min(low, high);
          const width = Math.max(1, Math.max(low, high) - start);
          const threshold = clamp(pack.threshold ?? 50);
          const verdictClass = (pack.verdict || 'unknown').toLowerCase().replaceAll('_', '-');

          return (
            <article className="rule-pack-card" key={id}>
              <div className="rule-pack-card-heading">
                <div className="rule-pack-name"><strong>{id}</strong><small>{pack.version}</small></div>
                <span
                  className={`pack-verdict-chip pack-verdict-chip--${verdictClass}`}
                  data-testid={`pack-verdict-${id}`}
                >
                  {pack.verdict}
                </span>
              </div>
              <svg
                className="interval-meter"
                viewBox="0 0 100 28"
                preserveAspectRatio="none"
                role="img"
                aria-label={`${id} ownership interval ${percent(pack.lo)} to ${percent(pack.hi)} percent`}
              >
                <rect className="interval-meter-track" x="0" y="5" width="100" height="6" rx="3" />
                <rect
                  className={`interval-meter-span interval-meter-span--${verdictClass}`}
                  x={start}
                  y="5"
                  width={width}
                  height="6"
                  rx="3"
                />
                <line
                  className={`interval-threshold ${pack.inclusive ? 'interval-threshold--inclusive' : 'interval-threshold--strict'}`}
                  x1={threshold}
                  x2={threshold}
                  y1="2"
                  y2="15"
                  data-testid={`interval-threshold-${id}`}
                />
                <text className="interval-scale-edge" x="0" y="25">0%</text>
                <text className="interval-threshold-caption" x={threshold} y="25" textAnchor="middle">
                  {pack.inclusive ? '≥' : '>'}{percent(pack.threshold)}%
                </text>
                <text className="interval-scale-edge" x="100" y="25" textAnchor="end">100%</text>
              </svg>
              <p className="interval-values">lo <strong>{percent(pack.lo)}%</strong><i /> hi <strong>{percent(pack.hi)}%</strong></p>

              {pack.decisive?.length > 0 && (
                <div className="pack-evidence-section">
                  <span className="pack-section-label">Decisive records</span>
                  <p className="pack-helper">{decisiveLabel(pack.decisive_kind)}</p>
                  <div className="pack-evidence-keys">
                    {pack.decisive.map((key) => <code key={key}>{key}</code>)}
                  </div>
                </div>
              )}
              {pack.presumptions?.length > 0 && (
                <div className="pack-evidence-section pack-presumptions">
                  <span className="pack-section-label">Control presumptions</span>
                  <div className="pack-evidence-keys">
                    {pack.presumptions.map((key) => <code key={key}>{key}</code>)}
                  </div>
                  <p className="pack-helper">Shown separately from ownership arithmetic.</p>
                </div>
              )}
              {pack.interpretation_note && <p className="pack-interpretation">{pack.interpretation_note}</p>}
              {pack.caveats?.length > 0 && (
                <ul className="pack-caveats">
                  {pack.caveats.map((caveat, index) => <li key={`${id}-caveat-${index}`}>{caveat}</li>)}
                </ul>
              )}
              <div className="pack-run-stats"><span>{pack.rounds} rounds</span><span>{pack.latency_ms} ms</span></div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export default RulePackPanel;
