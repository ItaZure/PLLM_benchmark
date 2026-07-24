// Task management page: dimension filter, table, drawer with type-dependent fields.
(function () {
  let tasks = [];
  let dimensions = [];
  let editId = null;
  let filterDim = "";

  document.getElementById("sidebar").innerHTML = renderSidebar("tasks");

  const TYPE_BADGE = {
    closed: ["封闭型", "#1d4ed8", "#eff6ff"],
    open: ["开放型", "#b45309", "#fffbeb"],
  };
  function typeBadge(t) {
    const [txt, c, bg] = TYPE_BADGE[t] || ["?", "#666", "#eee"];
    return `<span class="inline-flex items-center h-5 px-2 rounded text-[11px] font-medium" style="color:${c};background:${bg}">${txt}</span>`;
  }

  async function loadDimensions() {
    const res = await apiFetch("/dimensions");
    dimensions = res.data;
    // Populate both the top filter and the drawer select.
    const opts = dimensions.map((d) => `<option value="${d.id}">${escapeHtml(d.name)}</option>`).join("");
    document.getElementById("filterDim").innerHTML =
      `<option value="">全部维度</option>` + opts;
    document.getElementById("fDim").innerHTML = opts ||
      `<option value="">（请先创建维度）</option>`;
  }

  async function load() {
    try {
      await loadDimensions();
      const q = filterDim ? `?dimension_id=${filterDim}` : "";
      const res = await apiFetch("/tasks" + q);
      tasks = res.data;
      render();
    } catch (e) {
      toast("加载失败：" + e.message, "error");
    }
  }

  function truncate(s, n) {
    s = s || "";
    return s.length > n ? s.slice(0, n) + "…" : s;
  }

  function render() {
    document.getElementById("count").textContent = `共 ${tasks.length} 个`;
    const tbody = document.getElementById("rows");
    if (tasks.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="px-3 py-10 text-center text-black/40 text-[13px]">${filterDim ? "该维度下暂无任务" : "还没有任务，点击右上角新增"}</td></tr>`;
      return;
    }
    tbody.innerHTML = tasks.map((t, i) => `
      <tr class="border-t border-black/[0.05] ${i % 2 ? "bg-[#fcfcfc]" : ""} transition-colors">
        <td class="px-3 py-2.5 font-medium">${escapeHtml(t.name)}</td>
        <td class="px-3 py-2.5 text-[12px] text-black/65">${escapeHtml(t.dimension_name) || "—"}</td>
        <td class="px-3 py-2.5">${typeBadge(t.task_type)}</td>
        <td class="px-3 py-2.5 text-[12px] text-black/55">${escapeHtml(truncate(t.prompt, 50))}</td>
        <td class="px-3 py-2.5 mono text-[12px] text-black/45">${fmtTime(t.created_at)}</td>
        <td class="px-3 py-2.5 text-right whitespace-nowrap">
          <button data-edit="${t.id}" class="text-[12px] text-black/65 hover:text-black hover:underline">编辑</button>
          <button data-del="${t.id}" class="ml-3 text-[12px] text-[#b91c1c]/80 hover:text-[#b91c1c] hover:underline">删除</button>
        </td>
      </tr>`).join("");
    tbody.querySelectorAll("[data-edit]").forEach((b) => b.onclick = () => openDrawer(b.dataset.edit));
    tbody.querySelectorAll("[data-del]").forEach((b) => b.onclick = () => delTask(b.dataset.del));
  }

  function syncTypeFields() {
    const type = document.getElementById("fType").value;
    document.getElementById("closedFields").classList.toggle("hidden", type !== "closed");
    document.getElementById("openFields").classList.toggle("hidden", type !== "open");
  }

  // 【自动生成】仅在选中了所属维度后可用。
  function syncGenButton() {
    const hasDim = !!document.getElementById("fDim").value;
    document.getElementById("btnGen").disabled = !hasDim;
  }

  let generating = false;
  async function autoGenerate() {
    if (generating) return;
    const dimId = document.getElementById("fDim").value;
    if (!dimId) { toast("请先选择所属维度", "error"); return; }
    const type = document.getElementById("fType").value;
    // 已填任务名称时作为出题线索；空则走维度自由出题。
    const nameHint = document.getElementById("fName").value.trim();
    const btn = document.getElementById("btnGen");
    const icon = document.getElementById("genIcon");
    const label = document.getElementById("genLabel");
    generating = true;
    btn.disabled = true;
    icon.classList.add("spin");
    label.textContent = "生成中…";
    try {
      const res = await apiFetch("/tasks/generate", {
        method: "POST",
        body: JSON.stringify({
          dimension_id: dimId, task_type: type,
          name_hint: nameHint || null,
        }),
      });
      const d = res.data;
      // 回填表单（不落库，用户可再改后保存）。名称已填则保留用户的。
      document.getElementById("fName").value = d.name || "";
      document.getElementById("fPrompt").value = d.prompt || "";
      if (d.task_type === "closed") {
        document.getElementById("fRegex").value = d.scoring_regex || "[A-D]";
        document.getElementById("fExpected").value = d.expected_answer || "";
      }
      toast("已生成，可修改后保存", "ok");
    } catch (e) {
      toast("生成失败：" + e.message, "error");
    } finally {
      generating = false;
      icon.classList.remove("spin");
      label.textContent = "自动生成";
      syncGenButton();
    }
  }

  async function delTask(id) {
    const t = tasks.find((x) => x.id === id);
    if (!confirm(`删除任务「${t ? t.name : ""}」？`)) return;
    try {
      await apiFetch(`/tasks/${id}`, { method: "DELETE" });
      toast("已删除", "ok");
      load();
    } catch (e) { toast(e.message, "error"); }
  }

  function openDrawer(id) {
    editId = id || null;
    const t = id ? tasks.find((x) => x.id === id) : null;
    document.getElementById("drawerTitle").textContent = editId ? "编辑任务" : "新增任务";
    // Default dimension: current filter, else first dimension.
    const defDim = t ? t.dimension_id : (filterDim || (dimensions[0] && dimensions[0].id) || "");
    document.getElementById("fDim").value = defDim;
    document.getElementById("fName").value = t ? t.name : "";
    document.getElementById("fType").value = t ? t.task_type : "open";
    document.getElementById("fPrompt").value = t ? t.prompt : "";
    // 新建任务默认正则 [A-D]（选择题），编辑时保留原值
    document.getElementById("fRegex").value = t ? (t.scoring_regex || "") : "[A-D]";
    document.getElementById("fExpected").value = t && t.expected_answer ? t.expected_answer : "";
    document.getElementById("fRubric").value = t && t.scoring_rubric ? t.scoring_rubric : "";
    syncTypeFields();
    syncGenButton();
    const dr = document.getElementById("drawer");
    dr.classList.remove("hidden");
    requestAnimationFrame(() => {
      document.getElementById("drawerMask").style.opacity = "1";
      document.getElementById("drawerPanel").classList.remove("translate-x-full");
    });
  }
  function closeDrawer() {
    document.getElementById("drawerMask").style.opacity = "0";
    document.getElementById("drawerPanel").classList.add("translate-x-full");
    setTimeout(() => document.getElementById("drawer").classList.add("hidden"), 250);
  }

  async function saveTask() {
    const dimId = document.getElementById("fDim").value;
    const name = document.getElementById("fName").value.trim();
    const type = document.getElementById("fType").value;
    const prompt = document.getElementById("fPrompt").value.trim();
    if (!dimId) { toast("请选择所属维度（可能还没有维度）", "error"); return; }
    if (!name) { toast("请填写任务名称", "error"); return; }
    if (!prompt) { toast("请填写任务提示词", "error"); return; }
    const payload = {
      dimension_id: dimId, name, task_type: type, prompt,
      scoring_regex: null, expected_answer: null, scoring_rubric: null,
    };
    if (type === "closed") {
      payload.scoring_regex = document.getElementById("fRegex").value.trim();
      payload.expected_answer = document.getElementById("fExpected").value.trim();
      if (!payload.scoring_regex || !payload.expected_answer) {
        toast("封闭型需填写正则和标准答案", "error"); return;
      }
    } else {
      // 评分说明非必填
      payload.scoring_rubric = document.getElementById("fRubric").value.trim() || null;
    }
    try {
      if (editId) {
        await apiFetch(`/tasks/${editId}`, { method: "PUT", body: JSON.stringify(payload) });
        toast("已保存", "ok");
      } else {
        await apiFetch("/tasks", { method: "POST", body: JSON.stringify(payload) });
        toast("已新增", "ok");
      }
      closeDrawer();
      load();
    } catch (e) { toast("保存失败：" + e.message, "error"); }
  }

  document.getElementById("fType").onchange = syncTypeFields;
  document.getElementById("fDim").onchange = syncGenButton;
  document.getElementById("btnGen").onclick = autoGenerate;
  document.getElementById("filterDim").onchange = (e) => { filterDim = e.target.value; load(); };
  document.getElementById("btnNew").onclick = () => openDrawer(null);
  document.getElementById("btnSave").onclick = saveTask;
  document.getElementById("btnCancel").onclick = closeDrawer;
  document.getElementById("btnClose").onclick = closeDrawer;
  document.getElementById("drawerMask").onclick = closeDrawer;

  load();
})();
