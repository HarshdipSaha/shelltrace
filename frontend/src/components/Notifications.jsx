import { useEffect, useState } from 'react';
import { getCase, notifications as fetchNotifications } from '../api.js';

function Notifications({ workspace, refreshSignal = 0, onOpenCase }) {
  const [items, setItems] = useState([]);
  const [names, setNames] = useState({});
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setItems([]);
    setNames({});
    setError('');
  }, [workspace]);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const result = await fetchNotifications(workspace);
        if (active) { setItems(result || []); setError(''); }
      } catch (cause) {
        if (active) setError(cause?.message || 'Notifications are unavailable.');
      }
    };
    refresh();
    const interval = open ? window.setInterval(refresh, 5000) : null;
    return () => { active = false; if (interval) window.clearInterval(interval); };
  }, [workspace, refreshSignal, open]);

  useEffect(() => {
    let active = true;
    const missing = [...new Set(items.map((item) => item.case_id))].filter((caseId) => !names[caseId]);
    if (!missing.length) return () => { active = false; };
    Promise.all(missing.map(async (caseId) => {
      try {
        const result = await getCase(workspace, caseId);
        return [caseId, result.entity?.name || caseId];
      } catch {
        return [caseId, caseId];
      }
    })).then((entries) => {
      if (active) setNames((current) => ({ ...current, ...Object.fromEntries(entries) }));
    });
    return () => { active = false; };
  }, [items, names, workspace]);

  return (
    <section className="notifications-panel panel" aria-label="Case notifications">
      <button className="notifications-toggle" type="button" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <span><span className="eyebrow">CHANGE FEED</span><strong>Notifications</strong></span>
        <span className="notification-count">{items.length}</span>
      </button>
      {open && (
        <div className="notifications-drawer" role="region" aria-label="Notifications">
          {error && <p className="inline-error" role="alert">{error}</p>}
          {items.length === 0 ? <p className="watch-hint">No watched cases have changed.</p> : items.map((item) => (
            <article className="notification-item" key={`${item.event_id}-${item.case_id}`}>
              <div className="notification-heading"><strong>{names[item.case_id] || 'Loading case…'}</strong><time>{item.at}</time></div>
              <p className="notification-transition">{item.old} → {item.new}</p>
              <p className="notification-event">Designation event <code>{item.event_id}</code></p>
              <a href={`?ws=${encodeURIComponent(workspace)}#${item.diff?.new_case_id || item.new_case_id || item.case_id}`} onClick={(event) => { event.preventDefault(); onOpenCase?.(item); }}>View diff</a>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export default Notifications;
