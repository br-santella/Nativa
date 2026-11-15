import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import english from './translations.en.json';
type Language = 'en' | 'pt';
const translations: Record<string,string> = english;
let active: Language = 'en';
try { if (localStorage.getItem('nativa-language') === 'pt') active = 'pt'; } catch { /* Storage is optional. */ }
export function locale() { return active === 'en' ? 'en-US' : 'pt-BR'; }
export function t<T>(value: T): T {
  if (Array.isArray(value)) return value.map(item => t(item)) as T;
  if (active !== 'en' || typeof value !== 'string') return value;
  const key = value.replace(/\s+/g, ' ').trim();
  const translated = translations[key];
  if (translated === undefined) return value;
  const leading = value.match(/^\s*/)?.[0] || '';
  const trailing = value.match(/\s*$/)?.[0] || '';
  return (leading + translated + trailing) as T;
}
const Context = createContext<{language: Language; setLanguage: (language: Language) => void}>({language: active, setLanguage: () => {}});
export function LanguageProvider({children}: {children: ReactNode}) {
  const [language, update] = useState<Language>(active);
  const setLanguage = (next: Language) => { active = next; update(next); try {localStorage.setItem('nativa-language', next);} catch { /* Keep in memory. */ } };
  useEffect(() => {
    document.documentElement.lang = language === 'en' ? 'en' : 'pt-BR';
    document.title = language === 'en' ? 'NATIVA — A fresh perspective on your farm' : 'NATIVA — Uma nova perspectiva para sua lavoura';
    document.querySelector('meta[name="description"]')?.setAttribute('content',language === 'en' ? 'NATIVA: explore your property and compare agricultural scenarios from a new perspective.' : 'NATIVA: explore sua propriedade e compare cenários agrícolas com uma nova perspectiva.');
  }, [language]);
  return <Context.Provider value={{language, setLanguage}}>{children}</Context.Provider>;
}
export const useLanguage = () => useContext(Context);
export function LanguageSwitcher() {
  const {language, setLanguage} = useLanguage();
  return <label className="language-switcher"><svg className="language-globe" aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18M5 7.5h14M5 16.5h14"/></svg><select aria-label={language === 'en' ? 'Language' : 'Idioma'} value={language} onChange={e => setLanguage(e.target.value as Language)}><option value="en" lang="en">EN</option><option value="pt" lang="pt-BR">PT</option></select></label>;
}
