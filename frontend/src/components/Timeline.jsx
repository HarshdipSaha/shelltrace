function compactValue(value) {
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  return text.length > 24 ? `${text.slice(0, 21)}…` : text;
}

function Timeline({ result, selected, onSelect }) {
  const steps = result?.steps || [];
  const lastStep = steps.at(-1);

  return (
    <section className="timeline-panel panel" aria-labelledby="timeline-title">
      <div className="section-heading timeline-heading">
        <div>
          <p className="eyebrow">AUDIT TRAIL</p>
          <h2 id="timeline-title">Decision timeline</h2>
        </div>
        {steps.length > 0 && <span className="step-count">{steps.length} steps</span>}
      </div>

      {!steps.length ? (
        <div className="timeline-empty">
          <span className="timeline-empty-mark" aria-hidden="true">↳</span>
          <p>Each lookup, proposal, and policy check will appear here.</p>
        </div>
      ) : (
        <div className="timeline-list">
          {steps.map((step) => {
            const args = Object.entries(step.args || {});
            const probability = Number.isFinite(step.probability)
              ? Math.max(0, Math.min(1, step.probability))
              : null;
            return (
              <article className={`timeline-step ${step.fallback_reason ? 'step--fallback' : ''}`} data-testid="timeline-step" key={`${step.seq}-${step.hash}`}>
                <div className="step-marker"><span>{String(step.seq).padStart(2, '0')}</span></div>
                <div className="step-content">
                  <div className="step-title-line">
                    <strong>{step.tool || step.kind}</strong>
                    <span className="actor-chip">{step.actor}</span>
                  </div>
                  <div className="step-meta-line">
                    <span className="step-kind">{step.kind}</span>
                    <span>{step.latency_ms} ms</span>
                  </div>
                  {args.length > 0 && (
                    <p className="step-args">{args.map(([key, value]) => `${key}=${compactValue(value)}`).join(' · ')}</p>
                  )}
                  {step.rationale && <p className="step-rationale">{step.rationale}</p>}
                  {step.fallback_reason && <span className="fallback-note">Fallback: {step.fallback_reason}</span>}
                  {probability !== null && (
                    <div className="probability-row">
                      <span>Proposal confidence</span>
                      <span className="probability-track"><span style={{ width: `${probability * 100}%` }} /></span>
                      <strong>{probability.toFixed(2)}</strong>
                    </div>
                  )}
                  {step.evidence_keys?.length > 0 && (
                    <div className="evidence-keys" aria-label="Evidence keys">
                      {step.evidence_keys.map((key) => (
                        <button
                          className={`evidence-key ${selected === key ? 'evidence-key--selected' : ''}`}
                          type="button"
                          key={key}
                          onClick={() => onSelect(key)}
                          title={`Inspect ${key}`}
                        >{key}</button>
                      ))}
                    </div>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}

      {lastStep && (
        <div className="chain-status"><span className="chain-check">✓</span><span>Hash chain ✓</span><code>{lastStep.hash.slice(0, 12)}</code></div>
      )}
    </section>
  );
}

export default Timeline;
