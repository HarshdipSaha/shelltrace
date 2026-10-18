const setFor = (result, field) => new Set(
  Object.values(result?.packs || {}).flatMap((pack) => pack?.[field] || []),
);

const flaggedFor = (result) => new Set(
  (result?.red_flags || []).flatMap((flag) => flag?.evidence_keys || []),
);

const showValue = (value) => value == null || value === '' ? 'Not supplied' : String(value);

function EvidenceLocker({ result, selectedKey }) {
  const evidence = selectedKey ? result?.evidence?.[selectedKey] : null;
  const proof = setFor(result, 'proof');
  const decisive = setFor(result, 'decisive');
  const flagged = flaggedFor(result);
  const safeUrl = /^https?:\/\//i.test(evidence?.url || '') ? evidence.url : null;

  return (
    <section className="evidence-locker panel" aria-label="Evidence locker">
      <div className="record-heading">
        <div>
          <p className="eyebrow">SOURCE RECORD</p>
          <h2>Evidence locker</h2>
        </div>
        {evidence && <code className="record-key">{selectedKey}</code>}
      </div>
      {!result ? (
        <p className="locker-hint">Run an investigation to load evidence records.</p>
      ) : !selectedKey ? (
        <p className="locker-hint">Select a graph edge or proof key to inspect its source, snapshot, and licence.</p>
      ) : !evidence ? (
        <p className="locker-hint">The selected record is not part of this case result.</p>
      ) : (
        <>
          <div className="locker-badges" aria-label="Evidence status">
            {proof.has(selectedKey) && <span className="locker-badge locker-badge--proof">In proof</span>}
            {decisive.has(selectedKey) && <span className="locker-badge locker-badge--decisive">Decisive</span>}
            {flagged.has(selectedKey) && <span className="locker-badge locker-badge--flagged">Flagged</span>}
          </div>
          <dl className="locker-record">
            <div><dt>Relationship</dt><dd>{showValue(evidence.type)}</dd></div>
            <div><dt>From</dt><dd>{showValue(evidence.from_name || evidence.from_id)}</dd></div>
            <div><dt>To</dt><dd>{showValue(evidence.to_name || evidence.to_id)}</dd></div>
            <div><dt>Stake / basis</dt><dd>{evidence.pct != null ? `${evidence.pct}% · ${showValue(evidence.basis)}` : showValue(evidence.basis)}</dd></div>
            {evidence.basis === 'accounting_consolidation' && <div><dt>Interpretation</dt><dd>Accounting consolidation; excluded from legal ownership totals.</dd></div>}
            <div><dt>Valid dates</dt><dd>{evidence.valid_from || 'open'} → {evidence.valid_to || 'present'}</dd></div>
            {(evidence.listed_on || evidence.delisted_on) && (
              <div><dt>Designation dates</dt><dd>{showValue(evidence.listed_on)} → {showValue(evidence.delisted_on)}</dd></div>
            )}
            {evidence.listed_on_basis && <div><dt>Date basis</dt><dd>{evidence.listed_on_basis === 'first_seen' ? 'First observed by source. Approximation, not an official listing date.' : showValue(evidence.listed_on_basis)}</dd></div>}
            <div><dt>Source</dt><dd>{showValue(evidence.src)}</dd></div>
            <div><dt>Source record</dt><dd>{showValue(evidence.src_record)}</dd></div>
            <div><dt>Snapshot</dt><dd>{showValue(evidence.snapshot || result.snapshot)}</dd></div>
            <div><dt>Licence</dt><dd>{showValue(evidence.licence)}</dd></div>
            <div><dt>URL</dt><dd>{safeUrl ? <a href={safeUrl} target="_blank" rel="noreferrer">Open source record</a> : showValue(evidence.url)}</dd></div>
          </dl>
        </>
      )}
    </section>
  );
}

export default EvidenceLocker;
