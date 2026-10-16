import { useEffect, useRef, useState } from 'react';
import { searchEntities } from '../api.js';

function WatchBar({ workspace, result, onWatch, onInject }) {
  const [watching, setWatching] = useState(false);
  const [watchBusy, setWatchBusy] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState([]);
  const [selectedEntity, setSelectedEntity] = useState(null);
  const [authority, setAuthority] = useState('OFAC');
  const [program, setProgram] = useState('SDN (demo)');
  const [listedOn, setListedOn] = useState('2024-03-15');
  const [source, setSource] = useState('Demo injection');
  const [injecting, setInjecting] = useState(false);
  const [toast, setToast] = useState('');
  const [error, setError] = useState('');
  const watchRequest = useRef(0);

  useEffect(() => {
    setWatching(false);
    setWatchBusy(false);
    setError('');
    setToast('');
    watchRequest.current += 1;
    return () => { watchRequest.current += 1; };
  }, [result?.case_id, workspace]);

  useEffect(() => {
    let active = true;
    const term = query.trim();
    if (term.length < 2) {
      setHits([]);
      return () => { active = false; };
    }
    const timer = window.setTimeout(() => {
      searchEntities(workspace, term, 6)
        .then(({ hits: found = [] }) => { if (active) setHits(found); })
        .catch((cause) => { if (active) setError(cause?.message || 'Entity search failed.'); });
    }, 200);
    return () => { active = false; window.clearTimeout(timer); };
  }, [query, workspace]);

  const toggleWatch = async (event) => {
    const requestId = ++watchRequest.current;
    const next = event.target.checked;
    setWatchBusy(true);
    setError('');
    try {
      await onWatch(next);
      if (requestId === watchRequest.current) setWatching(next);
    } catch (cause) {
      if (requestId === watchRequest.current) setError(cause?.message || 'Watch status could not be changed.');
    } finally {
      if (requestId === watchRequest.current) setWatchBusy(false);
    }
  };

  const inject = async (event) => {
    event.preventDefault();
    if (!selectedEntity) return;
    setInjecting(true);
    setError('');
    try {
      const outcome = await onInject({
        entity_id: selectedEntity.id,
        authority,
        program: program.trim(),
        listed_on: listedOn,
        source: source.trim(),
      });
      const newlyBlocked = outcome.blast_radius?.length || 0;
      const changed = outcome.notifications?.length || 0;
      setToast(`${newlyBlocked} entities newly blocked · ${changed} watched case(s) changed`);
    } catch (cause) {
      setError(cause?.message || 'The designation could not be injected.');
    } finally {
      setInjecting(false);
    }
  };

  return (
    <section className="watch-bar panel" aria-label="Watch and demo controls">
      <div className="section-heading">
        <div><p className="eyebrow">CHANGE MONITORING</p><h2>Watch this case</h2></div>
        <span className="workspace-pill">{workspace}</span>
      </div>
      {result ? (
        <label className="watch-toggle">
          <input type="checkbox" aria-label="Watch this case" checked={watching} disabled={watchBusy} onChange={toggleWatch} />
          <span className="watch-switch" aria-hidden="true" />
          <span>{watchBusy ? 'Updating watch…' : watching ? 'Watching for changes' : 'Watch case for changes'}</span>
        </label>
      ) : <p className="watch-hint">Open a case to watch for future designation changes.</p>}

      <button className="disclosure-button" type="button" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
        <span>Demo: inject designation</span><span aria-hidden="true">{expanded ? '−' : '+'}</span>
      </button>
      {expanded && (
        <div className="designation-form-wrap" role="region" aria-label="Demo designation injection">
          <p className="watch-hint">Add a dated demo designation and recheck watched cases in this workspace.</p>
          <form className="designation-form" onSubmit={inject}>
            <label>Entity
              <input aria-label="Designation entity" autoComplete="off" value={query} onChange={(event) => { setQuery(event.target.value); setSelectedEntity(null); }} placeholder="Search an entity" />
            </label>
            {hits.length > 0 && !selectedEntity && (
              <div className="designation-results" role="listbox" aria-label="Designation entity results">
                {hits.map((hit) => (
                  <button type="button" role="option" key={hit.id} onClick={() => { setSelectedEntity(hit); setQuery(hit.name); setHits([]); }}>
                    <strong>{hit.name}</strong><small>{hit.id}</small>
                  </button>
                ))}
              </div>
            )}
            {selectedEntity && <span className="selected-designation">Selected: {selectedEntity.id}</span>}
            <div className="designation-field-row">
              <label>Authority
                <select aria-label="Authority" value={authority} onChange={(event) => setAuthority(event.target.value)}>
                  {['OFAC', 'EU', 'UK'].map((item) => <option key={item}>{item}</option>)}
                </select>
              </label>
              <label>Listed on
                <input aria-label="Listed on" type="date" value={listedOn} onChange={(event) => setListedOn(event.target.value)} />
              </label>
            </div>
            <label>Program
              <input aria-label="Program" value={program} onChange={(event) => setProgram(event.target.value)} />
            </label>
            <label>Source
              <input aria-label="Source" value={source} onChange={(event) => setSource(event.target.value)} />
            </label>
            <button className="action-button" type="submit" disabled={!selectedEntity || !program.trim() || !listedOn || !source.trim() || injecting}>
              {injecting ? 'Injecting…' : 'Inject designation'}
            </button>
          </form>
        </div>
      )}
      {toast && <p className="designation-toast" role="status">{toast}</p>}
      {error && <p className="inline-error" role="alert">{error}</p>}
    </section>
  );
}

export default WatchBar;
