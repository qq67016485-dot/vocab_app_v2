import React, { useState, useEffect, useRef } from 'react';
import apiClient from '../../api/axiosConfig.js';

const EDIT_POLL_INTERVAL = 10000;

/**
 * One graphic novel page card with inline image editing + variant selection.
 *
 * Editing never overwrites the original: the backend stores the edit as a
 * separate `edited_image` and exposes both URLs. The admin can flip between
 * the original and edited variant; whichever is selected is what students see.
 */
export default function GraphicNovelPageEditor({ page, audioUrl, audioStatus, audioError, onRegenAudio, onUpdated }) {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [zoomed, setZoomed] = useState(false);
  // Which variant the admin is previewing in this card (defaults to the active one).
  const [preview, setPreview] = useState(page.use_edited_image ? 'edited' : 'original');
  const pollRef = useRef(null);

  const status = page.generation_status || (page.image_url ? 'COMPLETED' : 'PENDING');
  const hasEdited = page.has_edited_image;
  const bust = (url) => (url ? `${url}${url.includes('?') ? '&' : '?'}t=${Date.now()}` : url);

  const previewUrl = preview === 'edited'
    ? (page.edited_image_url || page.image_url)
    : (page.original_image_url || page.image_url);

  // Close the zoom overlay with the Escape key while it's open.
  useEffect(() => {
    if (!zoomed) return;
    const onKey = (e) => { if (e.key === 'Escape') setZoomed(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [zoomed]);

  // Stop polling if the card unmounts mid-edit.
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const applyResult = (data) => {
    onUpdated({
      ...page,
      ...data,
      image_url: bust(data.image_url),
      edited_image_url: bust(data.edited_image_url),
    });
  };

  // Poll image-status/ until the background image op finishes, then apply the
  // result. Shared by the edit and redraw flows (both run async on the server).
  const pollUntilDone = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const poll = await apiClient.get(`/graphic-novel-pages/${page.id}/image-status/`);
        const data = poll.data;
        if (data.generation_status === 'COMPLETED') {
          clearInterval(pollRef.current);
          pollRef.current = null;
          applyResult(data);
          setPreview('edited');
          setBusy(false);
        } else if (data.generation_status === 'FAILED') {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setError(data.generation_error || 'Image generation failed. Try again.');
          setBusy(false);
        }
      } catch (err) {
        clearInterval(pollRef.current);
        pollRef.current = null;
        setError('Lost track of the image. Refresh to see the result.');
        setBusy(false);
      }
    }, EDIT_POLL_INTERVAL);
  };

  const submitEdit = async () => {
    const trimmed = prompt.trim();
    if (!trimmed) { setError('Enter a description of the edit.'); return; }
    setBusy(true);
    setError('');
    try {
      // The edit runs in a background worker; the POST returns immediately with
      // the page in RUNNING state, then we poll until it's COMPLETED or FAILED.
      await apiClient.post(`/graphic-novel-pages/${page.id}/edit-image/`, { prompt: trimmed });
      setPrompt('');
      setOpen(false);
      pollUntilDone();
    } catch (err) {
      setError(err.response?.data?.error || 'Image edit failed. Try again.');
      setBusy(false);
    }
  };

  const submitRedraw = async () => {
    setBusy(true);
    setError('');
    try {
      // Redraw replays the original generation payload (same prompt + reference)
      // on the server; like edit it runs in a background worker, so we poll.
      await apiClient.post(`/graphic-novel-pages/${page.id}/redraw-image/`);
      pollUntilDone();
    } catch (err) {
      setError(err.response?.data?.error || 'Image redraw failed. Try again.');
      setBusy(false);
    }
  };

  const selectVariant = async (variant) => {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const res = await apiClient.post(`/graphic-novel-pages/${page.id}/select-image/`, { variant });
      applyResult(res.data);
      setPreview(variant);
    } catch (err) {
      setError(err.response?.data?.error || 'Could not switch image.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ border: '1px solid var(--t-border)', borderRadius: 6, padding: 6 }}>
      {previewUrl ? (
        <img
          src={previewUrl}
          alt={`Page ${page.page_number}`}
          onClick={() => setZoomed(true)}
          title="Click to view full size"
          style={{ width: '100%', borderRadius: 4, marginBottom: 4, cursor: 'zoom-in', display: 'block' }}
        />
      ) : (
        <div className="t-hint" style={{ aspectRatio: '16 / 9', display: 'grid', placeItems: 'center', background: 'var(--t-surface-muted)', borderRadius: 4, marginBottom: 4 }}>Image pending</div>
      )}
      <div style={{ fontSize: '0.78rem' }}>Page {page.page_number} · {page.panel_count} panel{page.panel_count === 1 ? '' : 's'}</div>

      <AudioRow
        audioUrl={audioUrl}
        audioStatus={audioStatus}
        audioError={audioError}
        onRegenAudio={onRegenAudio}
      />
      <div
        style={{ fontSize: '0.75rem', color: status === 'FAILED' ? 'var(--t-danger)' : 'var(--t-text-secondary)' }}
        title={page.generation_error || ''}
      >
        {status}
        {page.generation_attempts ? ` · try ${page.generation_attempts}` : ''}
      </div>

      {hasEdited && (
        <VariantPicker
          page={page}
          preview={preview}
          setPreview={setPreview}
          selectVariant={selectVariant}
          busy={busy}
        />
      )}

      {page.image_url && !open && !busy && (
        <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
          <button
            className="t-btn t-btn--secondary"
            style={{ fontSize: '0.75rem', padding: '2px 8px' }}
            onClick={() => setOpen(true)}
          >
            Edit image
          </button>
          <button
            className="t-btn t-btn--secondary"
            style={{ fontSize: '0.75rem', padding: '2px 8px' }}
            onClick={submitRedraw}
            title="Re-run the original generation with the same prompt — a fresh attempt can clear up a bad image."
          >
            Redraw
          </button>
        </div>
      )}

      {!open && busy && (
        <div className="t-hint" style={{ fontSize: '0.72rem', marginTop: 6 }}>
          Working on the image — this can take up to a minute. You can leave this page; it keeps running.
        </div>
      )}

      {open && (
        <EditBox
          prompt={prompt}
          setPrompt={setPrompt}
          busy={busy}
          error={error}
          submitEdit={submitEdit}
          onCancel={() => { setOpen(false); setError(''); }}
        />
      )}
      {!open && error && <div style={{ fontSize: '0.72rem', color: 'var(--t-danger)', marginTop: 4 }}>{error}</div>}

      {zoomed && previewUrl && (
        <ImageLightbox
          src={previewUrl}
          alt={`Page ${page.page_number}`}
          onClose={() => setZoomed(false)}
        />
      )}
    </div>
  );
}

/**
 * Read-along audio for one page: the player (when audio exists) plus a per-page
 * (re)generate button. Regenerating a single page fills a gap left by a failed
 * TTS call without redoing the whole novel.
 */
function AudioRow({ audioUrl, audioStatus, audioError, onRegenAudio }) {
  const running = audioStatus === 'RUNNING';
  const failed = audioStatus === 'FAILED';
  const label = running
    ? '⏳ Generating…'
    : audioUrl
      ? '↺ Regen audio'
      : '🔊 Generate audio';
  return (
    <div style={{ marginTop: 4 }}>
      {audioUrl && (
        <audio controls src={audioUrl} style={{ width: '100%', height: 28 }} />
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
        {onRegenAudio && (
          <button
            className="t-btn t-btn--secondary"
            style={{ fontSize: '0.72rem', padding: '1px 8px' }}
            disabled={running}
            onClick={onRegenAudio}
            title={audioUrl ? 'Regenerate read-along audio for this page' : 'Generate read-along audio for this page'}
          >
            {label}
          </button>
        )}
        {failed && !running && (
          <span style={{ fontSize: '0.7rem', color: 'var(--t-danger)' }} title={audioError || ''}>
            Audio failed
          </span>
        )}
        {audioError && !failed && (
          <span style={{ fontSize: '0.7rem', color: 'var(--t-danger)' }}>{audioError}</span>
        )}
      </div>
    </div>
  );
}

/** Fullscreen overlay showing one page image at full size. Click anywhere or press Escape to close. */
function ImageLightbox({ src, alt, onClose }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 1100,
        background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24, cursor: 'zoom-out',
      }}
    >
      <img
        src={src}
        alt={alt}
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', borderRadius: 6, boxShadow: '0 8px 40px rgba(0,0,0,0.5)' }}
      />
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        style={{
          position: 'fixed', top: 16, right: 20, fontSize: '1.8rem', lineHeight: 1,
          color: '#fff', background: 'transparent', border: 'none', cursor: 'pointer',
        }}
      >
        ×
      </button>
    </div>
  );
}

/** Toggle which stored variant (original / edited) is shown to students. */
function VariantPicker({ page, preview, setPreview, selectVariant, busy }) {
  const active = page.use_edited_image ? 'edited' : 'original';
  const tabStyle = (key) => ({
    flex: 1,
    fontSize: '0.7rem',
    padding: '2px 6px',
    cursor: 'pointer',
    borderRadius: 4,
    border: `1px solid ${preview === key ? 'var(--t-primary)' : 'var(--t-border)'}`,
    background: preview === key ? 'var(--t-surface-muted)' : 'transparent',
    fontWeight: preview === key ? 600 : 400,
  });
  return (
    <div style={{ marginTop: 6 }}>
      <div style={{ display: 'flex', gap: 4, marginBottom: 4 }}>
        <button type="button" style={tabStyle('original')} onClick={() => setPreview('original')}>
          Original{active === 'original' ? ' ✓' : ''}
        </button>
        <button type="button" style={tabStyle('edited')} onClick={() => setPreview('edited')}>
          Edited{active === 'edited' ? ' ✓' : ''}
        </button>
      </div>
      {preview !== active ? (
        <button
          className="t-btn t-btn--primary"
          style={{ width: '100%', fontSize: '0.72rem', padding: '2px 8px' }}
          onClick={() => selectVariant(preview)}
          disabled={busy}
        >
          {busy ? 'Saving…' : `Use ${preview} for students`}
        </button>
      ) : (
        <div className="t-hint" style={{ fontSize: '0.7rem', textAlign: 'center' }}>
          Showing students the {active} image
        </div>
      )}
    </div>
  );
}

/** Prompt box for requesting an AI edit of the current image. */
function EditBox({ prompt, setPrompt, busy, error, submitEdit, onCancel }) {
  return (
    <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
      <textarea
        value={prompt}
        onChange={e => setPrompt(e.target.value)}
        disabled={busy}
        rows={3}
        placeholder="Describe the change, e.g. 'Make Hugo's hat blue and remove the dog in the background.'"
        style={{ width: '100%', fontSize: '0.75rem', padding: 4, borderRadius: 4, border: '1px solid var(--t-border)', resize: 'vertical', boxSizing: 'border-box' }}
      />
      {error && <div style={{ fontSize: '0.72rem', color: 'var(--t-danger)' }}>{error}</div>}
      <div style={{ display: 'flex', gap: 6 }}>
        <button className="t-btn t-btn--primary" style={{ fontSize: '0.75rem', padding: '2px 8px' }} onClick={submitEdit} disabled={busy}>
          {busy ? 'Editing…' : 'Apply edit'}
        </button>
        <button className="t-btn t-btn--secondary" style={{ fontSize: '0.75rem', padding: '2px 8px' }} onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
      {busy && <div className="t-hint" style={{ fontSize: '0.72rem' }}>Generating a new image — this can take up to a minute.</div>}
    </div>
  );
}
