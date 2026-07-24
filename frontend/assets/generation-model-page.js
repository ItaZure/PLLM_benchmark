// Generation-model settings page: single-select a chat model as the AI
// task-generator. Reads /settings/generation-model and the chat model list.
(function () {
  let chatModels = [];
  let currentId = "";

  document.getElementById("sidebar").innerHTML = renderSidebar("generation-model");

  async function load() {
    try {
      const [models, setting] = await Promise.all([
        apiFetch("/models/chat"),
        apiFetch("/settings/generation-model"),
      ]);
      chatModels = models.data;
      currentId = setting.data.generation_chat_model_id || "";
      renderOptions();
      renderCurrent(setting.data);
    } catch (e) {
      toast("加载失败：" + e.message, "error");
    }
  }

  function renderOptions() {
    const sel = document.getElementById("fModel");
    if (chatModels.length === 0) {
      sel.innerHTML = `<option value="">（请先在 Chat 模型页添加模型）</option>`;
      return;
    }
    const opts = chatModels.map((m) =>
      `<option value="${m.id}" ${m.id === currentId ? "selected" : ""}>${escapeHtml(m.name)}（${escapeHtml(m.model_name)}）</option>`
    ).join("");
    // Allow clearing the selection.
    sel.innerHTML = `<option value="">（未设置）</option>` + opts;
    sel.value = currentId;
  }

  function renderCurrent(data) {
    const el = document.getElementById("current");
    if (data.generation_chat_model_id) {
      el.textContent = `当前生成模型：${data.display_name}（${data.model_name}）`;
    } else {
      el.textContent = "当前未设置生成模型。";
    }
  }

  async function save() {
    const id = document.getElementById("fModel").value;
    try {
      const res = await apiFetch("/settings/generation-model", {
        method: "PUT",
        body: JSON.stringify({ generation_chat_model_id: id || null }),
      });
      currentId = res.data.generation_chat_model_id || "";
      renderCurrent(res.data);
      toast("已保存", "ok");
    } catch (e) {
      toast("保存失败：" + e.message, "error");
    }
  }

  document.getElementById("btnSave").onclick = save;
  load();
})();
