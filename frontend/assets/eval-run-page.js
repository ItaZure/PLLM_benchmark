// Evaluation detail page (read-only). Reached via the history list's 【查看】
// entry, which is only shown for 'done' evaluations — so this page never needs
// run/cancel/scoring controls or status polling.
(function () {
  document.getElementById("sidebar").innerHTML = renderSidebar("evaluations");
  const evalId = new URLSearchParams(location.search).get("id");
  if (!evalId) { toast("缺少评测 id", "error"); return; }

  function truncate(s, n) { s = s || ""; return s.length > n ? s.slice(0, n) + "…" : s; }
  function num(v, d = 0) { return v == null ? "—" : Number(v).toFixed(d); }

  // Task type lookup so we can label auto vs blind scores.
  function taskTypeMap(d) {
    const m = {};
    d.tasks.forEach((t) => { m[t.task_id] = t.task_type; });
    return m;
  }

  function renderOutput(r) {
    if (r.model_type !== "chat" && r.status === "success" && r.output_text) {
      const u = escapeAttr(r.output_text);
      return `<a href="${u}" target="_blank" rel="noopener">
        <img src="${u}" alt="生成图片" loading="lazy"
             class="h-16 w-16 object-cover rounded border border-black/10" /></a>`;
    }
    const txt = r.error || r.output_text || "";
    return `<span title="${escapeAttr(txt)}">${escapeHtml(truncate(txt, 40))}</span>`;
  }

  function scoreCell(r, types) {
    if (r.score == null) {
      if (types[r.task_id] === "open" && r.status === "success")
        return `<span class="text-[11px] text-[#b45309]">待盲评</span>`;
      return "—";
    }
    const tag = r.auto_scored
      ? `<span class="ml-1 text-[10px] text-black/40">自动</span>`
      : `<span class="ml-1 text-[10px] text-[#b45309]">盲评</span>`;
    return `${r.score}${tag}`;
  }

  function renderResults(d) {
    const tbody = document.getElementById("rows");
    if (d.results.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="px-3 py-10 text-center text-black/40 text-[13px]">无结果</td></tr>`;
      return;
    }
    const types = taskTypeMap(d);
    tbody.innerHTML = d.results.map((r, i) => `
      <tr class="border-t border-black/[0.05] ${i % 2 ? "bg-[#fcfcfc]" : ""}">
        <td class="px-3 py-2.5">${escapeHtml(r.task_name) || "—"}</td>
        <td class="px-3 py-2.5">${escapeHtml(r.model_name) || "—"}</td>
        <td class="px-3 py-2.5">${resultStatusBadge(r.status)}</td>
        <td class="px-3 py-2.5 mono text-[12px]">${scoreCell(r, types)}</td>
        <td class="px-3 py-2.5 mono text-[12px] text-black/65">${num(r.ttft_ms, 0)}${r.ttft_ms != null ? "ms" : ""}</td>
        <td class="px-3 py-2.5 mono text-[12px] text-black/65">${num(r.char_per_sec, 2)}</td>
        <td class="px-3 py-2.5 mono text-[12px] text-black/65">${r.output_char_count == null ? "—" : r.output_char_count}</td>
        <td class="px-3 py-2.5 text-[12px] text-black/55">${renderOutput(r)}</td>
      </tr>`).join("");
  }

  function renderSummary(d) {
    const box = document.getElementById("summary");
    if (!box) return;
    // Aggregate score per model across all its results (Σscore / Σweight).
    const agg = {};
    const weight = {};
    d.tasks.forEach((t) => { weight[t.task_id] = t.score_weight; });
    d.results.forEach((r) => {
      const key = r.model_name || r.model_id;
      if (!agg[key]) agg[key] = { score: 0, max: 0 };
      agg[key].max += weight[r.task_id] || 0;
      if (r.score != null) agg[key].score += r.score;
    });
    const rows = Object.entries(agg).sort((a, b) => b[1].score - a[1].score);
    if (rows.length === 0) { box.innerHTML = ""; return; }
    box.innerHTML = `
      <div class="text-[13px] font-medium mb-2">模型汇总（按满分加权）</div>
      <div class="flex flex-wrap gap-2">
        ${rows.map(([name, v]) => `
          <div class="border border-[var(--border)] rounded-md px-3 py-2 min-w-[140px]">
            <div class="text-[13px] font-medium truncate">${escapeHtml(name)}</div>
            <div class="mono text-[15px] mt-0.5">${v.score} <span class="text-[11px] text-black/40">/ ${v.max}</span></div>
          </div>`).join("")}
      </div>`;
  }

  (async () => {
    try {
      const res = await apiFetch(`/evaluations/${evalId}`);
      const d = res.data;
      document.getElementById("title").textContent = d.name;
      document.getElementById("statusBadge").innerHTML = evalStatusBadge(d.status);
      renderSummary(d);
      renderResults(d);
    } catch (e) {
      toast("加载失败：" + e.message, "error");
    }
  })();
})();
