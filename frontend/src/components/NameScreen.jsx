import { useEffect, useRef, useState } from 'react';

const SCREENING_TOOLTIP = 'List lookup only — what ShellTrace adds is the ownership graph';

function NameScreen({ result, onScreen }) {
  const [screening, setScreening] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const activeCaseId = useRef(result?.case_id);
  activeCaseId.current = result?.case_id;

  useEffect(() => {
    setScreening(null);
    setLoading(false);
    setError('');
  }, [result?.case_id]);

  const run = async () => {
    if (!result) return;
    const caseId = result.case_id;
    setLoading(true);
    setError('');
    try {
      const nextScreening = await onScreen();
      if (activeCaseId.current === caseId) setScreening(nextScreening);
    } catch (cause) {
      if (activeCaseId.current === caseId) {
        setScreening(null);
        setError(cause?.message || 'Name screening is unavailable.');
      }
    } finally {
      if (activeCaseId.current === caseId) setLoading(false);
    }
  };

  return (
    <section className="name-screen panel" aria-label="Name screening baseline">
      <div className="section-heading"><div><p className="eyebrow">BASELINE COMPARISON</p><h2>Name screening</h2></div></div>
      <button className="quiet-button" type="button" disabled={!result || loading} onClick={run}>
        {loading ? 'Screening…' : 'Run name screen'}
      </button>
      {!result && <p className="screening-hint">Open a case to compare its name with designated-list entries.</p>}
      {screening && (
        <div className="screening-result" title={SCREENING_TOOLTIP}>
          <strong>{screening.hit
            ? `Name screen: hit (score ${Math.round(screening.matches?.[0]?.score || 0)} on ${screening.matches?.[0]?.name || 'listed entity'})`
            : 'Name screen: no hit'}</strong>
          {screening.matches?.length > 0 && (
            <ul>{screening.matches.map((match) => <li key={`${match.id}-${match.authority}`}>{match.name} · {match.authority} · {Math.round(match.score)}</li>)}</ul>
          )}
        </div>
      )}
      {error && <p className="inline-error" role="alert">{error}</p>}
      {screening && <p className="screening-note">List lookup only — the validated disposition uses the ownership graph.</p>}
    </section>
  );
}

export default NameScreen;
