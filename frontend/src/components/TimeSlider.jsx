import { useEffect, useMemo, useState } from 'react';

const DATE_FIELDS = ['valid_from', 'valid_to', 'listed_on', 'delisted_on'];

function TimeSlider({ result, onChangeAsOf, loading = false }) {
  const resultDates = useMemo(() => {
    if (!result) return [];
    const evidenceDates = Object.values(result.evidence || {}).flatMap((item) => (
      DATE_FIELDS.map((field) => item[field]).filter(Boolean)
    ));
    return [...new Set([...evidenceDates, result.as_of].filter(Boolean))].sort();
  }, [result]);
  const [dateHistory, setDateHistory] = useState({ entityId: null, dates: [] });
  const sameEntity = dateHistory.entityId === result?.entity?.id;
  const dates = useMemo(() => [...new Set([
    ...(sameEntity ? dateHistory.dates : []),
    ...resultDates,
  ])].sort(), [dateHistory, resultDates, sameEntity]);
  const [pendingDate, setPendingDate] = useState(null);

  useEffect(() => {
    if (!result?.entity?.id) return;
    setDateHistory((current) => {
      const previousDates = current.entityId === result.entity.id ? current.dates : [];
      const mergedDates = [...new Set([...previousDates, ...resultDates])].sort();
      if (current.entityId === result.entity.id && mergedDates.length === previousDates.length) return current;
      return { entityId: result.entity.id, dates: mergedDates };
    });
  }, [result?.entity?.id, resultDates]);

  useEffect(() => {
    setPendingDate(null);
  }, [result?.case_id, result?.as_of]);

  useEffect(() => {
    if (!pendingDate || pendingDate === result?.as_of) return undefined;
    const timer = window.setTimeout(() => onChangeAsOf(pendingDate), 400);
    return () => window.clearTimeout(timer);
  }, [pendingDate, result?.as_of, onChangeAsOf]);

  if (!result) return null;

  const date = pendingDate || result.as_of;
  const selectedIndex = Math.max(0, dates.indexOf(date));
  const lastIndex = Math.max(0, dates.length - 1);

  return (
    <section className="time-slider-panel panel" aria-label="Investigation time slider">
      <div className="time-slider-heading">
        <div>
          <p className="eyebrow">DATED VIEW</p>
          <h2>Replay this case</h2>
        </div>
        <output className="time-slider-date" data-testid="slider-date">{date}</output>
      </div>
      <label className="time-slider-control">
        <span className="sr-only">Investigation date</span>
        <input
          type="range"
          min="0"
          max={lastIndex}
          step="1"
          value={selectedIndex}
          aria-label="Investigation date"
          aria-valuetext={date}
          data-ticks={JSON.stringify(dates)}
          disabled={loading || dates.length < 2}
          onChange={(event) => setPendingDate(dates[Number(event.target.value)] || result.as_of)}
        />
      </label>
      <div className="time-slider-ticks" aria-hidden="true">
        {dates.map((tick, index) => (
          <i key={tick} title={tick} style={{ left: `${lastIndex ? (index / lastIndex) * 100 : 0}%` }} />
        ))}
      </div>
      <div className="time-slider-range"><span>{dates[0] || result.as_of}</span><span>{dates.at(-1) || result.as_of}</span></div>
      <p className="time-slider-help">The case re-runs 400 ms after you choose a date with evidence.</p>
    </section>
  );
}

export default TimeSlider;
