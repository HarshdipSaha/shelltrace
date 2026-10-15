const dispositionClass = {
  EXPOSED: 'badge--exposed',
  ESCALATE: 'badge--escalate',
  CLEAR_WITHIN_BOUNDS: 'badge--clear',
};

function CaseHeader({ result }) {
  if (!result) {
    return (
      <section className="case-header case-header--empty" aria-label="Case disposition">
        <div className="case-header-topline">
          <div><p className="eyebrow">VALIDATION STATUS</p><h2>Disposition summary</h2></div>
          <span className="pending-label"><span /> Awaiting investigation</span>
        </div>
        <p className="case-header-hint">Validated outcome and agent proposal will be shown separately.</p>
      </section>
    );
  }

  const disposition = result.disposition;
  const reason = result.reasons?.[0];
  const bounds = result.bounds;

  return (
    <section className="case-header" aria-label="Case disposition">
      <div className="case-header-topline">
        <div><p className="eyebrow">VALIDATION STATUS</p><h2>Disposition summary</h2></div>
        <span className="latency-chip">{result.latency_ms} ms <span>·</span> {result.actor_model}</span>
      </div>

      <div className="disposition-badges">
        <span className="disposition-badge badge--proposal" data-testid="proposal-badge">
          <span className="badge-symbol" aria-hidden="true">✦</span>
          Agent proposal: {result.mode === 'playbook' ? '—' : result.proposal?.disposition || '—'}
        </span>
        <span className={`disposition-badge ${dispositionClass[disposition] || ''}`} data-testid="validated-badge">
          <span className="badge-symbol" aria-hidden="true">{disposition === 'EXPOSED' ? '!' : disposition === 'ESCALATE' ? '⌁' : '✓'}</span>
          Validated disposition: {disposition}
        </span>
      </div>

      {result.proposal_overridden && (
        <div className="override-note">
          <strong>Proposal overridden by policy</strong>
          {reason && <span>{reason.detail}</span>}
        </div>
      )}

      {disposition === 'CLEAR_WITHIN_BOUNDS' ? (
        <p className="bounds-sentence">
          No blocking exposure found within {bounds.max_hops} hops over {bounds.rel_scope.join(', ')} as of {bounds.as_of} ({bounds.snapshot}).
        </p>
      ) : (
        <div className="reason-row" aria-label="Disposition reasons">
          {(result.reasons || []).map((item) => (
            <span className="reason-chip" key={item.code} title={item.detail}>{item.code}</span>
          ))}
          {!result.reasons?.length && <span className="reason-chip">Policy validation complete</span>}
        </div>
      )}
    </section>
  );
}

export default CaseHeader;
