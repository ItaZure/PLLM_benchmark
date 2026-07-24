// Blind-scoring page: score open-type tasks one by one (1-5 tiers, hidden model).
(function () {
  document.getElementById("sidebar").innerHTML = renderSidebar("evaluations");
  const evalId = new URLSearchParams(location.search).get("id");
  if (!evalId) { toast("缺少评测 id", "error"); return; }
  // Mid-scoring exit returns to the list, where the evaluation shows 继续盲评.
  document.getElementById("backLink").href = "evaluations.html";

  let sessions = [];       // [{task_id, task_name, total, scored, completed}]
  let activeTaskId = null; // current task being scored
  let detail = null;       // ScoringTaskDetail for active task
  const localScores = {};  // blind_id -> tier (1-5), pending submit

  function truncate(s, n) { s = s || ""; return s.length > n ? s.slice(0, n) + "…" : s; }

  let pollTimer = null;

  function sessionOf(taskId) { return sessions.find((s) => s.task_id === taskId); }
  function allCompleted() { return sessions.length > 0 && sessions.every((s) => s.completed); }
  function anyNotReady() { return sessions.some((s) => !s.ready && !s.completed); }

  async function loadSessions() {
    const res = await apiFetch(`/evaluations/${evalId}/scoring-sessions`);
    sessions = res.data;
    if (sessions.length === 0) {
      document.getElementById("cards").innerHTML =
        `<div class="text-[13px] text-black/45">该评测没有开放型任务，无需盲评。</div>`;
      document.getElementById("hint").textContent = "";
      return;
    }
    // All scored already -> evaluation should be done; go to the list.
    if (allCompleted()) { goToList(); return; }
    // Default active task: first not-completed & ready; else keep current.
    if (!activeTaskId || !sessionOf(activeTaskId)) {
      const target = sessions.find((s) => !s.completed && s.ready)
                  || sessions.find((s) => !s.completed);
      activeTaskId = (target || sessions[0]).task_id;
    }
    renderTaskNav();
    const cur = sessionOf(activeTaskId);
    if (cur && cur.ready) {
      await loadTask(activeTaskId);
    } else {
      detail = null;
      renderTaskInfoWaiting(cur);
    }
    scheduleReadinessPoll();
  }

  // Poll for readiness while any task is still generating outputs.
  function scheduleReadinessPoll() {
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
    if (anyNotReady()) {
      pollTimer = setTimeout(async () => {
        try { await refreshSessionsKeepActive(); } catch (e) { /* transient */ }
      }, 3000);
    }
  }

  async function refreshSessionsKeepActive() {
    const res = await apiFetch(`/evaluations/${evalId}/scoring-sessions`);
    sessions = res.data;
    if (allCompleted()) { goToList(); return; }
    renderTaskNav();
    const cur = sessionOf(activeTaskId);
    // If the active task just became ready and isn't loaded, load it.
    if (cur && cur.ready && !detail) { await loadTask(activeTaskId); }
    scheduleReadinessPoll();
  }

  function goToList() {
    if (pollTimer) clearTimeout(pollTimer);
    toast("盲评完成，返回列表", "ok");
    setTimeout(() => { location.href = "evaluations.html"; }, 700);
  }

  function renderTaskNav() {
    document.getElementById("taskNav").innerHTML = sessions.map((s) => {
      const active = s.task_id === activeTaskId;
      let tag, disabled = false;
      if (s.completed) tag = "✓";
      else if (!s.ready) { tag = "生成中"; disabled = true; }
      else tag = `${s.scored}/${s.total}`;
      const cls = active
        ? "bg-[#1a1a1a] text-white border-[#1a1a1a]"
        : disabled
          ? "border-black/10 text-black/30 bg-[#fafafa] cursor-not-allowed"
          : "border-black/16 text-black/70 hover:bg-[#f5f5f5]";
      return `<button data-task="${s.task_id}" ${disabled ? "disabled" : ""}
        class="h-8 px-3 rounded-md text-[12px] font-medium border transition ${cls}">
        ${escapeHtml(s.task_name) || "任务"} <span class="ml-1 mono opacity-70">${tag}</span>
      </button>`;
    }).join("");
    document.getElementById("taskNav").querySelectorAll("[data-task]:not([disabled])").forEach((b) => {
      b.onclick = async () => {
        activeTaskId = b.dataset.task;
        const cur = sessionOf(activeTaskId);
        renderTaskNav();
        if (cur && cur.ready) await loadTask(activeTaskId);
        else { detail = null; renderTaskInfoWaiting(cur); }
      };
    });
  }

  function renderTaskInfoWaiting(s) {
    document.getElementById("taskInfo").innerHTML = `
      <div class="border border-[var(--border)] rounded-lg p-4 bg-[#fafafa]">
        <div class="text-[11px] uppercase tracking-wide text-black/40 font-medium mb-2">开放型任务</div>
        <p class="text-[14px] font-medium mb-1">${escapeHtml(s ? s.task_name : "") || "任务"}</p>
        <p class="text-[12px] text-[#b45309]">该任务的模型输出还在生成中，生成齐后即可打分…</p>
      </div>`;
    document.getElementById("hint").textContent = "";
    document.getElementById("cards").innerHTML = "";
    refreshSubmit();
  }

  async function loadTask(taskId) {
    for (const k in localScores) delete localScores[k];
    const res = await apiFetch(`/evaluations/${evalId}/scoring-sessions/${taskId}`);
    detail = res.data;
    // Preload existing scores as tiers (reverse of tier*weight/5).
    detail.items.forEach((it) => {
      if (it.current_score != null && detail.score_weight) {
        localScores[it.blind_id] = Math.round(it.current_score / (detail.score_weight / 5));
      }
    });
    renderTaskNav();
    renderTaskInfo();
    renderCards();
    refreshSubmit();
  }

  function renderTaskInfo() {
    const rubric = detail.rubric
      ? `<div class="text-[11px] uppercase tracking-wide text-black/40 font-medium mb-1">评分标准 Rubric</div>
         <p class="text-[12px] text-black/60 leading-relaxed whitespace-pre-wrap">${escapeHtml(detail.rubric)}</p>`
      : `<p class="text-[12px] text-black/40">（该任务未设置 rubric）</p>`;
    document.getElementById("taskInfo").innerHTML = `
      <div class="border border-[var(--border)] rounded-lg p-4 bg-[#fafafa]">
        <div class="text-[11px] uppercase tracking-wide text-black/40 font-medium mb-2">开放型任务</div>
        <p class="text-[14px] font-medium mb-2 whitespace-pre-wrap">${escapeHtml(detail.prompt) || escapeHtml(detail.task_name)}</p>
        ${rubric}
        <div class="mt-2 text-[11px] mono text-black/45">满分 ${detail.score_weight} · 打 1-5 档，得分 = 档位 × 满分/5</div>
      </div>`;
    document.getElementById("hint").textContent = detail.total
      ? `以下 ${detail.total} 份输出已随机打乱、隐藏模型名称。请为每份独立打 1-5 档。`
      : "该任务没有成功的输出可评。";
  }

  function cardOutput(it) {
    if (it.model_type !== "chat" && it.output_text) {
      const u = escapeAttr(it.output_text);
      return `<a href="${u}" target="_blank" rel="noopener">
        <img src="${u}" alt="生成图片"
             class="w-full max-h-64 object-contain rounded border border-black/10 bg-white" /></a>`;
    }
    const body = it.output_text
      ? `<div class="text-[13px] text-black/80 md-body">${renderMarkdown(it.output_text)}</div>`
      : `<p class="text-[13px] text-black/40">（无输出）</p>`;
    return `${body}
            <div class="mt-2 text-[12px] mono text-black/40">${(it.output_text || "").length} 字</div>`;
  }

  function renderCards() {
    document.getElementById("cards").innerHTML = detail.items.map((it, i) => {
      const label = "输出 " + String.fromCharCode(65 + i);
      const tier = localScores[it.blind_id] || null;
      return `<div class="border ${tier ? "border-black/16" : "border-[var(--border)]"} rounded-lg flex flex-col overflow-hidden">
        <div class="flex items-center justify-between px-4 h-10 bg-[#fafafa] border-b border-black/[0.05]">
          <span class="text-[13px] font-semibold">${label}</span>
          ${tier ? `<span class="text-[11px] mono text-black/55">已打 ${tier} 档</span>`
                 : '<span class="text-[11px] text-black/35">未打分</span>'}
        </div>
        <div class="px-4 py-3 flex-1">${cardOutput(it)}</div>
        <div class="px-4 py-3 border-t border-black/[0.05]">
          <div class="text-[11px] uppercase tracking-wide text-black/40 font-medium mb-1.5">打分（1-5 档）</div>
          <div class="flex gap-1.5">
            ${[1, 2, 3, 4, 5].map((n) => `
              <button data-bid="${it.blind_id}" data-tier="${n}"
                class="score-btn w-9 h-9 rounded-md border text-[13px] font-medium
                  ${tier === n ? "bg-[#1a1a1a] text-white border-[#1a1a1a]"
                               : "border-black/16 text-black/65 hover:bg-[#f5f5f5]"}">${n}</button>`).join("")}
          </div>
        </div>
      </div>`;
    }).join("");
    document.getElementById("cards").querySelectorAll("[data-tier]").forEach((b) => {
      b.onclick = () => { localScores[b.dataset.bid] = parseInt(b.dataset.tier, 10); renderCards(); refreshSubmit(); };
    });
  }

  function refreshSubmit() {
    const scored = detail ? detail.items.filter((it) => localScores[it.blind_id]).length : 0;
    const total = detail ? detail.items.length : 0;
    document.getElementById("progressBadge").innerHTML =
      `<span class="w-1.5 h-1.5 rounded-full" style="background:#b45309"></span>本任务 <span class="mono">${scored}/${total}</span>`;
    const btn = document.getElementById("submitBtn");
    const all = total > 0 && scored === total;
    btn.disabled = !all;
    btn.classList.toggle("opacity-40", !all);
    btn.classList.toggle("pointer-events-none", !all);
  }

  document.getElementById("submitBtn").onclick = async () => {
    if (!detail) return;
    try {
      // Submit each entry's tier sequentially; backend advances + finalizes.
      for (const it of detail.items) {
        await apiFetch(`/evaluations/${evalId}/scoring-sessions/${activeTaskId}/score`, {
          method: "POST",
          body: JSON.stringify({ blind_id: it.blind_id, tier: localScores[it.blind_id] }),
        });
      }
      toast("本任务打分已提交", "ok");
      // Move to the next unscored task, or leave to the list if all done.
      detail = null;
      activeTaskId = null;
      await loadSessions();
    } catch (e) {
      toast(e.message, "error");
    }
  };

  loadSessions().catch((e) => toast("加载失败：" + e.message, "error"));
})();
