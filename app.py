#!/usr/bin/env python3
"""
PyFile Tools - a single-file Python file analyzer.

Everything lives in this one file: the backend, the HTML, the CSS and the
JavaScript. There is no templates/ folder, no static/ folder and no
third-party dependency - it runs on the Python standard library alone.

Run it locally:

    python app.py
    # then open http://localhost:5000

Host it anywhere that can run Python (Render, Railway, a VPS, ...).
The server binds to 0.0.0.0 and reads the PORT environment variable, so it
works as-is on hosts like Render that assign a port at runtime.
"""

import ast
import io
import json
import os
import re
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

MAX_BYTES = 5 * 1024 * 1024          # 5 MB upload cap
ALLOWED = {".py", ".txt"}

PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>PyFile Tools — Python File Analyzer</title>
  <meta name="description" content="Analyze and download Python files safely. Inspect line counts, character counts and Python syntax without ever executing your code.">
  <meta name="color-scheme" content="light dark">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
/* ==========================================================================
   PyFile Tools — stylesheet
   Light-first, with a full dark theme via prefers-color-scheme.
   Palette is Python-inspired: steel blue + a single amber highlight.
   ========================================================================== */

:root {
  --bg: #f6f8fc;
  --bg-soft: #eef2f9;
  --surface: #ffffff;
  --surface-2: #f4f7fc;
  --recessed: #eef2f8;
  --border: rgba(15, 28, 48, 0.12);
  --border-strong: rgba(15, 28, 48, 0.22);

  --text: #0f1c30;
  --text-dim: #55657e;
  --text-faint: #8593a8;

  --blue: #2b6cb0;
  --blue-deep: #1d4e86;
  --blue-soft: rgba(43, 108, 176, 0.10);
  --amber: #c98a12;
  --amber-soft: rgba(201, 138, 18, 0.14);

  --good: #157347;
  --good-soft: rgba(21, 115, 71, 0.12);
  --bad: #b4232a;
  --bad-soft: rgba(180, 35, 42, 0.10);
  --neutral: #55657e;
  --neutral-soft: rgba(85, 101, 126, 0.12);

  --font-display: "Space Grotesk", "Segoe UI", system-ui, sans-serif;
  --font-body: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;

  --radius: 16px;
  --radius-sm: 11px;
  --shadow: 0 20px 45px -28px rgba(15, 28, 48, 0.35);
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0b1220;
    --bg-soft: #0e1728;
    --surface: #111c31;
    --surface-2: #16233c;
    --recessed: #0c1526;
    --border: rgba(255, 255, 255, 0.10);
    --border-strong: rgba(255, 255, 255, 0.20);

    --text: #e8eef9;
    --text-dim: #93a6c2;
    --text-faint: #64758f;

    --blue: #63a4e0;
    --blue-deep: #8cc2f2;
    --blue-soft: rgba(99, 164, 224, 0.14);
    --amber: #f0b429;
    --amber-soft: rgba(240, 180, 41, 0.16);

    --good: #4ade9a;
    --good-soft: rgba(74, 222, 154, 0.14);
    --bad: #ff8f97;
    --bad-soft: rgba(255, 143, 151, 0.12);
    --neutral: #93a6c2;
    --neutral-soft: rgba(147, 166, 194, 0.14);

    --shadow: 0 24px 60px -30px rgba(0, 0, 0, 0.75);
  }
}

* { box-sizing: border-box; }

html { scroll-behavior: smooth; }

body {
  margin: 0;
  min-height: 100vh;
  font-family: var(--font-body);
  font-size: 16px;
  line-height: 1.6;
  color: var(--text);
  background: linear-gradient(180deg, var(--bg) 0%, var(--bg-soft) 100%);
  background-attachment: fixed;
  -webkit-font-smoothing: antialiased;
}

/* Faint technical grid, faded toward the top */
.grid {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  background-image:
    linear-gradient(var(--border) 1px, transparent 1px),
    linear-gradient(90deg, var(--border) 1px, transparent 1px);
  background-size: 52px 52px;
  opacity: 0.5;
  -webkit-mask-image: radial-gradient(ellipse 75% 55% at 50% 0%, #000 15%, transparent 78%);
  mask-image: radial-gradient(ellipse 75% 55% at 50% 0%, #000 15%, transparent 78%);
}

.shell {
  position: relative;
  z-index: 1;
  width: min(940px, 92%);
  margin: 0 auto;
  padding-bottom: 8px;
}

/* ------------------------------------------------------------------ Nav */
.nav {
  height: 88px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  border-bottom: 1px solid var(--border);
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  color: inherit;
  text-decoration: none;
}

.brand-mark {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  background: var(--blue-deep);
  color: #fff;
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 17px;
  letter-spacing: -0.02em;
  border-bottom: 3px solid var(--amber);
}

.brand-text { display: flex; flex-direction: column; line-height: 1.25; }
.brand-text strong { font-family: var(--font-display); font-weight: 600; letter-spacing: -0.01em; }
.brand-text small {
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-dim);
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 999px;
  padding: 7px 13px;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--good);
  box-shadow: 0 0 0 4px var(--good-soft);
}

/* ----------------------------------------------------------------- Hero */
.hero { padding: 66px 4px 34px; }

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  margin: 0;
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 500;
  letter-spacing: 0.18em;
  color: var(--text-dim);
}

.tick { width: 18px; height: 2px; background: var(--amber); border-radius: 2px; }

.hero h1 {
  font-family: var(--font-display);
  font-weight: 700;
  letter-spacing: -0.035em;
  font-size: clamp(2.1rem, 5.4vw, 3.5rem);
  line-height: 1.05;
  margin: 18px 0 0;
}

.hero h1 em {
  font-style: normal;
  color: var(--blue);
  text-decoration: underline;
  text-decoration-color: var(--amber);
  text-decoration-thickness: 3px;
  text-underline-offset: 6px;
}

.lede {
  max-width: 60ch;
  margin: 20px 0 0;
  color: var(--text-dim);
  font-size: clamp(1rem, 1.6vw, 1.1rem);
}

.lede code {
  font-family: var(--font-mono);
  font-size: 0.85em;
  background: var(--recessed);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 1px 6px;
  color: var(--blue);
}

/* -------------------------------------------------------------- Panel */
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  box-shadow: var(--shadow);
}

/* ------------------------------------------------------------ Dropzone */
.dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 250px;
  padding: 28px;
  text-align: center;
  border: 1.5px dashed var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  cursor: pointer;
  transition: border-color .18s ease, background .18s ease, transform .18s ease;
}

.dropzone:hover,
.dropzone.drag {
  border-color: var(--blue);
  background: var(--blue-soft);
}

.dropzone.drag { transform: scale(0.995); }

.upload-icon {
  width: 56px;
  height: 56px;
  display: grid;
  place-items: center;
  border-radius: 15px;
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--blue);
  margin-bottom: 10px;
}

.upload-icon svg { width: 26px; height: 26px; }

.drop-title {
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 1.15rem;
  letter-spacing: -0.01em;
}

.drop-text { color: var(--text-faint); font-size: 13px; }
.drop-text b { color: var(--blue); font-weight: 600; }

/* ----------------------------------------------------------- File info */
.file-info {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-top: 14px;
  padding: 13px 15px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.file-info .tag {
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--good);
  background: var(--good-soft);
  border-radius: 999px;
  padding: 3px 9px;
}

.file-info b {
  font-size: 13.5px;
  word-break: break-all;
}

.file-info small { margin-left: auto; color: var(--text-faint); font-family: var(--font-mono); font-size: 12px; }

/* ------------------------------------------------------------- Buttons */
.primary {
  width: 100%;
  margin-top: 16px;
  padding: 15px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 0;
  border-radius: var(--radius-sm);
  background: var(--blue-deep);
  color: #fff;
  font-family: var(--font-body);
  font-weight: 600;
  font-size: 15px;
  cursor: pointer;
  transition: transform .15s ease, background .15s ease;
}

.primary:hover:not(:disabled) { transform: translateY(-1px); background: var(--blue); }
.primary:disabled { opacity: 0.65; cursor: progress; }
.primary .arrow { font-size: 17px; }

/* -------------------------------------------------------------- Result */
.result {
  margin-top: 16px;
  padding: 18px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}

.result-head > span {
  font-family: var(--font-mono);
  font-size: 11.5px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.pill {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 500;
  border-radius: 999px;
  padding: 5px 12px;
  white-space: nowrap;
}

.pill.good { color: var(--good); background: var(--good-soft); }
.pill.bad { color: var(--bad); background: var(--bad-soft); }
.pill.neutral { color: var(--neutral); background: var(--neutral-soft); }

.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin: 16px 0;
}

.stats > div {
  padding: 13px 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
}

.stats small {
  display: block;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-faint);
  margin-bottom: 6px;
}

.stats b { font-size: 14px; word-break: break-word; }

.syntax {
  display: flex;
  gap: 10px;
  align-items: baseline;
  padding: 11px 13px;
  border-radius: 10px;
  background: var(--bad-soft);
  color: var(--bad);
  font-size: 13px;
}

.syntax span {
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.85;
}

.actions { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; }

.actions button {
  flex: 1 1 160px;
  padding: 12px 16px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: var(--blue-deep);
  color: #fff;
  font-family: var(--font-body);
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  transition: transform .15s ease, background .15s ease;
}

.actions button:hover { transform: translateY(-1px); }
.actions .secondary {
  background: transparent;
  border-color: var(--border-strong);
  color: var(--text);
}
.actions .secondary:hover { border-color: var(--blue); color: var(--blue); }

/* --------------------------------------------------------------- Error */
.error {
  margin-top: 14px;
  padding: 13px 15px;
  border-radius: var(--radius-sm);
  background: var(--bad-soft);
  border: 1px solid transparent;
  color: var(--bad);
  font-size: 13.5px;
}

/* ------------------------------------------------------------ Features */
.features {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin: 30px 0 8px;
}

.features article {
  padding: 20px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.features .idx {
  display: block;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.1em;
  color: var(--amber);
  margin-bottom: 14px;
}

.features h3 {
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 1.02rem;
  margin: 0 0 6px;
  letter-spacing: -0.01em;
}

.features p { margin: 0; color: var(--text-dim); font-size: 13.5px; }

/* -------------------------------------------------------------- Footer */
footer {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  padding: 30px 4px 44px;
  margin-top: 18px;
  border-top: 1px solid var(--border);
  color: var(--text-faint);
  font-family: var(--font-mono);
  font-size: 11.5px;
}

/* ------------------------------------------------------------ Responsive */
@media (max-width: 680px) {
  .nav { height: 74px; }
  .brand-mark { width: 38px; height: 38px; }
  .hero { padding-top: 46px; }
  .panel { padding: 14px; }
  .dropzone { min-height: 210px; }
  .stats { grid-template-columns: 1fr 1fr; }
  .features { grid-template-columns: 1fr; }
  .status { font-size: 10.5px; padding: 6px 10px; }
}

@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  * { transition: none !important; }
}
  </style>
</head>
<body>
  <div class="grid" aria-hidden="true"></div>

  <main class="shell">
    <nav class="nav">
      <a class="brand" href="/">
        <span class="brand-mark" aria-hidden="true">Py</span>
        <span class="brand-text">
          <strong>PyFile Tools</strong>
          <small>Python File Analyzer</small>
        </span>
      </a>
      <div class="status"><span class="dot"></span> Service online</div>
    </nav>

    <header class="hero">
      <p class="eyebrow"><span class="tick"></span> FAST &nbsp;·&nbsp; PRIVATE &nbsp;·&nbsp; SAFE</p>
      <h1>Analyze your <em>Python files</em><br>in seconds.</h1>
      <p class="lede">
        Drop in a <code>.py</code> or <code>.txt</code> file to inspect its size, line and character
        counts and Python syntax — without a single line of your code being executed.
      </p>
    </header>

    <section class="panel">
      <form id="form" novalidate>
        <label class="dropzone" id="dropzone" for="file">
          <input id="file" name="file" type="file" accept=".py,.txt" hidden>
          <span class="upload-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 16V4"/><path d="M7 9l5-5 5 5"/><path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>
            </svg>
          </span>
          <span class="drop-title" id="dropTitle">Drop your file here</span>
          <span class="drop-text" id="dropText">or <b>browse files</b> · max 5&nbsp;MB · .py &amp; .txt only</span>
        </label>

        <div id="fileInfo" class="file-info" hidden></div>

        <button class="primary" id="analyzeBtn" type="submit">
          <span class="label">Analyze file</span>
          <span class="arrow" aria-hidden="true">→</span>
        </button>
      </form>

      <div id="result" class="result" role="status" aria-live="polite" hidden></div>
      <div id="error" class="error" role="alert" hidden></div>
    </section>

    <section class="features">
      <article>
        <span class="idx">01</span>
        <h3>Never executed</h3>
        <p>Your Python is parsed and measured only — it is never run on the server.</p>
      </article>
      <article>
        <span class="idx">02</span>
        <h3>Instant feedback</h3>
        <p>Line counts, character counts and syntax validity in a single round-trip.</p>
      </article>
      <article>
        <span class="idx">03</span>
        <h3>Take it with you</h3>
        <p>Download the original file back, or grab it bundled as a ZIP archive.</p>
      </article>
    </section>

    <footer>
      <span>PyFile Tools</span>
      <span>Built for simple, safe file inspection</span>
    </footer>
  </main>

<script>
  const fileInput = document.querySelector("#file");
  const drop = document.querySelector("#dropzone");
  const form = document.querySelector("#form");
  const info = document.querySelector("#fileInfo");
  const result = document.querySelector("#result");
  const errorBox = document.querySelector("#error");
  const title = document.querySelector("#dropTitle");
  const text = document.querySelector("#dropText");
  const analyzeBtn = document.querySelector("#analyzeBtn");

  const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[c]
  ));

  const kb = (bytes) => (bytes / 1024).toFixed(1);

  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.hidden = false;
  }
  function clearError() { errorBox.hidden = true; errorBox.textContent = ""; }

  function setFile(file) {
    if (!file) return;
    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;

    info.innerHTML =
      '<span class="tag">Selected</span>' +
      '<b>' + escapeHtml(file.name) + '</b>' +
      '<small>' + kb(file.size) + ' KB</small>';
    info.hidden = false;
    title.textContent = file.name;
    text.textContent = "Ready to analyze";
    clearError();
    result.hidden = true;
  }

  fileInput.addEventListener("change", () => setFile(fileInput.files[0]));

  ["dragenter", "dragover"].forEach((e) => drop.addEventListener(e, (ev) => {
    ev.preventDefault(); drop.classList.add("drag");
  }));
  ["dragleave", "drop"].forEach((e) => drop.addEventListener(e, (ev) => {
    ev.preventDefault(); drop.classList.remove("drag");
  }));
  drop.addEventListener("drop", (ev) => setFile(ev.dataTransfer.files[0]));

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    clearError();
    result.hidden = true;

    if (!fileInput.files[0]) return showError("Please select a file first.");

    analyzeBtn.disabled = true;
    analyzeBtn.querySelector(".label").textContent = "Analyzing…";

    const fd = new FormData();
    fd.append("file", fileInput.files[0]);

    try {
      const r = await fetch("/analyze", { method: "POST", body: fd });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "Something went wrong.");

      const x = data.result;
      const validClass = x.python_valid === null ? "neutral"
                       : x.python_valid ? "good" : "bad";
      const validLabel = x.python_valid === null ? "Not applicable"
                       : x.python_valid ? "Valid Python" : "Syntax error";

      result.innerHTML =
        '<div class="result-head">' +
          '<span>Analysis complete</span>' +
          '<strong class="pill ' + validClass + '">' + validLabel + '</strong>' +
        '</div>' +
        '<div class="stats">' +
          '<div><small>File</small><b>' + escapeHtml(x.filename) + '</b></div>' +
          '<div><small>Size</small><b>' + kb(x.size) + ' KB</b></div>' +
          '<div><small>Lines</small><b>' + x.lines + '</b></div>' +
          '<div><small>Characters</small><b>' + x.characters + '</b></div>' +
        '</div>' +
        (x.syntax_error ? '<div class="syntax"><span>Syntax</span>' + escapeHtml(x.syntax_error) + '</div>' : '') +
        '<div class="actions">' +
          '<button id="download" type="button">↓ Download file</button>' +
          '<button id="zip" type="button" class="secondary">↓ Download ZIP</button>' +
        '</div>';

      result.hidden = false;

      document.querySelector("#download").onclick = () => postDownload("/download");
      document.querySelector("#zip").onclick = () => postDownload("/download-zip");
    } catch (e) {
      showError(e.message);
    } finally {
      analyzeBtn.disabled = false;
      analyzeBtn.querySelector(".label").textContent = "Analyze file";
    }
  });

  async function postDownload(url) {
    if (!fileInput.files[0]) return showError("Please select a file first.");
    const fd = new FormData();
    fd.append("file", fileInput.files[0]);
    const r = await fetch(url, { method: "POST", body: fd });
    if (!r.ok) {
      const x = await r.json().catch(() => ({ error: "Download failed." }));
      return showError(x.error || "Download failed.");
    }
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = url.endsWith("zip") ? "python-file.zip" : fileInput.files[0].name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
  }
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def safe_name(name):
    """Reduce an uploaded filename to a safe, flat basename."""
    name = (name or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).lstrip(".")
    return name or "file"


def extension(name):
    dot = name.rfind(".")
    return name[dot:].lower() if dot != -1 else ""


def parse_multipart(body, boundary):
    """Minimal multipart/form-data parser -> {field: (filename|None, bytes)}."""
    fields = {}
    delimiter = b"--" + boundary
    for part in body.split(delimiter):
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.startswith(b"--"):          # closing marker
            continue
        if part.endswith(b"\r\n"):
            part = part[:-2]
        if b"\r\n\r\n" not in part:
            continue
        raw_headers, data = part.split(b"\r\n\r\n", 1)
        disposition = ""
        for line in raw_headers.split(b"\r\n"):
            if line.lower().startswith(b"content-disposition:"):
                disposition = line.decode("utf-8", "replace")
                break
        m_name = re.search(r'name="([^"]*)"', disposition)
        if not m_name:
            continue
        m_file = re.search(r'filename="([^"]*)"', disposition)
        fields[m_name.group(1)] = (m_file.group(1) if m_file else None, data)
    return fields


# --------------------------------------------------------------------------
# request handler
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "PyFileTools/1.0"

    # -- low level ---------------------------------------------------------
    def _send(self, code, body=b"", content_type="text/plain; charset=utf-8", headers=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

    # -- routes ------------------------------------------------------------
    def do_GET(self):
        if urlparse(self.path).path in ("/", "/index.html"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._json(404, {"error": "Not found."})

    def do_POST(self):
        path = urlparse(self.path).path

        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BYTES + 8192:
            return self._json(413, {"error": "File is too large. Maximum size is 5 MB."})
        body = self.rfile.read(length) if length else b""

        boundary = re.search(r'boundary="?([^";]+)"?', self.headers.get("Content-Type", ""))
        if not boundary:
            return self._json(400, {"error": "Invalid upload."})

        fields = parse_multipart(body, boundary.group(1).encode("latin-1"))
        filename, data = fields.get("file", (None, b""))
        if not filename:
            return self._json(400, {"error": "No file selected."})

        name = safe_name(filename)
        ext = extension(name)
        if ext not in ALLOWED:
            return self._json(400, {"error": "Only .py and .txt files are supported."})

        if path == "/analyze":
            if b"\x00" in data:
                return self._json(400, {"error": "Binary files are not supported."})
            text = data.decode("utf-8", errors="replace")
            result = {
                "filename": name,
                "size": len(data),
                "lines": len(text.splitlines()),
                "characters": len(text),
                "python_valid": None,
                "syntax_error": None,
            }
            if ext == ".py":
                try:
                    ast.parse(text)
                    result["python_valid"] = True
                except SyntaxError as exc:
                    result["python_valid"] = False
                    result["syntax_error"] = "Line %s: %s" % (exc.lineno, exc.msg)
            return self._json(200, {"result": result})

        if path == "/download":
            return self._send(
                200, data, "text/plain; charset=utf-8",
                {"Content-Disposition": 'attachment; filename="%s"' % name},
            )

        if path == "/download-zip":
            mem = io.BytesIO()
            with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(name, data)
            stem = name.rsplit(".", 1)[0] or "file"
            return self._send(
                200, mem.getvalue(), "application/zip",
                {"Content-Disposition": 'attachment; filename="%s.zip"' % stem},
            )

        return self._json(404, {"error": "Not found."})

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


def main():
    port = int(os.environ.get("PORT", 5000))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("PyFile Tools running on http://0.0.0.0:%d" % port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
