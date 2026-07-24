// Reusable model-management page controller for chat & image models.
// Config: { type: 'chat'|'image', label, navKey, paramsPlaceholder }
function initModelsPage(cfg) {
  const endpoint = `/models/${cfg.type}`;
  let models = [];
  let editId = null;
  let searchTerm = "";

  document.getElementById("sidebar").innerHTML = renderSidebar(cfg.navKey);
  document.getElementById("pageTitle").textContent = cfg.label;
  document.getElementById("drawerParamsHint").textContent = cfg.paramsHint;
  document.getElementById("fParams").placeholder = cfg.paramsPlaceholder;

  async function load() {
    try {
      const res = await apiFetch(endpoint);
      models = res.data;
      render();
    } catch (e) {
      toast("加载失败：" + e.message, "error");
    }
  }

  function filtered() {
    if (!searchTerm) return models;
    const t = searchTerm.toLowerCase();
    return models.filter((m) =>
      m.name.toLowerCase().includes(t) ||
      m.model_name.toLowerCase().includes(t) ||
      m.api_base_url.toLowerCase().includes(t)
    );
  }

  function render() {
    const list = filtered();
    document.getElementById("count").textContent = `共 ${models.length} 个`;
    const tbody = document.getElementById("rows");
    if (list.length === 0) {
      const cols = cfg.hasProviderMode ? 7 : 6;
      tbody.innerHTML = `<tr><td colspan="${cols}" class="px-3 py-10 text-center text-black/40 text-[13px]">${models.length === 0 ? "还没有模型，点击右上角新增" : "无匹配结果"}</td></tr>`;
      return;
    }
    tbody.innerHTML = list.map((m, i) => `
      <tr class="border-t border-black/[0.05] ${i % 2 ? "bg-[#fcfcfc]" : ""} transition-colors">
        <td class="px-3 py-2.5 font-medium">${escapeHtml(m.name)}</td>
        <td class="px-3 py-2.5 mono text-[12px] text-black/65">${escapeHtml(m.api_base_url)}</td>
        <td class="px-3 py-2.5 mono text-[12px] text-black/65">${escapeHtml(m.model_name)}</td>
        ${cfg.hasProviderMode ? `<td class="px-3 py-2.5 text-[12px] text-black/65">${providerModeLabel(m.provider_mode)}</td>` : ""}
        <td class="px-3 py-2.5 mono text-[12px] text-black/45">${fmtTime(m.last_tested_at)}</td>
        <td class="px-3 py-2.5" id="badge-${m.id}">${badgeHtml(m.test_status, m.test_error)}</td>
        <td class="px-3 py-2.5 text-right whitespace-nowrap">
          <button data-act="test" data-id="${m.id}" class="text-[12px] text-black/65 hover:text-black hover:underline">测试可用性</button>
          <button data-act="edit" data-id="${m.id}" class="ml-3 text-[12px] text-black/65 hover:text-black hover:underline">编辑</button>
          <button data-act="del" data-id="${m.id}" class="ml-3 text-[12px] text-[#b91c1c]/80 hover:text-[#b91c1c] hover:underline">删除</button>
        </td>
      </tr>`).join("");

    tbody.querySelectorAll("button[data-act]").forEach((btn) => {
      const id = btn.dataset.id;
      const act = btn.dataset.act;
      btn.onclick = () => {
        if (act === "test") testModel(id);
        else if (act === "edit") openDrawer(id);
        else if (act === "del") delModel(id);
      };
    });
  }

  async function testModel(id) {
    const cell = document.getElementById(`badge-${id}`);
    if (cell) cell.innerHTML = badgeHtml("testing");
    try {
      const res = await apiFetch(`${endpoint}/${id}/test`, { method: "POST" });
      const m = models.find((x) => x.id === id);
      if (m) {
        m.test_status = res.data.available ? "ok" : "error";
        m.test_error = res.data.error;
        m.last_tested_at = res.data.tested_at;
      }
      toast(res.data.available ? "模型可用" : "不可用：" + res.data.error,
            res.data.available ? "ok" : "error");
      render();
    } catch (e) {
      toast("测试失败：" + e.message, "error");
      load();
    }
  }

  async function delModel(id) {
    const m = models.find((x) => x.id === id);
    if (!confirm(`删除模型「${m ? m.name : ""}」？`)) return;
    try {
      await apiFetch(`${endpoint}/${id}`, { method: "DELETE" });
      toast("已删除", "ok");
      load();
    } catch (e) {
      toast("删除失败：" + e.message, "error");
    }
  }

  // --- Drawer ---
  function openDrawer(id) {
    editId = id || null;
    const m = id ? models.find((x) => x.id === id) : null;
    document.getElementById("drawerTitle").textContent =
      editId ? `编辑 ${cfg.label}` : `新增 ${cfg.label}`;
    document.getElementById("fName").value = m ? m.name : "";
    document.getElementById("fUrl").value = m ? m.api_base_url : "";
    document.getElementById("fModel").value = m ? m.model_name : "";
    document.getElementById("fParams").value = m
      ? JSON.stringify(m.default_params || {}, null, 2)
      : cfg.paramsDefault;
    const keyInput = document.getElementById("fKey");
    keyInput.value = "";
    keyInput.placeholder = m && m.api_key_set
      ? `已设置（${m.api_key_masked}），留空则不修改`
      : "sk-••••••••••••";
    document.getElementById("drawerKeyLabel").innerHTML = editId
      ? 'API Key <span class="text-black/40 text-[12px] font-normal">（留空保持不变）</span>'
      : 'API Key <span class="text-red-600">*</span>';

    if (cfg.hasProviderMode) {
      const sel = document.getElementById("fProviderMode");
      // New models default to poe_chat; editing preserves stored value.
      sel.value = m ? m.provider_mode : "poe_chat";
    }

    const d = document.getElementById("drawer");
    d.classList.remove("hidden");
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

  async function saveModel() {
    const name = document.getElementById("fName").value.trim();
    const url = document.getElementById("fUrl").value.trim();
    const modelName = document.getElementById("fModel").value.trim();
    const key = document.getElementById("fKey").value;
    const paramsRaw = document.getElementById("fParams").value.trim();

    if (!name || !url || !modelName) {
      toast("请填写名称、Base URL、模型名", "error");
      return;
    }
    if (!editId && !key) {
      toast("新增时必须填写 API Key", "error");
      return;
    }
    let params = {};
    if (paramsRaw) {
      try { params = JSON.parse(paramsRaw); }
      catch (e) { toast("默认参数 JSON 格式错误", "error"); return; }
    }

    const payload = { name, api_base_url: url, model_name: modelName, default_params: params };
    if (key) payload.api_key = key;
    if (cfg.hasProviderMode) {
      payload.provider_mode = document.getElementById("fProviderMode").value;
    }

    try {
      if (editId) {
        await apiFetch(`${endpoint}/${editId}`, { method: "PUT", body: JSON.stringify(payload) });
        toast("已保存", "ok");
      } else {
        await apiFetch(endpoint, { method: "POST", body: JSON.stringify(payload) });
        toast("已新增", "ok");
      }
      closeDrawer();
      load();
    } catch (e) {
      toast("保存失败：" + e.message, "error");
    }
  }

  document.getElementById("btnNew").onclick = () => openDrawer(null);
  document.getElementById("btnSave").onclick = saveModel;
  document.getElementById("btnCancel").onclick = closeDrawer;
  document.getElementById("btnClose").onclick = closeDrawer;
  document.getElementById("drawerMask").onclick = closeDrawer;
  document.getElementById("search").oninput = (e) => { searchTerm = e.target.value; render(); };

  load();
}
