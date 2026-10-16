import { useEffect, useRef, useState } from 'react';
import { judgeAlias } from '../api.js';

const candidateKey = (candidate) => `${candidate.a_id}|${candidate.b_id}`;

function AliasPanel({ result, onDecide }) {
  const [activeKey, setActiveKey] = useState(null);
  const [accept, setAccept] = useState(true);
  const [reason, setReason] = useState('');
  const [confirmMerge, setConfirmMerge] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [judgements, setJudgements] = useState({});
  const [judgingKey, setJudgingKey] = useState(null);
  const judgeRequest = useRef(0);
  const caseGeneration = useRef(0);

  useEffect(() => {
    setActiveKey(null);
    setConfirmMerge(false);
    setError('');
    setJudgements({});
    setJudgingKey(null);
    setSubmitting(false);
    judgeRequest.current += 1;
    caseGeneration.current += 1;
    return () => { judgeRequest.current += 1; caseGeneration.current += 1; };
  }, [result?.case_id]);

  if (!result) return null;
  const candidates = result.alias_candidates || [];
  const activeCandidate = candidates.find((candidate) => candidateKey(candidate) === activeKey);

  const askJudge = async (candidate) => {
    const requestId = ++judgeRequest.current;
    const key = candidateKey(candidate);
    setJudgingKey(key);
    try {
      const advice = await judgeAlias(result.workspace, candidate.a_id, candidate.b_id);
      if (requestId === judgeRequest.current) setJudgements((current) => ({ ...current, [key]: advice }));
    } catch (cause) {
      if (requestId === judgeRequest.current) setJudgements((current) => ({ ...current, [key]: { error: cause.message || 'Recommendation unavailable. Try again.' } }));
    } finally {
      if (requestId === judgeRequest.current) setJudgingKey(null);
    }
  };

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
    const requestId = caseGeneration.current;
    setSubmitting(true);
    setError('');
    try {
      await onDecide(activeCandidate, accept, reason.trim(), confirmMerge);
      if (requestId !== caseGeneration.current) return;
      setActiveKey(null);
      setConfirmMerge(false);
      setReason('');
    } catch (cause) {
      if (requestId !== caseGeneration.current) return;
      const message = cause?.message || 'The alias decision could not be saved.';
      if (/API 409:/i.test(message) && /merge|cluster|confirm/i.test(message)) {
        setConfirmMerge(true);
        setError('This merge joins two clusters — confirm?');
      } else {
        setError(message);
      }
    } finally {
      if (requestId === caseGeneration.current) setSubmitting(false);
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
              {candidate.state === 'pending' && <div className="alias-advice">
                <button className="quiet-button" type="button" onClick={() => askJudge(candidate)} disabled={judgingKey !== null}>
                  {judgingKey === candidateKey(candidate) ? 'Checking identity…' : 'Ask JEV'}
                </button>
                {judgements[candidateKey(candidate)] && (() => {
                  const advice = judgements[candidateKey(candidate)];
                  if (advice.error) return <p className="inline-error" role="alert">{advice.error}</p>;
                  const label = { same_entity: 'Likely same entity', different_entity: 'Likely different entities', uncertain: 'Needs analyst review' }[advice.recommendation];
                  return <p role="status">{label}{advice.source === 'jev' && advice.confidence != null ? ` · ${Math.round(advice.confidence * 100)}% model confidence` : ''}. Analyst acceptance is required. {advice.model ? `Model: ${advice.model}.` : advice.source === 'fallback' ? 'JEV is unavailable or disabled.' : 'Identifier checks applied.'}</p>;
                })()}
              </div>}
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
