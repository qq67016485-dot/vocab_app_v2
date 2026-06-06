import React, { useState, useEffect } from 'react';
import apiClient from '../../api/axiosConfig.js';

const PROVIDER_TYPES = [
  { value: 'gemini_native', label: 'Gemini (Native)' },
  { value: 'openai_compatible', label: 'OpenAI-Compatible' },
  { value: 'anthropic', label: 'Anthropic' },
];

export default function LLMConfig() {
  const [activeTab, setActiveTab] = useState('sites');
  const [sites, setSites] = useState([]);
  const [stepConfigs, setStepConfigs] = useState([]);
  const [configSets, setConfigSets] = useState([]);
  const [selectedSetId, setSelectedSetId] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Site form state
  const [editingSite, setEditingSite] = useState(null);
  const [siteForm, setSiteForm] = useState({ name: '', base_url: '', api_key_env_var: '', provider_type: 'gemini_native' });

  // Set rename state
  const [setNameDraft, setSetNameDraft] = useState('');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [sitesRes, setsRes] = await Promise.all([
        apiClient.get('/admin/llm-sites/'),
        apiClient.get('/admin/llm-config-sets/'),
      ]);
      setSites(sitesRes.data);
      setConfigSets(setsRes.data);
      // Default the editor to the active set (or the first one).
      const active = setsRes.data.find(s => s.is_active) || setsRes.data[0];
      const targetId = selectedSetId || (active && active.id);
      await loadStepConfigs(targetId);
    } catch (err) {
      setError('Failed to load LLM configuration.');
    } finally {
      setIsLoading(false);
    }
  };

  const loadStepConfigs = async (setId) => {
    const url = setId ? `/admin/llm-step-configs/?set=${setId}` : '/admin/llm-step-configs/';
    const res = await apiClient.get(url);
    setStepConfigs(res.data.configs);
    setSelectedSetId(res.data.set.id);
    setSetNameDraft(res.data.set.name);
  };

  const clearMessages = () => { setError(''); setSuccess(''); };

  // --- Config Sets ---
  const selectSet = async (setId) => {
    clearMessages();
    try {
      await loadStepConfigs(setId);
    } catch (err) {
      setError('Failed to load config set.');
    }
  };

  const activateSet = async () => {
    if (!selectedSetId) return;
    clearMessages();
    try {
      const res = await apiClient.put(`/admin/llm-config-sets/${selectedSetId}/`, { is_active: true });
      setConfigSets(prev => prev.map(s => ({ ...s, is_active: s.id === res.data.id })));
      setSuccess(`"${res.data.name}" is now the active set.`);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to activate set.');
    }
  };

  const saveSetName = async () => {
    if (!selectedSetId) return;
    const name = setNameDraft.trim();
    if (!name) { setError('Set name cannot be blank.'); return; }
    clearMessages();
    try {
      const res = await apiClient.put(`/admin/llm-config-sets/${selectedSetId}/`, { name });
      setConfigSets(prev => prev.map(s => (s.id === res.data.id ? { ...s, name: res.data.name } : s)));
      setSuccess('Set name updated.');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to rename set.');
    }
  };

  // --- Site CRUD ---
  const startAddSite = () => {
    setEditingSite('new');
    setSiteForm({ name: '', base_url: '', api_key_env_var: '', provider_type: 'gemini_native' });
    clearMessages();
  };

  const startEditSite = (site) => {
    setEditingSite(site.id);
    setSiteForm({ name: site.name, base_url: site.base_url, api_key_env_var: site.api_key_env_var, provider_type: site.provider_type });
    clearMessages();
  };

  const cancelEditSite = () => { setEditingSite(null); clearMessages(); };

  const saveSite = async () => {
    clearMessages();
    try {
      if (editingSite === 'new') {
        await apiClient.post('/admin/llm-sites/', siteForm);
        setSuccess('Site created.');
      } else {
        await apiClient.put(`/admin/llm-sites/${editingSite}/`, siteForm);
        setSuccess('Site updated.');
      }
      setEditingSite(null);
      await loadData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save site.');
    }
  };

  const deleteSite = async (id) => {
    if (!confirm('Delete this site?')) return;
    clearMessages();
    try {
      await apiClient.delete(`/admin/llm-sites/${id}/`);
      setSuccess('Site deleted.');
      await loadData();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to delete site.');
    }
  };

  // --- Step Config ---
  const updateStepConfig = (stepKey, field, value) => {
    setStepConfigs(prev => prev.map(cfg =>
      cfg.step_key === stepKey ? { ...cfg, [field]: value } : cfg
    ));
  };

  const saveStepConfigs = async () => {
    clearMessages();
    const payload = stepConfigs.map(cfg => ({
      step_key: cfg.step_key,
      primary_site: cfg.primary_site,
      primary_model: cfg.primary_model,
      fallback_site: cfg.fallback_site,
      fallback_model: cfg.fallback_model,
    }));
    try {
      const url = selectedSetId ? `/admin/llm-step-configs/?set=${selectedSetId}` : '/admin/llm-step-configs/';
      const res = await apiClient.put(url, payload);
      setStepConfigs(res.data.configs);
      setSuccess(`Step configurations saved to "${res.data.set.name}".`);
    } catch (err) {
      const errors = err.response?.data?.errors;
      setError(errors ? errors.join('; ') : 'Failed to save step configs.');
    }
  };

  if (isLoading) return <p>Loading LLM configuration...</p>;

  return (
    <div>
      <div className="t-page-header">
        <h1 className="t-page-title">LLM Configuration</h1>
      </div>

      {error && <div className="t-alert t-alert--error">{error}</div>}
      {success && <div className="t-alert t-alert--success">{success}</div>}

      <div className="t-tabs" style={{ marginBottom: '1.5rem' }}>
        <button className={`t-tab ${activeTab === 'sites' ? 't-tab--active' : ''}`} onClick={() => setActiveTab('sites')}>
          API Sites
        </button>
        <button className={`t-tab ${activeTab === 'steps' ? 't-tab--active' : ''}`} onClick={() => setActiveTab('steps')}>
          Step Configuration
        </button>
      </div>

      {activeTab === 'sites' && (
        <div className="t-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ margin: 0 }}>API Sites</h2>
            <button className="t-btn t-btn--primary" onClick={startAddSite}>Add Site</button>
          </div>
          <table className="t-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Base URL</th>
                <th>API Key Env Var</th>
                <th>Provider</th>
                <th>Key Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {editingSite === 'new' && (
                <tr>
                  <td><input className="t-form-input" value={siteForm.name} onChange={e => setSiteForm({...siteForm, name: e.target.value})} placeholder="Site name" /></td>
                  <td><input className="t-form-input" value={siteForm.base_url} onChange={e => setSiteForm({...siteForm, base_url: e.target.value})} placeholder="https://..." /></td>
                  <td><input className="t-form-input" value={siteForm.api_key_env_var} onChange={e => setSiteForm({...siteForm, api_key_env_var: e.target.value})} placeholder="GEMINI_API_KEY" /></td>
                  <td>
                    <select className="t-form-select" value={siteForm.provider_type} onChange={e => setSiteForm({...siteForm, provider_type: e.target.value})}>
                      {PROVIDER_TYPES.map(pt => <option key={pt.value} value={pt.value}>{pt.label}</option>)}
                    </select>
                  </td>
                  <td></td>
                  <td>
                    <button className="t-btn t-btn--small t-btn--primary" onClick={saveSite}>Save</button>
                    <button className="t-btn t-btn--small t-btn--secondary" onClick={cancelEditSite} style={{ marginLeft: '0.5rem' }}>Cancel</button>
                  </td>
                </tr>
              )}
              {sites.map(site => (
                <tr key={site.id}>
                  {editingSite === site.id ? (
                    <>
                      <td><input className="t-form-input" value={siteForm.name} onChange={e => setSiteForm({...siteForm, name: e.target.value})} /></td>
                      <td><input className="t-form-input" value={siteForm.base_url} onChange={e => setSiteForm({...siteForm, base_url: e.target.value})} /></td>
                      <td><input className="t-form-input" value={siteForm.api_key_env_var} onChange={e => setSiteForm({...siteForm, api_key_env_var: e.target.value})} /></td>
                      <td>
                        <select className="t-form-select" value={siteForm.provider_type} onChange={e => setSiteForm({...siteForm, provider_type: e.target.value})}>
                          {PROVIDER_TYPES.map(pt => <option key={pt.value} value={pt.value}>{pt.label}</option>)}
                        </select>
                      </td>
                      <td></td>
                      <td>
                        <button className="t-btn t-btn--small t-btn--primary" onClick={saveSite}>Save</button>
                        <button className="t-btn t-btn--small t-btn--secondary" onClick={cancelEditSite} style={{ marginLeft: '0.5rem' }}>Cancel</button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td style={{ fontWeight: 600 }}>{site.name}</td>
                      <td><code style={{ fontSize: '0.85em' }}>{site.base_url || '(native SDK)'}</code></td>
                      <td><code>{site.api_key_env_var}</code></td>
                      <td>{PROVIDER_TYPES.find(pt => pt.value === site.provider_type)?.label}</td>
                      <td>{site.has_api_key ? <span style={{ color: 'green' }}>Set</span> : <span style={{ color: 'red' }}>Missing</span>}</td>
                      <td>
                        <button className="t-btn t-btn--small t-btn--secondary" onClick={() => startEditSite(site)}>Edit</button>
                        <button className="t-btn t-btn--small t-btn--danger" onClick={() => deleteSite(site.id)} style={{ marginLeft: '0.5rem' }}>Delete</button>
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'steps' && (
        <div className="t-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ margin: 0 }}>Step Configuration</h2>
            <button className="t-btn t-btn--primary" onClick={saveStepConfigs}>Save All</button>
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.5rem', alignItems: 'flex-end', marginBottom: '1.25rem', paddingBottom: '1rem', borderBottom: '1px solid var(--t-border, #e2e2e2)' }}>
            <div>
              <label className="t-form-label" style={{ display: 'block', marginBottom: '0.25rem' }}>Editing set</label>
              <select className="t-form-select" value={selectedSetId || ''} onChange={e => selectSet(Number(e.target.value))}>
                {configSets.map(s => (
                  <option key={s.id} value={s.id}>{s.name}{s.is_active ? ' — active' : ''}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="t-form-label" style={{ display: 'block', marginBottom: '0.25rem' }}>Set name</label>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <input className="t-form-input" value={setNameDraft} onChange={e => setSetNameDraft(e.target.value)} />
                <button className="t-btn t-btn--small t-btn--secondary" onClick={saveSetName}>Rename</button>
              </div>
            </div>
            <div>
              {configSets.find(s => s.id === selectedSetId)?.is_active ? (
                <span style={{ color: 'green', fontWeight: 600 }}>This set is active</span>
              ) : (
                <button className="t-btn t-btn--secondary" onClick={activateSet}>Make this set active</button>
              )}
            </div>
          </div>

          <p style={{ marginTop: 0, color: 'var(--t-text-muted, #666)', fontSize: '0.9em' }}>
            The pipeline uses the <strong>active</strong> set. Editing a non-active set is safe — changes apply only when you activate it. API Sites are shared across all sets.
          </p>

          <table className="t-table">
            <thead>
              <tr>
                <th>Step</th>
                <th>Primary Site</th>
                <th>Primary Model</th>
                <th>Fallback Site</th>
                <th>Fallback Model</th>
              </tr>
            </thead>
            <tbody>
              {stepConfigs.map(cfg => (
                <tr key={cfg.step_key}>
                  <td style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>{cfg.step_display}</td>
                  <td>
                    <select className="t-form-select" value={cfg.primary_site} onChange={e => updateStepConfig(cfg.step_key, 'primary_site', Number(e.target.value))}>
                      {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  </td>
                  <td>
                    <input className="t-form-input" value={cfg.primary_model} onChange={e => updateStepConfig(cfg.step_key, 'primary_model', e.target.value)} />
                  </td>
                  <td>
                    <select className="t-form-select" value={cfg.fallback_site} onChange={e => updateStepConfig(cfg.step_key, 'fallback_site', Number(e.target.value))}>
                      {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  </td>
                  <td>
                    <input className="t-form-input" value={cfg.fallback_model} onChange={e => updateStepConfig(cfg.step_key, 'fallback_model', e.target.value)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
