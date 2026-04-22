import React, { useState, useRef, useEffect } from 'react';

/**
 * A searchable dropdown that filters options as you type.
 * Includes an "Other..." option to create new entries.
 *
 * Props:
 *   options: [{ id, name }]
 *   value: selected id (or '__other__' or '')
 *   onChange: (id) => void  — called with option id, '__other__', or ''
 *   customValue: string for the "Other" text input
 *   onCustomChange: (text) => void
 *   placeholder: string
 *   customPlaceholder: string
 */
export default function SearchableSelect({
  options, value, onChange, customValue, onCustomChange, placeholder, customPlaceholder,
}) {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const wrapperRef = useRef(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClick = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) setIsOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const selectedOption = options.find(o => String(o.id) === String(value));
  const displayValue = value === '__other__' ? 'Other...' : selectedOption?.name || '';

  const filtered = query
    ? options.filter(o => o.name.toLowerCase().includes(query.toLowerCase()))
    : options;

  const handleSelect = (id) => {
    onChange(id);
    setQuery('');
    setIsOpen(false);
  };

  const handleClear = () => {
    onChange('');
    setQuery('');
    onCustomChange('');
  };

  return (
    <div ref={wrapperRef} style={{ position: 'relative' }}>
      <div style={{ position: 'relative' }}>
        <input
          className="t-form-input"
          type="text"
          value={isOpen ? query : displayValue}
          placeholder={placeholder || '-- Select --'}
          onChange={(e) => { setQuery(e.target.value); if (!isOpen) setIsOpen(true); }}
          onFocus={() => { setIsOpen(true); setQuery(''); }}
        />
        {value && (
          <button type="button" onClick={handleClear}
            style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: 'var(--t-text-tertiary)', cursor: 'pointer', fontSize: '1rem', padding: '0 4px', minWidth: 'auto', lineHeight: 1 }}
          >&times;</button>
        )}
      </div>
      {isOpen && (
        <ul style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 10,
          background: 'var(--t-surface)', border: '1px solid var(--t-border)', borderRadius: 'var(--t-radius-sm)',
          boxShadow: 'var(--t-shadow-md)', maxHeight: 200, overflowY: 'auto', margin: '4px 0 0', padding: 0, listStyle: 'none',
        }}>
          {filtered.map(o => (
            <li key={o.id} onClick={() => handleSelect(o.id)}
              style={{
                padding: '6px 12px', cursor: 'pointer', fontSize: '0.85rem',
                background: String(o.id) === String(value) ? 'var(--t-primary-light)' : 'none',
                border: 'none', margin: 0,
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'var(--t-primary-light)'}
              onMouseLeave={(e) => e.currentTarget.style.background = String(o.id) === String(value) ? 'var(--t-primary-light)' : 'transparent'}
            >{o.name}</li>
          ))}
          {filtered.length === 0 && query && (
            <li style={{ padding: '6px 12px', fontSize: '0.85rem', color: 'var(--t-text-tertiary)', background: 'none', border: 'none', margin: 0 }}>No matches</li>
          )}
          <li onClick={() => handleSelect('__other__')}
            style={{
              padding: '6px 12px', cursor: 'pointer', fontSize: '0.85rem', fontStyle: 'italic',
              color: 'var(--t-primary)', borderTop: '1px solid var(--t-border-light)', background: 'none', border: 'none', borderTop: '1px solid var(--t-border-light)', margin: 0,
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = 'var(--t-primary-light)'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
          >Other... (create new)</li>
        </ul>
      )}
      {value === '__other__' && (
        <input className="t-form-input" type="text" value={customValue} onChange={(e) => onCustomChange(e.target.value)}
          placeholder={customPlaceholder} style={{ marginTop: 6 }} />
      )}
    </div>
  );
}
