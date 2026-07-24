// Shared frontend helpers: API client, sidebar nav, toast, status badges.
const API_BASE = "/api";

// Global <select> styling: replace the native dropdown arrow with a custom
// SVG placed with breathing room from the right border (native arrows hug
// the edge and can't be padded). Injected once for every page loading app.js.
(function injectSelectStyle() {
  const arrow =
    "data:image/svg+xml;utf8," +
    encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" ' +
      'viewBox="0 0 24 24" fill="none" stroke="rgba(0,0,0,0.5)" ' +
      'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M6 9l6 6 6-6"/></svg>'
    );
  const css = `
    select {
      -webkit-appearance: none; -moz-appearance: none; appearance: none;
      background-image: url("${arrow}");
      background-repeat: no-repeat;
      background-position: right 10px center;
      padding-right: 30px !important;
    }
    select::-ms-expand { display: none; }`;
  const el = document.createElement("style");
  el.textContent = css;
  document.head.appendChild(el);
})();

async function apiFetch(path, options = {}) {
  const opts = { headers: { "Content-Type": "application/json" }, ...options };
  const resp = await fetch(API_BASE + path, opts);
  let body = null;
  try {
    body = await resp.json();
  } catch (e) {
    body = null;
  }
  if (!resp.ok) {
    const detail = (body && body.detail) || `HTTP ${resp.status}`;
    throw new Error(detail);
  }
  return body;
}

// --- Sidebar navigation (shared across all pages) ---
const NAV = [
  { group: "模型", items: [
    { label: "Chat 模型", href: "chat-models.html", key: "chat" },
    { label: "图片生成模型", href: "image-models.html", key: "image" },
    { label: "评测生成模型", href: "generation-model.html", key: "generation-model" },
  ]},
  { group: "Benchmark", items: [
    { label: "维度管理", href: "dimensions.html", key: "dimensions" },
    { label: "任务管理", href: "tasks.html", key: "tasks" },
  ]},
  { group: "评测", items: [
    { label: "运行评测", href: "evaluations-new.html", key: "eval-run" },
    { label: "历史评测结果", href: "evaluations.html", key: "evaluations" },
  ]},
];

function renderSidebar(activeKey) {
  const nav = NAV.map((g) => {
    const items = g.items.map((it) => {
      const active = it.key === activeKey ? "active" : "";
      return `<a href="${it.href}" class="nav-item ${active}">${it.label}</a>`;
    }).join("");
    return `<div class="px-3 pt-3 pb-1.5 text-[11px] font-medium tracking-wide text-black/40 uppercase">${g.group}</div>${items}`;
  }).join("");
  return `
  <aside class="w-[220px] h-screen shrink-0 bg-[#fafafa] border-r border-[var(--border)] flex flex-col">
    <div class="h-14 flex items-center gap-2 px-4 border-b border-[var(--border)]">
      <img src="/favicon.svg" alt="" class="w-6 h-6 rounded-md" />
      <span class="text-[14px] font-semibold">PLLM Benchmark</span>
    </div>
    <nav class="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">${nav}</nav>
  </aside>`;
}

// --- Toast ---
function toast(msg, kind = "info") {
  const colors = {
    ok: ["#15803d", "#f0fdf4"], error: ["#b91c1c", "#fef2f2"],
    info: ["#1d4ed8", "#eff6ff"],
  };
  const [c, bg] = colors[kind] || colors.info;
  const el = document.createElement("div");
  el.className = "fixed bottom-5 right-5 z-50 px-4 py-2.5 rounded-md text-[13px] font-medium shadow-lg";
  el.style.color = c;
  el.style.background = bg;
  el.style.border = `1px solid ${c}33`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => { el.style.transition = "opacity .3s"; el.style.opacity = "0"; }, 2200);
  setTimeout(() => el.remove(), 2600);
}

// --- Status badge ---
const BADGE = {
  ok: ["可用", "#15803d", "#f0fdf4"],
  error: ["不可用", "#b91c1c", "#fef2f2"],
  untested: ["未测试", "rgba(0,0,0,0.55)", "#f5f5f5"],
};

function badgeHtml(status, error) {
  if (status === "testing") {
    return `<span class="inline-flex items-center gap-1.5 h-5 px-2 rounded text-[11px] font-medium" style="color:#1d4ed8;background:#eff6ff"><svg class="w-3 h-3 spin" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-6.2-8.5"/></svg>测试中</span>`;
  }
  const key = status === "ok" ? "ok" : status === "error" ? "error" : "untested";
  const [txt, c, bg] = BADGE[key];
  const dot = `<span class="w-1.5 h-1.5 rounded-full" style="background:${c}"></span>`;
  const tip = key === "error" && error ? `title="${escapeAttr(error)}"` : "";
  const cursor = key === "error" ? "cursor-help" : "";
  return `<span ${tip} class="inline-flex items-center gap-1.5 h-5 px-2 rounded text-[11px] font-medium ${cursor}" style="color:${c};background:${bg}">${dot}${txt}</span>`;
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}
function escapeAttr(s) { return escapeHtml(s); }

// Minimal, dependency-free Markdown -> HTML for rendering model output.
// HTML is escaped FIRST (model output is untrusted), then a safe subset of
// Markdown is applied: headings, bold/italic/inline-code, links, fenced &
// inline code, blockquotes, ordered/unordered lists, and paragraphs.
function renderInlineMd(s) {
  // Inline code first so its contents aren't touched by other rules.
  s = s.replace(/`([^`]+)`/g,
    '<code class="px-1 py-0.5 rounded bg-black/[0.06] mono text-[12px]">$1</code>');
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
  // Links [text](url) — url already HTML-escaped; block javascript: scheme.
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener" class="text-[#1d4ed8] hover:underline">$1</a>');
  return s;
}

function renderMarkdown(src) {
  if (src == null) return "";
  const lines = escapeHtml(String(src)).split("\n");
  const out = [];
  let i = 0;
  let inCode = false, codeBuf = [];
  let listType = null, listBuf = [];
  const flushList = () => {
    if (!listType) return;
    const tag = listType;
    const cls = tag === "ul"
      ? "list-disc pl-5 space-y-0.5 my-1.5"
      : "list-decimal pl-5 space-y-0.5 my-1.5";
    out.push(`<${tag} class="${cls}">${listBuf.join("")}</${tag}>`);
    listBuf = []; listType = null;
  };
  while (i < lines.length) {
    const line = lines[i];
    // Fenced code block ```
    const fence = line.match(/^\s*```/);
    if (fence) {
      if (inCode) {
        out.push(`<pre class="my-1.5 p-2.5 rounded bg-black/[0.05] overflow-x-auto"><code class="mono text-[12px] leading-relaxed">${codeBuf.join("\n")}</code></pre>`);
        codeBuf = []; inCode = false;
      } else {
        flushList(); inCode = true;
      }
      i++; continue;
    }
    if (inCode) { codeBuf.push(line); i++; continue; }
    // Headings
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      flushList();
      const lvl = h[1].length;
      const sz = { 1: "text-[16px]", 2: "text-[15px]", 3: "text-[14px]", 4: "text-[13px]" }[lvl];
      out.push(`<div class="${sz} font-semibold mt-2 mb-1">${renderInlineMd(h[2])}</div>`);
      i++; continue;
    }
    // Blockquote
    const bq = line.match(/^\s*>\s?(.*)$/);
    if (bq) {
      flushList();
      out.push(`<blockquote class="border-l-2 border-black/15 pl-3 my-1.5 text-black/60">${renderInlineMd(bq[1])}</blockquote>`);
      i++; continue;
    }
    // List items
    const ul = line.match(/^\s*[-*+]\s+(.*)$/);
    const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (ul || ol) {
      const t = ul ? "ul" : "ol";
      if (listType && listType !== t) flushList();
      listType = t;
      listBuf.push(`<li>${renderInlineMd((ul || ol)[1])}</li>`);
      i++; continue;
    }
    // Blank line -> paragraph break
    if (line.trim() === "") { flushList(); i++; continue; }
    // Plain paragraph line
    flushList();
    out.push(`<p class="my-1 leading-relaxed">${renderInlineMd(line)}</p>`);
    i++;
  }
  flushList();
  if (inCode && codeBuf.length) {
    out.push(`<pre class="my-1.5 p-2.5 rounded bg-black/[0.05] overflow-x-auto"><code class="mono text-[12px]">${codeBuf.join("\n")}</code></pre>`);
  }
  return out.join("");
}

const EVAL_STATUS = {
  pending: ["待运行", "rgba(0,0,0,0.55)", "#f5f5f5"],
  running: ["运行中", "#1d4ed8", "#eff6ff"],
  scoring: ["待盲评", "#b45309", "#fffbeb"],
  done: ["已完成", "#15803d", "#f0fdf4"],
  cancelled: ["已取消", "#b45309", "#fffbeb"],
};
function evalStatusBadge(status) {
  const [txt, c, bg] = EVAL_STATUS[status] || [status, "#666", "#eee"];
  const spin = status === "running"
    ? '<svg class="w-3 h-3 spin" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-6.2-8.5"/></svg>'
    : `<span class="w-1.5 h-1.5 rounded-full" style="background:${c}"></span>`;
  return `<span class="inline-flex items-center gap-1.5 h-5 px-2 rounded text-[11px] font-medium" style="color:${c};background:${bg}">${spin}${txt}</span>`;
}
function resultStatusBadge(status) {
  const map = {
    success: ["success", "#15803d", "#f0fdf4"],
    failed: ["failed", "#b91c1c", "#fef2f2"],
    cancelled: ["cancelled", "#b45309", "#fffbeb"],
    skipped: ["skipped", "rgba(0,0,0,0.55)", "#f5f5f5"],
    pending: ["等待中", "rgba(0,0,0,0.55)", "#f5f5f5"],
    streaming: ["streaming", "#1d4ed8", "#eff6ff"],
  };
  const [txt, c, bg] = map[status] || [status, "#666", "#eee"];
  return `<span class="inline-flex items-center h-5 px-2 rounded text-[11px] font-medium" style="color:${c};background:${bg}">${txt}</span>`;
}

const PROVIDER_MODE_LABELS = {
  poe_chat: "POE 同步",
  aicodewith_async: "aicodewith 异步",
};
function providerModeLabel(mode) {
  return PROVIDER_MODE_LABELS[mode] || mode || "—";
}

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
