// Per-dimension generation model settings page.
(function () {
  let chatModels = [];
  // Map dim.id -> current generation_model_id (string or "")
  const pending = {};

  document.getElementById("sidebar").innerHTML = renderSidebar("generation-model");

  async function load() {
    try {
      const [modelsRes, dimsRes] = await Promise.all([
        apiFetch("/models/chat"),
        apiFetch("/dimensions"),
      ]);
      chatModels = modelsRes.data;
      renderDimensions(dimsRes.data);
    } catch (e) {
      toast("加载失败：" + e.message, "error");
    }
  }

  function buildOptions(selectedId) {
    const none = `<option value="">（未设置）</option>`;
    if (chatModels.length === 0) {
      return `<option value="">（请先在 Chat 模型页添加模型）</option>`;
    }
    const opts = chatModels.map((m) =>
      `<option value="${m.id}" ${m.id === selectedId ? "selected" : ""}>${escapeHtml(m.name)}（${escapeHtml(m.model_name)}）</option>`
    ).join("");
    return none + opts;
  }

  function renderDimensions(dims) {
    const container = document.getElementById("dimList");
    const empty = document.getElementById("emptyState");
    if (!dims || dims.length === 0) {
      container.innerHTML = "";
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");
    container.innerHTML = dims.map((dim) => {
      const selId = dim.generation_model_id || "";
      pending[dim.id] = selId;
      return `
        <div class="border border-black/10 rounded-lg p-4 space-y-2">
          <div class="font-medium text-[13px]">${escapeHtml(dim.name)}</div>
          ${dim.description ? `<div class="text-[12px] text-black/45">${escapeHtml(dim.description)}</div>` : ""}
          <select
            class="w-full h-9 px-2.5 text-[13px] border border-black/12 rounded-md bg-white"
            data-dim-id="${dim.id}"
          >${buildOptions(selId)}</select>
        </div>`;
    }).join("");

    container.querySelectorAll("select[data-dim-id]").forEach((sel) => {
      sel.addEventListener("change", () => {
        pending[sel.dataset.dimId] = sel.value;
      });
    });
  }

  async function saveAll() {
    const btn = document.getElementById("btnSaveAll");
    btn.disabled = true;
    btn.textContent = "保存中…";
    let ok = 0;
    let fail = 0;
    try {
      await Promise.all(
        Object.entries(pending).map(async ([dimId, modelId]) => {
          try {
            await apiFetch(`/dimensions/${dimId}`, {
              method: "PUT",
              body: JSON.stringify({ generation_model_id: modelId || null }),
            });
            ok++;
          } catch (e) {
            fail++;
          }
        })
      );
      if (fail === 0) {
        toast("已保存全部维度设置", "ok");
      } else {
        toast(`${ok} 个成功，${fail} 个失败`, "error");
      }
    } finally {
      btn.disabled = false;
      btn.textContent = "保存全部";
    }
  }

  document.getElementById("btnSaveAll").onclick = saveAll;
  load();
})();
