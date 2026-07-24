// Create-evaluation page: pick dimension -> its tasks (with weight) + whitelist models.
(function () {
  let dimensions = [];
  let tasks = [];         // tasks in selected dimension
  let whitelist = [];     // {model_id, model_type, name}
  const selTasks = {};    // task_id -> weight (selected)
  const selModels = {};   // "type:id" -> {model_id, model_type}

  document.getElementById("sidebar").innerHTML = renderSidebar("eval-run");

  async function loadDims() {
    const res = await apiFetch("/dimensions");
    dimensions = res.data;
    document.getElementById("fDim").innerHTML = dimensions.length
      ? dimensions.map((d) => `<option value="${d.id}">${escapeHtml(d.name)}</option>`).join("")
      : `<option value="">（请先创建维度）</option>`;
  }

  async function onDimChange() {
    const dimId = document.getElementById("fDim").value;
    for (const k in selTasks) delete selTasks[k];
    for (const k in selModels) delete selModels[k];
    if (!dimId) { tasks = []; whitelist = []; renderTasks(); renderModels(); return; }
    const dim = dimensions.find((d) => d.id === dimId);
    whitelist = dim ? (dim.whitelist || []) : [];
    const res = await apiFetch(`/tasks?dimension_id=${dimId}`);
    tasks = res.data;
    // 默认全选：任务用默认满分 5，模型全部选中。
    tasks.forEach((t) => { selTasks[t.id] = 5; });
    whitelist.forEach((m) => {
      selModels[`${m.model_type}:${m.model_id}`] = { model_id: m.model_id, model_type: m.model_type };
    });
    renderTasks();
    renderModels();
  }

  function renderTasks() {
    const el = document.getElementById("taskList");
    if (tasks.length === 0) {
      el.innerHTML = `<div class="px-3 py-4 text-[12px] text-black/40">该维度下暂无任务</div>`;
      return;
    }
    const typeName = { closed: "封闭型", open: "开放型" };
    el.innerHTML = tasks.map((t) => {
      const on = t.id in selTasks;
      return `<div class="flex items-center gap-3 px-3 py-2">
        <input type="checkbox" data-task="${t.id}" ${on ? "checked" : ""} class="w-4 h-4" />
        <span class="flex-1 text-[13px]">${escapeHtml(t.name)}
          <span class="ml-2 text-[11px] text-black/45">${typeName[t.task_type] || t.task_type}</span></span>
        <label class="text-[12px] text-black/45">满分</label>
        <select data-weight="${t.id}"
          class="w-16 h-7 px-2 text-[13px] mono border border-black/12 rounded-md bg-white ${on ? "" : "opacity-40"}" ${on ? "" : "disabled"}>
          ${[5, 10, 15, 20].map((v) => `<option value="${v}" ${(on ? selTasks[t.id] : 5) === v ? "selected" : ""}>${v}</option>`).join("")}
        </select>
      </div>`;
    }).join("");
    el.querySelectorAll("[data-task]").forEach((cb) => {
      cb.onchange = () => {
        const id = cb.dataset.task;
        if (cb.checked) selTasks[id] = 5; else delete selTasks[id];
        renderTasks();
      };
    });
    el.querySelectorAll("[data-weight]").forEach((inp) => {
      inp.onchange = () => {
        selTasks[inp.dataset.weight] = parseInt(inp.value, 10);
      };
    });
  }

  function renderModels() {
    const el = document.getElementById("modelList");
    if (whitelist.length === 0) {
      el.innerHTML = `<div class="px-3 py-4 text-[12px] text-black/40">该维度白名单为空，请先在维度管理配置</div>`;
      return;
    }
    el.innerHTML = whitelist.map((m) => {
      const key = `${m.model_type}:${m.model_id}`;
      const on = key in selModels;
      const tag = m.model_type === "chat" ? "Chat" : "图片";
      const note = "";
      return `<div class="flex items-center gap-3 px-3 py-2">
        <input type="checkbox" data-model="${key}" data-id="${m.model_id}" data-type="${m.model_type}" ${on ? "checked" : ""} class="w-4 h-4" />
        <span class="flex-1 text-[13px]">${escapeHtml(m.name) || m.model_id}
          <span class="ml-2 text-[11px] text-black/45">${tag}</span>${note}</span>
      </div>`;
    }).join("");
    el.querySelectorAll("[data-model]").forEach((cb) => {
      cb.onchange = () => {
        const key = cb.dataset.model;
        if (cb.checked) selModels[key] = { model_id: cb.dataset.id, model_type: cb.dataset.type };
        else delete selModels[key];
      };
    });
  }

  async function create() {
    const name = document.getElementById("fName").value.trim();
    if (!name) { toast("请填写评测名称", "error"); return; }
    const taskItems = Object.entries(selTasks).map(([task_id, w]) => ({ task_id, score_weight: w }));
    const modelItems = Object.values(selModels);
    if (taskItems.length === 0) { toast("请至少选择一个任务", "error"); return; }
    if (modelItems.length === 0) { toast("请至少选择一个模型", "error"); return; }
    // Does the plan include any open-type task? Those need blind scoring.
    const hasOpen = Object.keys(selTasks).some((tid) => {
      const t = tasks.find((x) => x.id === tid);
      return t && t.task_type === "open";
    });
    try {
      const res = await apiFetch("/evaluations", {
        method: "POST",
        body: JSON.stringify({ name, tasks: taskItems, models: modelItems }),
      });
      const id = res.data.id;
      await apiFetch(`/evaluations/${id}/run`, { method: "POST" });
      if (hasOpen) {
        // Go straight to blind scoring; never pass through the results page
        // before scoring (that would reveal model attribution).
        toast("已创建，进入盲评", "ok");
        location.href = `blind-scoring.html?id=${id}`;
      } else {
        // Pure objective evaluation: no blind scoring, go to the history list.
        toast("已创建并开始运行", "ok");
        location.href = "evaluations.html";
      }
    } catch (e) {
      toast("创建失败：" + e.message, "error");
    }
  }

  // 任务全选：选中全部，保留已设满分，未选的用默认 5。
  function taskSelectAll() {
    tasks.forEach((t) => { if (!(t.id in selTasks)) selTasks[t.id] = 5; });
    renderTasks();
  }
  // 任务反选：已选取消、未选选中（新选中的用默认 5）。
  function taskInvert() {
    tasks.forEach((t) => {
      if (t.id in selTasks) delete selTasks[t.id];
      else selTasks[t.id] = 5;
    });
    renderTasks();
  }
  function modelSelectAll() {
    whitelist.forEach((m) => {
      selModels[`${m.model_type}:${m.model_id}`] = { model_id: m.model_id, model_type: m.model_type };
    });
    renderModels();
  }
  function modelInvert() {
    whitelist.forEach((m) => {
      const key = `${m.model_type}:${m.model_id}`;
      if (key in selModels) delete selModels[key];
      else selModels[key] = { model_id: m.model_id, model_type: m.model_type };
    });
    renderModels();
  }

  document.getElementById("fDim").onchange = onDimChange;
  document.getElementById("btnCreate").onclick = create;
  document.getElementById("taskSelectAll").onclick = taskSelectAll;
  document.getElementById("taskInvert").onclick = taskInvert;
  document.getElementById("modelSelectAll").onclick = modelSelectAll;
  document.getElementById("modelInvert").onclick = modelInvert;

  (async () => {
    try { await loadDims(); await onDimChange(); }
    catch (e) { toast("加载失败：" + e.message, "error"); }
  })();
})();
