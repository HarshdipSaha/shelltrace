import { useEffect, useState } from 'react';

const KEY = 'shelltrace-theme';
const choices = ['system', 'light', 'dark'];

export default function ThemeControl() {
  const [theme, setTheme] = useState(() => {
    try { return choices.includes(localStorage.getItem(KEY)) ? localStorage.getItem(KEY) : 'system'; }
    catch { return 'system'; }
  });

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const apply = () => {
      const resolved = theme === 'system' ? (media.matches ? 'dark' : 'light') : theme;
      document.documentElement.dataset.theme = resolved;
      document.documentElement.style.colorScheme = resolved;
      document.querySelector('meta[name="theme-color"]')?.setAttribute('content', resolved === 'dark' ? '#0d151e' : '#f3f6f8');
    };
    apply();
    try { localStorage.setItem(KEY, theme); } catch { /* Appearance still works without storage. */ }
    media.addEventListener('change', apply);
    return () => media.removeEventListener('change', apply);
  }, [theme]);

  return (
    <label className="theme-control">
      <svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M20.5 13.1A8.6 8.6 0 0 1 10.9 3.5 8.6 8.6 0 1 0 20.5 13.1Z" />
      </svg>
      <span className="sr-only">Appearance</span>
      <select aria-label="Appearance" value={theme} onChange={event => setTheme(event.target.value)}>
        <option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option>
      </select>
    </label>
  );
}
