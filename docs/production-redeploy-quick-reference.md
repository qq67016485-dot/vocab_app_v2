# Production Redeploy — Quick Reference

Full redeploy (backend + frontend) built entirely on the Ubuntu production server.

- **Server:** `http://106.52.164.47` (Tencent Cloud, Ubuntu 24.04, 2 vCPU / 3.6 GB)
- **Stack:** nginx → serves `frontend/dist/`, proxies `/api` + `/admin` to gunicorn; systemd unit `vocab.service`; MySQL 8

---

## Full redeploy (all on the Ubuntu server)

```bash
# 1. SSH in
ssh ubuntu@106.52.164.47
cd ~/vocab_app_v2

# 2. Pull latest code (or scp from Windows if git pull hangs)
git pull origin master

# --- BACKEND ---
cd ~/vocab_app_v2/backend
source venv/bin/activate
pip install -r requirements.txt              # if requirements.txt changed
python manage.py migrate                     # if migrations changed
python manage.py collectstatic --noinput     # if Django static/admin changed

# --- FRONTEND (build on the server) ---
cd ~/vocab_app_v2/frontend
npm ci                                        # if package-lock.json changed (else: npm install)
npm run build                                 # outputs to frontend/dist/ — nginx serves this directly

# --- RESTART & VERIFY ---
sudo systemctl restart vocab                  # backend only; nginx picks up new dist/ with no restart
sudo systemctl status vocab --no-pager
```

---

## Run only what changed

| If you changed…                | You must run…                                  |
| ------------------------------ | ---------------------------------------------- |
| Backend `.py` only             | restart `vocab`                                |
| Models / migrations            | `migrate` → restart                            |
| Django static assets / admin   | `collectstatic --noinput` → restart            |
| `requirements.txt`             | `pip install -r requirements.txt` → restart    |
| Frontend (`frontend/src`, deps)| `npm ci` / `npm install` → `npm run build`     |

---

## Notes for building the frontend on the Ubuntu box

- **Node is installed via NodeSource apt** (nvm is blocked on this server). Confirm before building:
  ```bash
  node -v && npm -v
  ```
- **`npm ci` vs `npm install`**: prefer `npm ci` for a clean, lockfile-exact install. Use plain `npm install` only if you intentionally changed deps without updating the lockfile.
- **Memory**: the box is small (3.6 GB RAM). A Vite build can spike memory; if `npm run build` gets OOM-killed, cap Node's heap:
  ```bash
  NODE_OPTIONS=--max-old-space-size=2048 npm run build
  ```
- **No restart needed for frontend** — nginx serves `frontend/dist/` straight from disk, so a fresh build is live immediately. Hard-refresh the browser to bust cached assets.
- **Build output path**: Vite writes to `frontend/dist/`, exactly what the nginx root expects — no copy/move step required when building in place.

---

## If `git pull` hangs (known issue)

GitHub `git pull`/`clone` is unreliable on this server (HTTP/2 connection drops). Abort (Ctrl-C) and `scp` only the changed subdirectories from Windows (`C:\project\vocab_app_v2`):

```powershell
scp -r backend\vocabulary ubuntu@106.52.164.47:~/vocab_app_v2/backend/
```

> ⚠️ Never `scp -r backend\` wholesale — that overwrites the server's `.env`, `media/`, and `venv/`. Copy only changed subdirectories (e.g. `vocabulary`, `config`, `users`).

---

## Verify

```bash
sudo systemctl status vocab --no-pager        # should be active (running)
sudo journalctl -u vocab -n 50 --no-pager     # check for startup errors
curl -I http://106.52.164.47                  # smoke-test the live site
```

Then load `http://106.52.164.47` in a browser, log in, and exercise the specific feature you changed.

---

## Rollback (if verification fails)

```bash
cd ~/vocab_app_v2/backend
git log --oneline -5                          # find the previous good commit
git reset --hard <prev_sha>                   # or git revert <bad_sha> for a safer audit trail
python manage.py migrate <app> <prev_migration>   # if a migration must be rolled back
sudo systemctl restart vocab
# Frontend: rebuild from the rolled-back source, or restore a backed-up dist/
```

---

## Server-specific gotchas

- The gunicorn socket **must** live at `/run/vocab/vocab.sock` (not `/run/vocab.sock`).
- gunicorn **must run threaded workers** — `--worker-class gthread --threads 8` in the unit's ExecStart (`sudo systemctl edit --full vocab`, then restart). The sentence-write judge holds a worker for a synchronous 2–10s LLM call; with the default sync workers, 3 concurrent judged submits stall every request on the box.
- nginx needs `chmod o+x /home/ubuntu` to traverse the home dir.
- The box has **no ffmpeg** — audiobook encoding relies on `lameenc`; don't introduce ffmpeg/pydub deps.
- Never delete `backend/media/` — generated images and audio are persistent there.
