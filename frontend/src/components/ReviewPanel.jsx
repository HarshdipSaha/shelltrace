import { useEffect, useState } from 'react';

const REVIEW_CODES = [
  'CONFIRMED_EXPOSED',
  'CONFIRMED_CLEAR',
  'FALSE_POSITIVE_ALIAS',
  'ESCALATED_RED_FLAG',
  'OVERRIDDEN',
];

const REMOVES_EXPOSURE = new Set(['CONFIRMED_CLEAR', 'FALSE_POSITIVE_ALIAS', 'OVERRIDDEN']);

function ReviewPanel({ result, onSubmit }) {
  const [code, setCode] = useState('CONFIRMED_EXPOSED');
  const [reason, setReason] = useState('');
  const [reviewer, setReviewer] = useState('');
  const [secondReviewer, setSecondReviewer] = useState('');
  const [history, setHistory] = useState([]);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const needsSecondReviewer = result?.disposition === 'EXPOSED' && REMOVES_EXPOSURE.has(code);

  useEffect(() => {
    setHistory([]);
    setError('');
    setCode('CONFIRMED_EXPOSED');
  }, [result?.case_id]);

  const submit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const saved = await onSubmit({
        code,
        reason: reason.trim(),
        reviewer: reviewer.trim(),
        ...(needsSecondReviewer ? { second_reviewer: secondReviewer.trim() } : {}),
      });
      setHistory((current) => [saved, ...current]);
      setReason('');
      setError('');
    } catch (cause) {
      const message = cause?.message || 'The review could not be saved.';
      setError(/second reviewer is required/i.test(message)
        ? 'A second reviewer is required to remove an exposure'
        : message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="review-panel panel" aria-label="Review disposition">
      <div className="section-heading">
        <div><p className="eyebrow">HUMAN REVIEW</p><h2>Disposition review</h2></div>
        {result && <code className="review-case-id">{result.case_id}</code>}
      </div>
      {!result ? (
        <p className="review-hint">Open a case before recording an analyst review.</p>
      ) : (
        <>
          <form className="review-form" onSubmit={submit}>
            <label>Review code
              <select aria-label="Review code" value={code} onChange={(event) => setCode(event.target.value)}>
                {REVIEW_CODES.map((item) => <option key={item} value={item}>{item.replaceAll('_', ' ')}</option>)}
              </select>
            </label>
            <label>Reason <small>{reason.length}/10 minimum</small>
              <textarea aria-label="Reason" minLength={10} value={reason} onChange={(event) => setReason(event.target.value)} rows={3} />
            </label>
            <div className="reviewer-fields">
              <label>Reviewer
                <input aria-label="Reviewer" value={reviewer} onChange={(event) => setReviewer(event.target.value)} minLength={2} />
              </label>
              {needsSecondReviewer && (
                <label>Second reviewer
                  <input aria-label="Second reviewer" value={secondReviewer} onChange={(event) => setSecondReviewer(event.target.value)} minLength={2} />
                </label>
              )}
            </div>
            {needsSecondReviewer && <p className="review-four-eyes">A separate reviewer must confirm a decision that removes an exposure.</p>}
            <button className="action-button" type="submit" disabled={submitting || reason.trim().length < 10 || reviewer.trim().length < 2}>
              {submitting ? 'Saving review…' : 'Submit review'}
            </button>
          </form>
          {error && <p className="inline-error" role="alert">{error}</p>}
          {history.length > 0 && (
            <div className="review-history" aria-label="Review history">
              <span className="pack-section-label">Review history</span>
              {history.map((item, index) => (
                <article className="review-history-item" key={`${item.at}-${index}`}>
                  <strong>{item.code.replaceAll('_', ' ')}</strong>
                  <span>{item.reviewer} · {item.at}</span>
                  <p>{item.reason}</p>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}

export default ReviewPanel;
