import { useEffect, useState } from 'react';

const candidateKey = (candidate) => `${candidate.a_id}|${candidate.b_id}`;

function AliasPanel({ result, onDecide }) {
  const [activeKey, setActiveKey] = useState(null);
  const [accept, setAccept] = useState(true);
  const [reason, setReason] = useState('');
  const [confirmMerge, setConfirmMerge] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setActiveKey(null);
    setConfirmMerge(false);
    setError('');
  }, [result?.case_id]);

  if (!result) return null;
  const candidates = result.alias_candidates || [];
  const activeCandidate = candidates.find((candidate) => candidateKey(candidate) === activeKey);

  const begin = (candidate, acceptValue) => {
    setActiveKey(candidateKey(candidate));
    setAccept(acceptValue);
    setReason('');
    setConfirmMerge(false);
    setError('');
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!activeCandidate) return;
    setSubmitting(true);
    setError('');
    try {
      await onDecide(activeCandidate, accept, reason.trim(), confirmMerge);
      setActiveKey(null);
      setConfirmMerge(false);
      setReason('');
    } catch (cause) {
      const message = cause?.message || 'The alias decision could not be saved.';
      if (/API 409:/i.test(message) && /merge|cluster|confirm/i.test(message)) {
        setConfirmMerge(true);
        setError('This merge joins two clusters — confirm?');
      } else {
        setError(message);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="alias-panel panel" aria-label="Alias decisions">
      <div className="section-heading"><div><p className="eyebrow">ENTITY RESOLUTION</p><h2>Alias decisions</h2></div></div>
      {candidates.length === 0 ? (
        <p className="alias-hint">No alias candidates need review for this case.</p>
      ) : (
        <div className="alias-list">
          {candidates.map((candidate) => (
            <article className={`alias-card alias-card--${candidate.state}`} key={candidateKey(candidate)}>
              <div className="alias-card-heading"><span>{candidate.state}</span><strong>{Math.round(candidate.score * 100)}% match</strong></div>
              <p className="alias-pair"><strong>{candidate.a_name}</strong><span>↔</span><strong>{candidate.b_name}</strong></p>
              <p className="alias-reason">{candidate.reason.replaceAll('_', ' ')}{candidate.touches_designated ? ' · touches a designated party' : ''}</p>
              {candidate.state === 'rejected' ? (
                <p className="alias-rejected">Rejected: {candidate.reason || 'No reason recorded.'}</p>
              ) : candidate.state === 'accepted' ? (
                <p className="alias-accepted">Accepted into the entity cluster.</p>
              ) : activeKey === candidateKey(candidate) ? (
                <form className="alias-decision-form" onSubmit={submit}>
                  <label>Decision reason
                    <textarea aria-label="Decision reason" minLength={10} rows={2} value={reason} onChange={(event) => setReason(event.target.value)} />
                  </label>
                  {error && <p className="inline-error" role="alert">{error}</p>}
                  <div className="alias-action-row">
                    <button className="action-button" type="submit" disabled={reason.trim().length < 10 || submitting}>
                      {submitting ? 'Saving…' : confirmMerge ? 'Confirm merge' : accept ? 'Confirm accept' : 'Confirm reject'}
                    </button>
                    <button className="quiet-button" type="button" onClick={() => setActiveKey(null)}>Cancel</button>
                  </div>
                </form>
              ) : (
                <div className="alias-action-row">
                  <button className="action-button" type="button" onClick={() => begin(candidate, true)}>Accept alias</button>
                  <button className="quiet-button" type="button" onClick={() => begin(candidate, false)}>Reject</button>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export default AliasPanel;
