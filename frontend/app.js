const API = {
  skills: "/api/skills",
  normalize: "/api/normalize",
  normalizeMany: "/api/normalize-many",
};

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function badgeClass(matchType) {
  return matchType === "exact"
    ? "exact"
    : matchType === "semantic"
    ? "semantic"
    : matchType === "review"
    ? "review"
    : "unknown";
}

function badgeText(matchType) {
  return matchType === "exact"
    ? "精确匹配"
    : matchType === "semantic"
    ? "语义匹配"
    : matchType === "review"
    ? "待审核"
    : "未知";
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`请求失败 (${res.status}): ${text}`);
  }
  return res.json();
}

async function getJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`请求失败 (${res.status}): ${text}`);
  }
  return res.json();
}

function renderSingleResult(result) {
  const normalized = result.normalized
    ? `<div class="meta-item">
        <div class="meta-label">标准技能</div>
        <div class="meta-value">${escapeHtml(result.normalized.canonical_name)}</div>
      </div>
      <div class="meta-item">
        <div class="meta-label">Skill ID</div>
        <div class="meta-value">${escapeHtml(result.normalized.skill_id)}</div>
      </div>`
    : `<div class="meta-item">
        <div class="meta-label">标准技能</div>
        <div class="meta-value" style="color:var(--text-secondary)">-</div>
      </div>
      <div class="meta-item">
        <div class="meta-label">Skill ID</div>
        <div class="meta-value" style="color:var(--text-secondary)">-</div>
      </div>`;

  const score = result.score != null ? (result.score * 100).toFixed(1) + "%" : "-";

  let candidatesHtml = "";
  if (result.candidates && result.candidates.length > 0) {
    const list = result.candidates
      .map(
        (c) => `
      <div class="candidate">
        <span class="candidate-name">${escapeHtml(c.name)}</span>
        <span class="candidate-score">${(c.score * 100).toFixed(1)}%</span>
      </div>`
      )
      .join("");
    candidatesHtml = `
      <div class="candidates">
        <h4>Top 候选</h4>
        <div class="candidate-list">${list}</div>
      </div>`;
  }

  return `
    <div class="result-card">
      <div class="result-header">
        <span class="result-title">${escapeHtml(result.raw_text)}</span>
        <span class="badge ${badgeClass(result.match_type)}">${badgeText(result.match_type)}</span>
      </div>
      <div class="result-meta">
        ${normalized}
        <div class="meta-item">
          <div class="meta-label">置信度</div>
          <div class="meta-value">${score}</div>
        </div>
        <div class="meta-item">
          <div class="meta-label">需要审核</div>
          <div class="meta-value">${result.needs_review ? "是" : "否"}</div>
        </div>
      </div>
      ${candidatesHtml}
    </div>`;
}

function renderBatchResults(results) {
  if (results.length === 0) {
    return '<p class="empty">没有可标准化的内容。</p>';
  }
  const rows = results
    .map((r) => {
      const normalized = r.normalized
        ? escapeHtml(r.normalized.canonical_name)
        : '<span style="color:var(--text-secondary)">-</span>';
      const score = r.score != null ? (r.score * 100).toFixed(1) + "%" : "-";
      return `
        <tr>
          <td>${escapeHtml(r.raw_text)}</td>
          <td>${normalized}</td>
          <td><span class="badge ${badgeClass(r.match_type)}">${badgeText(r.match_type)}</span></td>
          <td>${score}</td>
          <td>${r.needs_review ? "是" : "否"}</td>
        </tr>`;
    })
    .join("");

  return `
    <table class="results-table">
      <thead>
        <tr>
          <th>原始表达</th>
          <th>标准技能</th>
          <th>匹配类型</th>
          <th>置信度</th>
          <th>需审核</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderSkillItem(skill) {
  const aliases = skill.aliases && skill.aliases.length > 0
    ? `<div class="aliases">${skill.aliases.map((a) => `<span class="alias-tag">${escapeHtml(a)}</span>`).join("")}</div>`
    : "";
  const description = skill.description
    ? `<div class="skill-description">${escapeHtml(skill.description)}</div>`
    : "";
  const category = skill.category
    ? `<span class="alias-tag">${escapeHtml(skill.category)}</span>`
    : "";

  return `
    <div class="skill-item">
      <div class="skill-name">${escapeHtml(skill.name)} ${category}</div>
      <div class="skill-id">${escapeHtml(skill.id)}</div>
      ${description}
      ${aliases}
    </div>`;
}

// Tabs
const tabs = document.querySelectorAll(".tab");
const panels = document.querySelectorAll(".panel");

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    const target = tab.dataset.tab;
    tabs.forEach((t) => {
      t.classList.remove("active");
      t.setAttribute("aria-selected", "false");
    });
    panels.forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    tab.setAttribute("aria-selected", "true");
    $(target).classList.add("active");
  });
});

// Single normalize
$("single-btn").addEventListener("click", async () => {
  const input = $("single-input");
  const text = input.value.trim();
  const resultArea = $("single-result");
  if (!text) {
    resultArea.innerHTML = '<p class="empty">请输入一个技能表达。</p>';
    return;
  }

  const btn = $("single-btn");
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>处理中';

  try {
    const data = await postJson(API.normalize, { text });
    resultArea.innerHTML = renderSingleResult(data);
  } catch (err) {
    resultArea.innerHTML = `<div class="error">${escapeHtml(err.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalText;
  }
});

$("single-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    $("single-btn").click();
  }
});

// Batch normalize
$("batch-btn").addEventListener("click", async () => {
  const textarea = $("batch-input");
  const texts = textarea.value
    .split("\n")
    .map((t) => t.trim())
    .filter((t) => t.length > 0);
  const resultArea = $("batch-result");

  if (texts.length === 0) {
    resultArea.innerHTML = '<p class="empty">请输入至少一个技能表达。</p>';
    return;
  }

  const btn = $("batch-btn");
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>处理中';

  try {
    const data = await postJson(API.normalizeMany, { texts });
    resultArea.innerHTML = renderBatchResults(data);
  } catch (err) {
    resultArea.innerHTML = `<div class="error">${escapeHtml(err.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalText;
  }
});

$("batch-clear").addEventListener("click", () => {
  $("batch-input").value = "";
  $("batch-result").innerHTML = "";
});

// Taxonomy
let allSkills = [];

async function loadTaxonomy() {
  const list = $("taxonomy-list");
  const count = $("taxonomy-count");
  try {
    allSkills = await getJson(API.skills);
    count.textContent = `共 ${allSkills.length} 项`;
    renderTaxonomy(allSkills);
  } catch (err) {
    list.innerHTML = `<div class="error">${escapeHtml(err.message)}</div>`;
  }
}

function renderTaxonomy(skills) {
  const list = $("taxonomy-list");
  if (skills.length === 0) {
    list.innerHTML = '<p class="empty">没有匹配的技能。</p>';
    return;
  }
  list.innerHTML = skills.map(renderSkillItem).join("");
}

$("taxonomy-search").addEventListener("input", (e) => {
  const q = e.target.value.trim().toLowerCase();
  if (!q) {
    renderTaxonomy(allSkills);
    return;
  }
  const filtered = allSkills.filter(
    (s) =>
      s.name.toLowerCase().includes(q) ||
      s.id.toLowerCase().includes(q) ||
      (s.aliases || []).some((a) => a.toLowerCase().includes(q))
  );
  renderTaxonomy(filtered);
});

loadTaxonomy();
