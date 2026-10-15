import { useEffect, useState } from 'react';

function ReportPanel({ result, onDraft, onSelect }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setReport(null);
    setError('');
    setCopied(false);
  }, [result?.case_id]);

  const draft = async () => {
    setLoading(true);
    setError('');
    setCopied(false);
    try {
      setReport(await onDraft());
    } catch (cause) {
      setReport(null);
      setError(cause?.message || 'The report could not be drafted.');
    } finally {
      setLoading(false);
    }
  };

  const copyMarkdown = async () => {
    if (!report?.markdown) return;
    try {
      await navigator.clipboard.writeText(report.markdown);
      setCopied(true);
    } catch {
      setError('Clipboard access is unavailable. Select and copy the Markdown text below.');
    }
  };

  return (
    <section className="report-panel panel" aria-label="Cited investigation report">
      <div className="section-heading">
        <div><p className="eyebrow">EVIDENCE SUMMARY</p><h2>Investigation report</h2></div>
        {report && <span className="report-writer">Writer: {report.writer}</span>}
      </div>
      <button className="action-button" type="button" disabled={!result || loading} onClick={draft}>
        {loading ? 'Drafting report…' : 'Draft report'}
      </button>
      {!result && <p className="report-hint">Open a case to draft a cited report.</p>}
      {error && <p className="inline-error" role="alert">{error}</p>}
      {report && (
        <>
          <div className="report-sentences">
            {(report.sentences || []).map((sentence, index) => (
              <article
                className={`report-sentence ${sentence.supported === false ? 'report-sentence--unsupported' : ''}`}
                data-testid="report-sentence"
                data-kind={sentence.kind}
                key={`${sentence.kind}-${index}`}
              >
                {sentence.supported === false ? <del>{sentence.text}</del> : <p>{sentence.text}</p>}
                {sentence.supported === false && <span className="report-problem">Problem: {sentence.problem || 'Unsupported claim'}</span>}
                {sentence.keys?.length > 0 && (
                  <div className="report-citations" aria-label="Citation keys">
                    {sentence.keys.map((key, keyIndex) => (
                      <button
                        className="report-citation"
                        data-testid="report-citation"
                        type="button"
                        aria-label={`Select evidence ${key}`}
                        key={`${key}-${keyIndex}`}
                        onClick={() => onSelect?.(key)}
                      >
                        [{key}]
                      </button>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
          <div className="report-copy-row">
            <button className="quiet-button" type="button" onClick={copyMarkdown}>{copied ? 'Copied Markdown' : 'Copy Markdown'}</button>
            <details>
              <summary>Preview Markdown</summary>
              <pre>{report.markdown}</pre>
            </details>
          </div>
        </>
      )}
    </section>
  );
}

export default ReportPanel;
