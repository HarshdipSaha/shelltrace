import { useEffect, useState } from 'react';
import { searchEntities } from '../api.js';

const PACKS = ['OFAC', 'EU', 'UK'];

function SearchPanel({
  workspace,
  health,
  healthLoading,
  healthError,
  entity,
  asOf,
  maxHops,
  packs,
  mode,
  loading,
  onSelectEntity,
  onChange,
  onRun,
  onRetryHealth,
}) {
  const [query, setQuery] = useState(entity?.name || '');
  const [hits, setHits] = useState([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const selectedId = entity?.id;
  const selectedName = entity?.name;

  useEffect(() => {
    let active = true;
    const term = query.trim();
    setSearching(false);
    if (term.length < 2 || (selectedName && term === selectedName)) {
      setHits([]);
      setOpen(false);
      setSearchError('');
      return () => { active = false; };
    }

    const timer = window.setTimeout(() => {
      if (!active) return;
      setSearching(true);
      searchEntities(workspace, term, 8)
        .then(({ hits: found = [] }) => {
          if (!active) return;
          setHits(found);
          setSearchError('');
          setOpen(true);
        })
        .catch((reason) => {
          if (!active) return;
          setHits([]);
          setSearchError(reason.message || 'Search is unavailable.');
          setOpen(true);
        })
        .finally(() => {
          if (active) setSearching(false);
        });
    }, 250);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [query, workspace, selectedId, selectedName]);

  const chooseEntity = (hit) => {
    onSelectEntity(hit);
    setQuery(hit.name);
    setHits([]);
    setOpen(false);
    setSearchError('');
  };

  const togglePack = (pack) => {
    const next = packs.includes(pack)
      ? packs.filter((item) => item !== pack)
      : PACKS.filter((item) => item === pack || packs.includes(item));
    onChange({ packs: next });
  };

  const agentUnavailable = health?.llm === 'deterministic';
  const agentChecking = healthLoading;
  const agentStatusUnknown = Boolean(healthError) && !healthLoading;
  const agentDisabled = agentUnavailable || agentChecking || agentStatusUnknown;

  return (
    <section className="search-panel panel" aria-labelledby="search-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">NEW INVESTIGATION</p>
          <h2 id="search-title">Case controls</h2>
        </div>
        <span className="workspace-pill">{workspace}</span>
      </div>

      <div className="field-block entity-search">
        <label htmlFor="entity-query">Entity</label>
        <div className="search-input-wrap">
          <span className="search-icon" aria-hidden="true">⌕</span>
          <input
            id="entity-query"
            type="search"
            placeholder="Search company, LEI or IMO"
            value={query}
            autoComplete="off"
            disabled={loading}
            aria-autocomplete="list"
            aria-controls="entity-options"
            aria-expanded={open && hits.length > 0}
            onChange={(event) => {
              setQuery(event.target.value);
              onSelectEntity(null);
            }}
            onFocus={() => { if (hits.length) setOpen(true); }}
            onKeyDown={(event) => {
              if (event.key === 'Escape') setOpen(false);
              if (event.key === 'Enter' && hits.length) {
                event.preventDefault();
                chooseEntity(hits[0]);
              }
            }}
          />
          {searching && <span className="search-spinner" aria-label="Searching" />}
        </div>
        {open && (
          <div className="search-results" id="entity-options" role="listbox" aria-label="Entity results">
            {searchError ? (
              <p className="search-message">{searchError}</p>
            ) : hits.length ? hits.map((hit) => (
              <button
                className="entity-option"
                key={hit.id}
                type="button"
                role="option"
                aria-selected={entity?.id === hit.id}
                onClick={() => chooseEntity(hit)}
              >
                <span className="option-main">
                  <strong>{hit.name}</strong>
                  <small>{hit.kind}{hit.country ? ` · ${hit.country}` : ''}</small>
                </span>
                <span className="option-tags">
                  {hit.designated && <span className="designated-chip">Designated</span>}
                  <span className="option-arrow" aria-hidden="true">↗</span>
                </span>
              </button>
            )) : <p className="search-message">No matching entities found.</p>}
          </div>
        )}
        {entity && !open && <p className="selected-entity-hint"><span className="selection-check">✓</span> Subject selected</p>}
      </div>

      <div className="field-row">
        <div className="field-block">
          <label htmlFor="as-of">As of</label>
          <input id="as-of" type="date" value={asOf} disabled={loading} onChange={(event) => onChange({ asOf: event.target.value })} />
        </div>
        <div className="field-block">
          <label htmlFor="max-hops">Max hops</label>
          <select id="max-hops" value={maxHops} disabled={loading} onChange={(event) => onChange({ maxHops: Number(event.target.value) })}>
            {[1, 2, 3, 4, 5, 6].map((hops) => <option key={hops} value={hops}>{hops} {hops === 1 ? 'hop' : 'hops'}</option>)}
          </select>
        </div>
      </div>

      <fieldset className="choice-fieldset">
        <legend>Rule packs</legend>
        <div className="pack-choices">
          {PACKS.map((pack) => (
            <label className="pack-choice" key={pack}>
              <input type="checkbox" checked={packs.includes(pack)} disabled={loading} onChange={() => togglePack(pack)} />
              <span>{pack}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="choice-fieldset mode-fieldset">
        <legend>Investigation mode</legend>
        <div className="mode-choices" role="group" aria-label="Investigation mode">
          <label className={`mode-choice ${mode === 'agent' ? 'mode-choice--active' : ''} ${agentDisabled ? 'mode-choice--disabled' : ''}`}>
            <input
              type="radio"
              name="mode"
              value="agent"
              checked={mode === 'agent'}
              disabled={agentDisabled || loading}
              onChange={() => onChange({ mode: 'agent' })}
            />
            <span><strong>Agent</strong><small>Claude-assisted</small></span>
          </label>
          <label className={`mode-choice ${mode === 'playbook' ? 'mode-choice--active' : ''}`}>
            <input
              type="radio"
              name="mode"
              value="playbook"
              checked={mode === 'playbook'}
              disabled={loading}
              onChange={() => onChange({ mode: 'playbook' })}
            />
            <span><strong>Playbook</strong><small>Deterministic</small></span>
          </label>
        </div>
        {agentUnavailable && <p className="mode-note">Agent mode is unavailable without a configured model key.</p>}
        {agentChecking && <p className="mode-note">Confirming model availability; playbook mode remains ready.</p>}
        {agentStatusUnknown && (
          <p className="mode-note mode-note--retry">
            Could not confirm model availability. Playbook mode remains ready.
            <button type="button" disabled={loading} onClick={onRetryHealth}>Retry status check</button>
          </p>
        )}
      </fieldset>

      <button className="run-button" type="button" disabled={loading || !entity || !packs.length} onClick={onRun}>
        {loading ? <><span className="button-spinner" /> Running investigation…</> : <>Run investigation <span aria-hidden="true">→</span></>}
      </button>
      {!packs.length && <p className="form-note">Select at least one rule pack to continue.</p>}
    </section>
  );
}

export default SearchPanel;
