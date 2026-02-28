import React, { createContext, useState, useContext, useEffect } from 'react';

const ThemeContext = createContext();

export const useTheme = () => useContext(ThemeContext);

const THEMES = [
  { id: 'sky-lavender',   label: 'Sky & Lavender' },
  { id: 'mint-meadow',    label: 'Mint Meadow' },
  { id: 'sunny-peach',    label: 'Sunny Peach' },
  { id: 'grape-soda',     label: 'Grape Soda' },
  { id: 'seafoam-breeze', label: 'Seafoam Breeze' },
];

export const ThemeProvider = ({ children }) => {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('studentTheme') || 'sky-lavender';
  });

  useEffect(() => {
    localStorage.setItem('studentTheme', theme);
  }, [theme]);

  const value = { theme, setTheme, THEMES };

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
};
