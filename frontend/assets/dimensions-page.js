// Dimension management page: card list, drawer form, model whitelist editor.
(function () {
  let dims = [];
  let allModels = []; // {model_id, model_type, name}
  let editId = null;
  const openState = {}; // dimId -> expanded bool
  // Pending whitelist edits per dimension (Set of "type:id" keys) while expanded.
  const draftWhitelist = {};

  document.getElementById("sidebar").innerHTML = renderSidebar("dimensions");

  function keyOf(m) { return `${m.model_type}:${m.model_id}`; }

  async function loadModels() {
    const [chat, image] = await Promise.all([
      apiFetch("/models/chat"), apiFetch("/models/image"),
    ]);
    allModels = [
      ...chat.data.map((m) => ({ model_id: m.id, model_type: "chat", name: m.name })),
      ...image.data.map((m) => ({ model_id: m.id, model_type: "image", name: m.name })),
    ];
  }

  async function load() {
    try {
      await loadModels();
      const res = await apiFetch("/dimensions");
      dims = res.data;
      render();
    } catch (e) {
      toast("加载失败：" + e.message, "error");
    }
  }

  function render() {
    document.getElementById("count").textContent = `共 ${dims.length} 个维度`;
    const list = document.getElementById("list");
    if (dims.length === 0) {
      list.innerHTML = `<div class="text-black/40 text-[13px] py-10 text-center border border-[var(--border)] rounded-lg">还没有维度，点击右上角新增</div>`;
      return;
    }
    list.innerHTML = dims.map((d) => cardHtml(d)).join("");
    bindCardEvents();
  }

  function cardHtml(d) {
    const open = !!openState[d.id];
    const draft = draftWhitelist[d.id] || new Set((d.whitelist || []).map(keyOf));
    const sys = d.system_prompt;
    const cell = (m) => {
      const on = draft.has(keyOf(m));
      const check = on
        ? '<svg class="w-3 h-3 text-white" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg>'
        : "";
      return `<label data-wl="${d.id}" data-key="${keyOf(m)}" class="flex items-center gap-2 h-8 px-2.5 rounded-md border ${on ? "border-black/16 bg-white" : "border-transparent"} hover:bg-white cursor-pointer transition-colors" title="${escapeHtml(m.name)}">
          <span class="w-4 h-4 rounded flex items-center justify-center shrink-0 border ${on ? "bg-[#1a1a1a] border-[#1a1a1a]" : "border-black/24 bg-white"}">${check}</span>
          <span class="text-[13px] truncate ${on ? "text-black" : "text-black/55"}">${escapeHtml(m.name)}</span>
        </label>`;
    };
    const gridCls = "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-1.5";
    const section = (label, list) => list.length === 0 ? "" : `
        <div class="mb-1 mt-2 text-[11px] font-medium text-black/45">${label} · ${list.length}</div>
        <div class="${gridCls}">${list.map(cell).join("")}</div>`;
    const chatModels = allModels.filter((m) => m.model_type === "chat");
    const imageModels = allModels.filter((m) => m.model_type === "image");
    const grid = section("Chat 模型", chatModels) + section("图片生成模型", imageModels);
    const emptyModels = allModels.length === 0
      ? '<div class="text-[12px] text-black/40 py-2">还没有模型，请先到模型管理添加</div>' : "";

    return `
    <div data-dragid="${d.id}" class="dim-card border border-[var(--border)] rounded-lg overflow-hidden bg-white">
      <div data-toggle="${d.id}" class="flex items-center gap-2 px-3 h-[52px] cursor-pointer hover:bg-[#fafafa] transition-colors">
        <span data-grip="${d.id}" title="拖拽排序" class="grip shrink-0 w-5 h-6 flex items-center justify-center text-black/25 hover:text-black/50 cursor-grab active:cursor-grabbing">
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><circle cx="9" cy="6" r="1.4"/><circle cx="15" cy="6" r="1.4"/><circle cx="9" cy="12" r="1.4"/><circle cx="15" cy="12" r="1.4"/><circle cx="9" cy="18" r="1.4"/><circle cx="15" cy="18" r="1.4"/></svg>
        </span>
        <svg class="chev w-4 h-4 text-black/40 ${open ? "rotate-90" : ""}" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-[14px] font-semibold">${escapeHtml(d.name)}</span>
            <span class="text-[11px] text-black/45">${escapeHtml(d.description) || "—"}</span>
          </div>
        </div>
        <span class="text-[12px] text-black/55 mono">${d.task_count} 任务</span>
        <span class="text-[12px] text-black/55 mono">${(d.whitelist || []).length} 模型</span>
        <button data-edit="${d.id}" class="text-[12px] text-black/65 hover:text-black hover:underline">编辑</button>
        <button data-del="${d.id}" class="text-[12px] text-[#b91c1c]/80 hover:text-[#b91c1c] hover:underline">删除</button>
      </div>
      <div class="${open ? "" : "hidden"} border-t border-black/[0.05] bg-[#fcfcfc] px-4 py-4">
        ${sys ? `<div class="mb-3"><div class="text-[11px] uppercase tracking-wide text-black/40 font-medium mb-1">System Prompt</div><div class="text-[12px] text-black/70 leading-relaxed border border-[var(--border)] rounded-md bg-white px-3 py-2 whitespace-pre-wrap">${escapeHtml(sys)}</div></div>` : ""}
        <div class="flex items-center justify-between mb-1.5">
          <div class="text-[11px] uppercase tracking-wide text-black/40 font-medium">模型白名单 · 勾选加入评测范围</div>
          <button data-savewl="${d.id}" class="h-7 px-2.5 rounded-md bg-[#1a1a1a] text-white text-[12px] font-medium hover:bg-black">保存白名单</button>
        </div>
        <div>${grid}</div>
        ${emptyModels}
      </div>
    </div>`;
  }
  function bindCardEvents() {
    const list = document.getElementById("list");
    list.querySelectorAll("[data-toggle]").forEach((el) => {
      el.onclick = (ev) => {
        if (ev.target.closest("[data-edit],[data-del]")) return;
        const id = el.dataset.toggle;
        openState[id] = !openState[id];
        if (openState[id]) {
          // Seed draft from current saved whitelist when expanding.
          const d = dims.find((x) => x.id === id);
          draftWhitelist[id] = new Set((d.whitelist || []).map(keyOf));
        }
        render();
      };
    });
    list.querySelectorAll("[data-edit]").forEach((el) => {
      el.onclick = (ev) => { ev.stopPropagation(); openDrawer(el.dataset.edit); };
    });
    list.querySelectorAll("[data-del]").forEach((el) => {
      el.onclick = (ev) => { ev.stopPropagation(); delDimension(el.dataset.del); };
    });
    list.querySelectorAll("[data-wl]").forEach((el) => {
      el.onclick = (ev) => {
        ev.preventDefault();
        const id = el.dataset.wl;
        const k = el.dataset.key;
        const set = draftWhitelist[id] || new Set();
        if (set.has(k)) set.delete(k); else set.add(k);
        draftWhitelist[id] = set;
        render();
      };
    });
    list.querySelectorAll("[data-savewl]").forEach((el) => {
      el.onclick = (ev) => { ev.stopPropagation(); saveWhitelist(el.dataset.savewl); };
    });
    bindDrag(list);
  }

  // --- Drag to reorder (native HTML5 DnD, drag only starts from the grip) ---
  let dragId = null;
  function bindDrag(list) {
    const cards = [...list.querySelectorAll("[data-dragid]")];
    cards.forEach((card) => {
      const grip = card.querySelector("[data-grip]");
      // Only allow dragging when the grip is the press target.
      if (grip) {
        grip.onmousedown = () => { card.setAttribute("draggable", "true"); };
      }
      card.addEventListener("dragend", () => {
        card.removeAttribute("draggable");
        card.classList.remove("dragging");
        cards.forEach((c) => c.classList.remove("drag-over"));
      });
      card.addEventListener("dragstart", (ev) => {
        dragId = card.dataset.dragid;
        card.classList.add("dragging");
        ev.dataTransfer.effectAllowed = "move";
        try { ev.dataTransfer.setData("text/plain", dragId); } catch (e) {}
      });
      card.addEventListener("dragover", (ev) => {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        if (card.dataset.dragid !== dragId) card.classList.add("drag-over");
      });
      card.addEventListener("dragleave", () => card.classList.remove("drag-over"));
      card.addEventListener("drop", (ev) => {
        ev.preventDefault();
        card.classList.remove("drag-over");
        const targetId = card.dataset.dragid;
        if (!dragId || dragId === targetId) return;
        const from = dims.findIndex((x) => x.id === dragId);
        const to = dims.findIndex((x) => x.id === targetId);
        if (from < 0 || to < 0) return;
        const [moved] = dims.splice(from, 1);
        dims.splice(to, 0, moved);
        render();
        persistOrder();
      });
    });
  }

  async function persistOrder() {
    try {
      await apiFetch("/dimensions/reorder", {
        method: "PUT",
        body: JSON.stringify({ ids: dims.map((d) => d.id) }),
      });
    } catch (e) {
      toast("排序保存失败：" + e.message, "error");
      load(); // reload authoritative order on failure
    }
  }

  async function saveWhitelist(id) {
    const set = draftWhitelist[id] || new Set();
    const models = [...set].map((k) => {
      const [model_type, model_id] = k.split(":");
      return { model_id, model_type };
    });
    try {
      const res = await apiFetch(`/dimensions/${id}/whitelist`, {
        method: "PUT", body: JSON.stringify({ models }),
      });
      const idx = dims.findIndex((x) => x.id === id);
      if (idx >= 0) dims[idx] = res.data;
      toast("白名单已保存", "ok");
      render();
    } catch (e) {
      toast("保存失败：" + e.message, "error");
    }
  }

  async function delDimension(id) {
    const d = dims.find((x) => x.id === id);
    if (!confirm(`删除维度「${d ? d.name : ""}」？`)) return;
    try {
      await apiFetch(`/dimensions/${id}`, { method: "DELETE" });
      toast("已删除", "ok");
      load();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  // --- Drawer ---
  function openDrawer(id) {
    editId = id || null;
    const d = id ? dims.find((x) => x.id === id) : null;
    document.getElementById("drawerTitle").textContent = editId ? "编辑维度" : "新增维度";
    document.getElementById("fName").value = d ? d.name : "";
    document.getElementById("fDesc").value = d && d.description ? d.description : "";
    document.getElementById("fSys").value = d && d.system_prompt ? d.system_prompt : "";
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
  async function saveDimension() {
    const name = document.getElementById("fName").value.trim();
    if (!name) { toast("请填写维度名称", "error"); return; }
    const payload = {
      name,
      description: document.getElementById("fDesc").value.trim() || null,
      system_prompt: document.getElementById("fSys").value.trim() || null,
    };
    try {
      if (editId) {
        await apiFetch(`/dimensions/${editId}`, { method: "PUT", body: JSON.stringify(payload) });
        toast("已保存", "ok");
      } else {
        await apiFetch("/dimensions", { method: "POST", body: JSON.stringify(payload) });
        toast("已新增", "ok");
      }
      closeDrawer();
      load();
    } catch (e) {
      toast("保存失败：" + e.message, "error");
    }
  }

  document.getElementById("btnNew").onclick = () => openDrawer(null);
  document.getElementById("btnSave").onclick = saveDimension;
  document.getElementById("btnCancel").onclick = closeDrawer;
  document.getElementById("btnClose").onclick = closeDrawer;
  document.getElementById("drawerMask").onclick = closeDrawer;

  load();
})();
