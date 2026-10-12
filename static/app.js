/* CTI 통화 대시보드 — 메뉴 1: 대시보드 */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const el = (tag, attrs = {}, ...children) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "style") n.style.cssText = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) if (c != null) n.append(c);
    return n;
  };

  // ---------- 색상 ----------
  const isDark = () => {
    const t = document.documentElement.dataset.theme;
    if (t) return t === "dark";
    return matchMedia("(prefers-color-scheme: dark)").matches;
  };
  // 범주형 슬롯(고정 순서). 색은 상담원 ID 순서에 고정 — 필터로 다시 칠하지 않는다.
  const CAT = {
    light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
    dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
  };
  // 브랜드 블루 순차 램프
  const BLUE = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
    "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"];
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  let agentOrder = []; // 상담원 ID 정렬 목록 → 색 슬롯
  const agentColor = (id) => {
    const i = agentOrder.indexOf(id);
    const pal = CAT[isDark() ? "dark" : "light"];
    return i >= 0 && i < pal.length ? pal[i] : css("--muted");
  };

  /** 히트맵 셀 색: 0 은 비움, 그 외 값/최대값 비율로 램프 단계 선택. */
  const heatColor = (v, max) => {
    if (!v || !max) return null;
    const t = v / max;
    // 라이트: 밝은→진한, 다크: 표면에 가까운 진한 단계→밝은 단계
    const ramp = isDark() ? BLUE.slice(3).reverse() : BLUE;
    const idx = Math.min(ramp.length - 1, Math.floor(t * (ramp.length - 1) + 0.0001));
    const whiteText = isDark() ? idx < ramp.length - 4 : idx >= 7;
    return { bg: ramp[idx], text: whiteText ? "on-dark" : "on-light" };
  };

  // ---------- 포맷 ----------
  const nf = new Intl.NumberFormat("ko-KR");
  const fmtInt = (n) => (n == null ? "–" : nf.format(n));
  const fmtDur = (sec) => {
    if (sec == null) return "–";
    sec = Math.round(sec);
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    const pad = (x) => String(x).padStart(2, "0");
    return h ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
  };
  const fmtDurLong = (sec) => {
    if (sec == null) return "–";
    sec = Math.round(sec);
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
    return h ? `${nf.format(h)}시간 ${m}분` : `${m}분 ${sec % 60}초`;
  };
  const fmtPct = (r, digits = 1) => (r == null ? "–" : `${(r * 100).toFixed(digits)}%`);
  const fmtBytes = (b) => {
    if (b < 1024) return `${b} B`;
    const u = ["KB", "MB", "GB", "TB"]; let i = -1;
    do { b /= 1024; i++; } while (b >= 1024 && i < u.length - 1);
    return `${b.toFixed(1)} ${u[i]}`;
  };
  const DOW = ["일", "월", "화", "수", "목", "금", "토"];
  const shortDate = (iso) => {
    const d = new Date(iso + "T00:00:00");
    return `${d.getMonth() + 1}/${d.getDate()}(${DOW[d.getDay()]})`;
  };
  const isWeekend = (iso) => [0, 6].includes(new Date(iso + "T00:00:00").getDay());

  // ---------- API ----------
  async function api(path, opts = {}) {
    const res = await fetch(path, {
      credentials: "same-origin",
      headers: opts.body ? { "Content-Type": "application/json" } : {},
      ...opts,
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 && path !== "/api/login") { showLogin(); throw new Error(data.error || "로그인이 필요합니다."); }
    if (!res.ok) throw new Error(data.error || `요청 실패 (${res.status})`);
    return data;
  }

  const toast = (msg) => {
    const t = $("#toast"); t.textContent = msg; t.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 3000);
  };

  // ---------- 상태 ----------
  const state = {
    user: null,
    preset: "today",
    start: null,
    end: null,
    agentId: "",
    data: null,
    hiddenSeries: new Set(), // 숨긴 추이 선 (agent id 또는 "total")
    sort: { key: "handled", dir: "desc" },
    drawerAgent: null,
  };
  try {
    const saved = JSON.parse(localStorage.getItem("cti.filters") || "{}");
    if (saved.preset) Object.assign(state, { preset: saved.preset, start: saved.start, end: saved.end, agentId: saved.agentId || "" });
  } catch { /* 저장소 없음 */ }
  const saveFilters = () => {
    try {
      localStorage.setItem("cti.filters", JSON.stringify({ preset: state.preset, start: state.start, end: state.end, agentId: state.agentId }));
    } catch { /* 무시 */ }
  };

  const periodQuery = () => {
    const p = new URLSearchParams({ preset: state.preset });
    if (state.preset === "custom") { p.set("start", state.start); p.set("end", state.end); }
    return p;
  };

  // ---------- 로그인 ----------
  function showLogin() {
    $("#app-view").hidden = true;
    $("#login-view").hidden = false;
    closeDrawer();
  }
  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    $("#login-error").textContent = "";
    try {
      state.user = await api("/api/login", { method: "POST", body: JSON.stringify(Object.fromEntries(f)) });
      e.target.reset();
      await startApp();
    } catch (err) {
      $("#login-error").textContent = err.message;
    }
  });
  $("#logout").addEventListener("click", async () => {
    await api("/api/logout", { method: "POST", body: "{}" }).catch(() => {});
    state.user = null; showLogin();
  });

  async function startApp() {
    $("#login-view").hidden = true;
    $("#app-view").hidden = false;
    $("#user-label").textContent = `${state.user.username} (${state.user.role === "admin" ? "관리자" : "조회"})`;
    const agents = await api("/api/agents");
    agentOrder = agents.map((a) => a.id).sort((a, b) => a - b);
    const sel = $("#agent-filter");
    sel.replaceChildren(el("option", { value: "" }, "전체"),
      ...agents.map((a) => el("option", { value: a.id }, a.name)));
    if (!agents.some((a) => String(a.id) === String(state.agentId))) state.agentId = "";
    sel.value = state.agentId;
    syncFilterUI();
    await load();
  }

  // ---------- 필터 ----------
  const todayIso = () => {
    const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
    return d.toISOString().slice(0, 10);
  };
  function syncFilterUI() {
    document.querySelectorAll(".seg button").forEach((b) => {
      const on = b.dataset.preset === state.preset;
      b.classList.toggle("active", on);
      b.setAttribute("aria-checked", on);
      b.setAttribute("role", "radio");
    });
    $("#custom-range").hidden = state.preset !== "custom";
    $("#start-date").value = state.start || todayIso();
    $("#end-date").value = state.end || todayIso();
  }
  document.querySelectorAll(".seg button").forEach((b) =>
    b.addEventListener("click", () => {
      state.preset = b.dataset.preset;
      if (state.preset === "custom") {
        state.start = state.start || todayIso(); state.end = state.end || todayIso();
        syncFilterUI(); return; // 적용 버튼을 눌러야 조회
      }
      syncFilterUI(); saveFilters(); load();
    }));
  $("#apply-range").addEventListener("click", () => {
    const s = $("#start-date").value, e = $("#end-date").value;
    if (!s || !e) return toast("시작일과 종료일을 선택하세요.");
    [state.start, state.end] = s <= e ? [s, e] : [e, s];
    syncFilterUI(); saveFilters(); load();
  });
  $("#agent-filter").addEventListener("change", (e) => {
    state.agentId = e.target.value; saveFilters(); load();
  });

  // ---------- 로드 ----------
  let loadSeq = 0;
  async function load() {
    const seq = ++loadSeq;
    const q = periodQuery();
    if (state.agentId) q.set("agent_id", state.agentId);
    try {
      const data = await api(`/api/dashboard?${q}`);
      if (seq !== loadSeq) return; // 늦게 도착한 이전 응답 무시
      state.data = data;
      render();
    } catch (err) {
      if (state.user) toast(err.message);
    }
  }

  function render() {
    const d = state.data;
    const p = d.period, pp = d.prev_period;
    const rng = (x) => (x.start === x.end ? x.start : `${x.start} ~ ${x.end}`);
    $("#period-label").textContent = `${rng(p)} · 비교: ${rng(pp)}`;
    renderKpis(d);
    renderTrend(d.daily_trend);
    renderHourly(d.hourly);
    renderMatrix(d.daily_matrix, d.min_call_sec);
    renderPerf(d.agent_performance);
  }

  // ---------- KPI ----------
  function renderKpis(d) {
    const k = d.kpis;
    const min = d.min_call_sec;
    const cards = [
      { key: "total_calls", label: "총 통화 건수", fmt: fmtInt, better: "up" },
      { key: "total_sec", label: "총 통화시간", fmt: fmtDurLong, better: "up" },
      { key: "att_sec", label: "평균 통화시간 (ATT)", fmt: fmtDur, better: null, hint: `${min}초 이상 통화 기준` },
      { key: "customers", label: "고객 수", fmt: fmtInt, better: "up", hint: "중복 제외" },
      { key: "short_ratio", label: "짧은 통화 비율", fmt: fmtPct, better: "down", hint: `${min}초 미만`, pp: true },
    ];
    $("#kpis").replaceChildren(...cards.map((c) => {
      const m = k[c.key];
      return el("div", { class: "kpi" },
        el("div", { class: "label" }, c.label),
        el("div", { class: "value" }, c.fmt(m.value)),
        el("div", { class: "delta" }, deltaNode(m, c), el("span", { class: "muted" }, `직전 ${c.fmt(m.prev)}`)),
        c.hint ? el("div", { class: "hint" }, c.hint) : null);
    }));
  }
  function deltaNode(m, c) {
    if (!m.delta) return el("span", { class: "flat" }, "비교 불가");
    const v = m.delta.abs;
    if (v === 0) return el("span", { class: "flat" }, "— 변동 없음");
    const up = v > 0;
    const arrow = up ? "▲" : "▼";
    let cls = "flat";
    if (c.better) cls = (up === (c.better === "up")) ? (up ? "up-good" : "down-good") : (up ? "up-bad" : "down-bad");
    let text;
    if (c.pp) text = `${arrow} ${Math.abs(v * 100).toFixed(1)}%p`;
    else if (m.delta.pct != null) text = `${arrow} ${Math.abs(m.delta.pct).toFixed(1)}%`;
    else text = `${arrow} ${c.fmt(Math.abs(v))}`;
    return el("span", { class: cls, title: up ? "증가" : "감소" }, text);
  }

  // ---------- 차트 공통 ----------
  const charts = {};
  function baseOptions() {
    const grid = css("--grid"), muted = css("--muted"), axis = css("--axis");
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: css("--ink"), titleColor: css("--surface"), bodyColor: css("--surface"), padding: 10, boxPadding: 4 },
      },
      scales: {
        x: { grid: { display: false }, border: { color: axis }, ticks: { color: muted, font: { size: 11 }, maxRotation: 0, autoSkipPadding: 12 } },
        y: { beginAtZero: true, grid: { color: grid }, border: { display: false }, ticks: { color: muted, font: { size: 11 }, precision: 0 } },
      },
    };
  }
  const upsert = (id, config) => {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(document.getElementById(id), config);
  };

  // ---------- 일별 추이 ----------
  function renderTrend(t) {
    const ink2 = css("--ink-2");
    const series = [
      { id: "total", name: "전체 합계", data: t.total, color: ink2, total: true },
      ...t.series.map((s) => ({ id: s.agent_id, name: s.name, data: s.counts, color: agentColor(s.agent_id) })),
    ];
    // 범례 = 선 토글
    $("#trend-legend").replaceChildren(...series.map((s) => el("button", {
      class: s.total ? "total" : null,
      "aria-pressed": String(!state.hiddenSeries.has(s.id)),
      style: `--c:${s.color}`,
      onclick: () => {
        state.hiddenSeries.has(s.id) ? state.hiddenSeries.delete(s.id) : state.hiddenSeries.add(s.id);
        renderTrend(t);
      },
    }, el("span", { class: "swatch" }), s.name)));

    const opts = baseOptions();
    opts.interaction = { mode: "index", intersect: false };
    opts.plugins.tooltip.callbacks = { title: (items) => shortDate(t.dates[items[0].dataIndex]) };
    const single = t.dates.length === 1;
    upsert("trend-chart", {
      type: "line",
      data: {
        labels: t.dates.map(shortDate),
        datasets: series.filter((s) => !state.hiddenSeries.has(s.id)).map((s) => ({
          label: s.name,
          data: s.data,
          borderColor: s.color,
          backgroundColor: s.color,
          borderWidth: 2,
          borderDash: s.total ? [5, 4] : [],
          pointRadius: single ? 4 : 0,
          pointHoverRadius: 4,
          pointHoverBorderColor: css("--surface"),
          pointHoverBorderWidth: 2,
          cubicInterpolationMode: "monotone",
        })),
      },
      options: opts,
    });
  }

  // ---------- 시간대별 ----------
  function renderHourly(h) {
    const opts = baseOptions();
    opts.plugins.tooltip.callbacks = {
      title: (items) => `${items[0].dataIndex}시 ~ ${items[0].dataIndex + 1}시`,
      label: (item) => ` ${fmtInt(item.raw)}건`,
    };
    upsert("hourly-chart", {
      type: "bar",
      data: {
        labels: h.map((_, i) => String(i)),
        datasets: [{
          label: "통화 건수",
          data: h,
          backgroundColor: css("--brand"),
          borderRadius: { topLeft: 4, topRight: 4 },
          borderSkipped: "bottom",
          categoryPercentage: 0.85,
          barPercentage: 0.9,
        }],
      },
      options: opts,
    });
  }

  // ---------- 히트맵 표 ----------
  function renderMatrix(m, minSec) {
    $("#matrix-note").textContent = `처리건수 = ${minSec}초 이상 통화 · 진할수록 많음`;
    const thead = el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "상담원"),
      m.dates.map((d) => el("th", { scope: "col", class: `date${isWeekend(d) ? " weekend" : ""}`, title: d }, shortDate(d))),
      el("th", { scope: "col", class: "total" }, "합계")));
    const tbody = el("tbody", {}, m.rows.map((r) => el("tr", {},
      el("td", {}, agentButton(r.agent_id, r.name)),
      r.counts.map((v, i) => {
        const c = heatColor(v, m.max_cell);
        return el("td", {
          class: `cell${c ? " " + c.text : ""}`,
          style: c ? `background:${c.bg}` : null,
          title: `${r.name} · ${m.dates[i]} · ${v}건`,
        }, v ? fmtInt(v) : "·");
      }),
      el("td", { class: "total" }, fmtInt(r.total)))));
    const tfoot = el("tfoot", {}, el("tr", {},
      el("td", {}, "합계"),
      m.col_totals.map((v) => el("td", {}, fmtInt(v))),
      el("td", {}, fmtInt(m.grand_total))));
    $("#matrix").replaceChildren(thead, tbody, tfoot);
  }

  const agentButton = (id, name) => el("button", { class: "agent-link", onclick: () => openDrawer(id) }, name);

  // ---------- 상담원별 실적 ----------
  const PERF_COLS = [
    { key: "name", label: "상담원", fmt: null, type: "str" },
    { key: "handled", label: "처리건수", fmt: fmtInt },
    { key: "total_sec", label: "총 통화시간", fmt: fmtDur },
    { key: "att_sec", label: "ATT", fmt: fmtDur },
    { key: "longest_sec", label: "최장 통화", fmt: fmtDur },
  ];
  function renderPerf(rows) {
    const { key, dir } = state.sort;
    const col = PERF_COLS.find((c) => c.key === key);
    const sorted = [...rows].sort((a, b) => {
      const x = a[key], y = b[key];
      if (x == null && y == null) return 0;
      if (x == null) return 1; // 값 없음은 항상 뒤로
      if (y == null) return -1;
      const r = col.type === "str" ? String(x).localeCompare(String(y), "ko") : x - y;
      return dir === "asc" ? r : -r;
    });
    const thead = el("thead", {}, el("tr", {}, PERF_COLS.map((c) => el("th", {
      scope: "col",
      tabindex: "0",
      "aria-sort": c.key === key ? (dir === "asc" ? "ascending" : "descending") : "none",
      onclick: () => setSort(c.key, rows),
      onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSort(c.key, rows); } },
    }, c.label))));
    const tbody = el("tbody", {}, sorted.map((r) => el("tr", {},
      PERF_COLS.map((c) => el("td", {}, c.key === "name" ? agentButton(r.agent_id, r.name) : c.fmt(r[c.key]))))));
    $("#perf").replaceChildren(thead, tbody);
  }
  function setSort(key, rows) {
    const s = state.sort;
    state.sort = { key, dir: s.key === key ? (s.dir === "asc" ? "desc" : "asc") : (key === "name" ? "asc" : "desc") };
    renderPerf(rows);
  }

  // ---------- 드로어 ----------
  async function openDrawer(agentId) {
    state.drawerAgent = agentId;
    const drawer = $("#drawer");
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
    $("#drawer-backdrop").hidden = false;
    $("#drawer-title").textContent = "불러오는 중…";
    $("#backup-msg").textContent = "";
    $("#backup-msg").className = "small";
    try {
      const d = await api(`/api/agents/${agentId}?${periodQuery()}`);
      if (state.drawerAgent !== agentId) return;
      renderDrawer(d);
      $("#drawer-close").focus();
    } catch (err) {
      $("#drawer-title").textContent = "오류";
      toast(err.message);
    }
  }
  function closeDrawer() {
    state.drawerAgent = null;
    $("#drawer").classList.remove("open");
    $("#drawer").setAttribute("aria-hidden", "true");
    $("#drawer-backdrop").hidden = true;
  }
  $("#drawer-close").addEventListener("click", closeDrawer);
  $("#drawer-backdrop").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && state.drawerAgent != null) closeDrawer(); });

  function renderDrawer(d) {
    const a = d.agent;
    $("#drawer-title").textContent = a.extension ? `${a.name} (내선 ${a.extension})` : a.name;

    const opts = baseOptions();
    opts.interaction = { mode: "index", intersect: false };
    opts.plugins.tooltip.callbacks = {
      title: (items) => shortDate(d.trend.dates[items[0].dataIndex]),
      label: (item) => ` 처리 ${fmtInt(item.raw)}건 · ATT ${fmtDur(d.trend.att_sec[item.dataIndex])}`,
    };
    const color = agentColor(a.id);
    upsert("drawer-chart", {
      type: "line",
      data: {
        labels: d.trend.dates.map(shortDate),
        datasets: [{
          label: "처리건수", data: d.trend.handled, borderColor: color, backgroundColor: color,
          borderWidth: 2, pointRadius: d.trend.dates.length === 1 ? 4 : 0, pointHoverRadius: 4, cubicInterpolationMode: "monotone",
        }],
      },
      options: opts,
    });

    $("#recent").replaceChildren(
      el("thead", {}, el("tr", {}, ["일시", "고객번호", "통화시간"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", {}, d.recent_calls.length
        ? d.recent_calls.map((c) => el("tr", {},
          el("td", {}, c.started_at.slice(0, 16)),
          el("td", {}, c.customer_number || "–"),
          el("td", {}, fmtDur(c.duration_sec))))
        : el("tr", {}, el("td", { colspan: "3", class: "muted" }, "통화 기록이 없습니다."))));

    const isAdmin = state.user.role === "admin" && d.sync_folder;
    $("#admin-section").hidden = !isAdmin;
    if (isAdmin) renderAdmin(a, d.sync_folder, d.backups);
  }

  function renderAdmin(agent, folder, backups) {
    const st = $("#sync-status");
    if (folder.error) {
      st.replaceChildren(el("span", { class: "error" }, folder.error));
    } else {
      st.replaceChildren(
        el("div", {}, "경로: ", el("code", {}, folder.path)),
        el("div", {}, folder.exists
          ? `파일 ${fmtInt(folder.file_count)}개 · ${fmtBytes(folder.total_bytes)}`
          : "폴더가 아직 없습니다."));
    }
    const btn = $("#backup-btn");
    btn.disabled = !!folder.error || !folder.file_count;
    btn.onclick = () => runBackup(agent, folder);

    $("#backups").replaceChildren(
      el("thead", {}, el("tr", {}, ["일시", "파일 수", "용량", "실행자", "백업 파일"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", {}, backups.length
        ? backups.map((b) => el("tr", {},
          el("td", {}, b.created_at.slice(0, 16)),
          el("td", {}, fmtInt(b.file_count)),
          el("td", {}, fmtBytes(b.total_bytes)),
          el("td", {}, b.performed_by),
          el("td", { title: b.archive_path }, b.archive_path.split(/[\\/]/).pop())))
        : el("tr", {}, el("td", { colspan: "5", class: "muted" }, "백업 이력이 없습니다."))));
  }

  async function runBackup(agent, folder) {
    const ok = confirm(`${agent.name} 상담원의 동기화 폴더 파일 ${folder.file_count}개를 백업한 뒤 폴더를 비웁니다.\n\n${folder.path}\n\n계속할까요?`);
    if (!ok) return;
    const btn = $("#backup-btn"), msg = $("#backup-msg");
    btn.disabled = true;
    msg.className = "small"; msg.textContent = "백업 중…";
    try {
      const r = await api(`/api/agents/${agent.id}/backup`, { method: "POST", body: "{}" });
      msg.className = "small ok";
      msg.textContent = `완료: ${fmtInt(r.backup.file_count)}개 파일(${fmtBytes(r.backup.total_bytes)})을 백업하고 폴더를 비웠습니다.`;
      if (state.drawerAgent === agent.id) renderAdmin(agent, r.sync_folder, r.backups);
    } catch (err) {
      msg.className = "small err"; msg.textContent = err.message;
      btn.disabled = false;
    }
  }

  // 테마 변경 시 색 다시 그리기
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => state.data && render());

  // ---------- 시작 ----------
  api("/api/me").then((u) => { state.user = u; return startApp(); }).catch(() => showLogin());
})();
