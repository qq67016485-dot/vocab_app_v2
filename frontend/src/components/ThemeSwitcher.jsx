import React, { useRef } from 'react';

const THEMES = [
  { id: 'sky-lavender',   label: 'Sky & Lavender' },
  { id: 'mint-meadow',    label: 'Mint Meadow' },
  { id: 'sunny-peach',    label: 'Sunny Peach' },
  { id: 'grape-soda',     label: 'Grape Soda' },
  { id: 'seafoam-breeze', label: 'Seafoam Breeze' },
];

export default function ThemeSwitcher({ value, onChange, compact = false, asButton = false }) {
  const ref = useRef(null);
  const handleChange = (e) => onChange?.(e.target.value);

  if (asButton) {
    return (
      <div className={`theme-button-wrap${compact ? ' compact' : ''}`}>
        <button
          type="button"
          className="theme-trigger"
          onClick={() => { try { ref.current?.showPicker?.(); } catch {} ref.current?.focus(); }}
          aria-label="Change color theme"
        >
          change color
        </button>
        <select
          ref={ref}
          className="theme-select-native"
          value={value}
          onChange={handleChange}
          aria-label="Theme"
        >
          {THEMES.map(t => (
            <option key={t.id} value={t.id}>{t.label}</option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div className={`theme-switcher${compact ? ' compact' : ''}`}>
      <label htmlFor="student-theme" className="sr-only">Theme</label>
      <select
        id="student-theme"
        className="theme-select"
        value={value}
        onChange={handleChange}
      >
        {THEMES.map(t => (
          <option key={t.id} value={t.id}>{t.label}</option>
        ))}
      </select>
    </div>
  );
}
