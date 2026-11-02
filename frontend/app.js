/* AI 절약 코치 - 바닐라 JS 프론트엔드 (ES 모듈) */
(() => {
  "use strict";

  const API = ((window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL) || "http://127.0.0.1:8000").replace(/\/+$/, "");
  const $ = (sel) => document.querySelector(sel);
  const won = (n) => `${Math.round(n).toLocaleString("ko-KR")}원`;
  const manwon = (n) => (n >= 10000 ? `${(n / 10000).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}만원` : won(n));

  let Auth = null; // auth.js 모듈 (Firebase). init에서 동적으로 불러온다.

  const state = {
    user: null, // GET /api/me 응답
    conversationId: null,
    sending: false,
    summary: null,
    donutMonth: null,
    dataRows: [],
  };

  // ---------------------------------------------------------------- API
  class ApiError extends Error {
    constructor(message, status) { super(message); this.status = status; }
  }

  async function api(path, { method = "GET", body, timeout = 20000, auth = true } = {}) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    try {
      const headers = {};
      if (body) headers["Content-Type"] = "application/json";
      if (auth && Auth) {
        const token = await Auth.getIdToken();
        if (token) headers["Authorization"] = `Bearer ${token}`;
      }
      const res = await fetch(API + path, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
        signal: ctrl.signal,
      });
      if (res.status === 204) return null;
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        const err = new ApiError(errorMessage(data, res.status), res.status);
        if (res.status === 401) handleUnauthorized(err.message);
        if (res.status === 403 && data && data.detail === "consent_required") {
          err.message = "개인정보 동의가 필요해요.";
          showConsent();
        }
        throw err;
      }
      return data;
    } catch (e) {
      if (e instanceof ApiError) throw e;
      if (e.name === "AbortError") throw new ApiError("서버 응답이 너무 늦어요. 잠시 후 다시 시도해 주세요.", 0);
      throw new ApiError("서버에 연결할 수 없어요. 서버 주소와 실행 상태를 확인해 주세요.", 0);
    } finally {
      clearTimeout(timer);
    }
  }

  function errorMessage(data, status) {
    const d = data && data.detail;
    if (Array.isArray(d)) {
      // Pydantic 422 검증 오류
      return d.map((x) => `${(x.loc || []).slice(1).join(".") || "입력"}: ${x.msg}`).join(" / ");
    }
    if (typeof d === "string") return d;
    return `요청 실패 (HTTP ${status})`;
  }

  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.add("hidden"), 2600);
  }

  // ---------------------------------------------------------------- 서버 깨우기 (Render 무료 티어 콜드스타트)
  async function warmUp() {
    const status = $("#serverStatus");
    const banner = $("#coldStartBanner");
    const slow = setTimeout(() => {
      banner.classList.remove("hidden");
      status.textContent = "서버 깨우는 중…";
    }, 3000);
    try {
      await api("/health", { timeout: 90000, auth: false });
      status.textContent = "서버 연결됨";
      status.className = "status status-ok";
      return true;
    } catch (e) {
      status.textContent = "서버 연결 실패";
      status.className = "status status-error";
      toast(e.message);
      return false;
    } finally {
      clearTimeout(slow);
      banner.classList.add("hidden");
    }
  }

  // ---------------------------------------------------------------- 테마
  function initTheme() {
    let saved = null;
    try { saved = localStorage.getItem("theme"); } catch (_) { /* 저장소 사용 불가 */ }
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    applyTheme(saved || (prefersDark ? "dark" : "light"));
    $("#themeToggle").addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      applyTheme(next);
      try { localStorage.setItem("theme", next); } catch (_) { /* noop */ }
    });
  }
  function applyTheme(t) {
    document.documentElement.dataset.theme = t;
    $("#themeToggle").textContent = t === "dark" ? "☀️" : "🌙";
  }

  // ---------------------------------------------------------------- 탭
  function initTabs() {
    document.querySelectorAll(".tab").forEach((btn) =>
      btn.addEventListener("click", () => showTab(btn.dataset.tab))
    );
  }
  function showTab(name) {
    document.querySelectorAll(".tab").forEach((b) => {
      const on = b.dataset.tab === name;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on);
    });
    $("#tab-chat").classList.toggle("hidden", name !== "chat");
    $("#tab-data").classList.toggle("hidden", name !== "data");
  }

  // ---------------------------------------------------------------- 채팅
  const messagesEl = () => $("#chatMessages");

  function clearMessages() {
    messagesEl().innerHTML = "";
  }

  function showWelcome() {
    messagesEl().innerHTML = `
      <div class="welcome">
        <p class="welcome-title">무엇이 궁금하세요?</p>
        <div class="chips">
          <button class="chip" type="button">이번 달 지출 어때?</button>
          <button class="chip" type="button">가장 많이 쓴 때는 언제야?</button>
          <button class="chip" type="button">식비를 줄이려면 어떻게 해야 할까?</button>
          <button class="chip" type="button">월별 지출 추세를 분석해줘</button>
        </div>
      </div>`;
  }

  function addMessage(role, text) {
    const welcome = messagesEl().querySelector(".welcome");
    if (welcome) welcome.remove();
    const el = document.createElement("div");
    el.className = `msg ${role}`;
    el.textContent = text; // textContent: 사용자 입력/AI 응답을 HTML로 해석하지 않음 (XSS 방지)
    if (role === "assistant") {
      const tag = document.createElement("span");
      tag.className = "ai-tag";
      tag.textContent = "AI 생성 답변 · 참고용";
      el.appendChild(tag);
    }
    messagesEl().appendChild(el);
    messagesEl().scrollTop = messagesEl().scrollHeight;
    return el;
  }

  function addTyping() {
    const el = document.createElement("div");
    el.className = "msg assistant";
    el.innerHTML = '<span class="typing"><span></span><span></span><span></span></span><span class="typing-label">지출 데이터를 분석하는 중…</span>';
    messagesEl().appendChild(el);
    messagesEl().scrollTop = messagesEl().scrollHeight;
    return el;
  }

  async function sendMessage(text) {
    text = text.trim();
    if (!text || state.sending) return;
    state.sending = true;
    $("#chatSend").disabled = true;
    $("#chatInput").value = "";
    autoGrow();

    addMessage("user", text);
    const typing = addTyping();
    try {
      const res = await api("/api/chat", {
        method: "POST",
        body: { message: text, conversation_id: state.conversationId },
        timeout: 90000, // 콜드스타트 + GPT 응답 시간 고려
      });
      typing.remove();
      addMessage("assistant", res.reply);
      const isNew = !state.conversationId;
      state.conversationId = res.conversation_id;
      if (res.summary) renderSummary(res.summary);
      await loadConversations();
      if (typeof res.remaining_today === "number" && res.remaining_today <= 5) {
        toast(`오늘 남은 채팅: ${res.remaining_today}회`);
      } else if (isNew) {
        toast("대화가 자동 저장되었어요.");
      }
    } catch (e) {
      typing.remove();
      addMessage("error", `⚠ ${e.message}`);
    } finally {
      state.sending = false;
      $("#chatSend").disabled = false;
      $("#chatInput").focus();
    }
  }

  function autoGrow() {
    const ta = $("#chatInput");
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 140) + "px";
  }

  function initChat() {
    $("#chatForm").addEventListener("submit", (e) => {
      e.preventDefault();
      sendMessage($("#chatInput").value);
    });
    $("#chatInput").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        sendMessage($("#chatInput").value);
      }
    });
    $("#chatInput").addEventListener("input", autoGrow);
    messagesEl().addEventListener("click", (e) => {
      const chip = e.target.closest(".chip");
      if (chip) sendMessage(chip.textContent);
    });
    $("#newChatBtn").addEventListener("click", () => {
      state.conversationId = null;
      showWelcome();
      markActiveConversation();
      showTab("chat");
      $("#chatInput").focus();
    });
  }

  // ---------------------------------------------------------------- 대화 기록
  function formatTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d)) return "";
    return d.toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  async function loadConversations() {
    try {
      const list = await api("/api/conversations");
      renderConversations(list);
    } catch (e) {
      toast(`대화 목록: ${e.message}`);
    }
  }

  function renderConversations(list) {
    const ul = $("#conversationList");
    ul.innerHTML = "";
    $("#conversationEmpty").classList.toggle("hidden", list.length > 0);
    for (const c of list) {
      const li = document.createElement("li");
      li.className = "conv-item";
      li.dataset.id = c.id;
      li.tabIndex = 0;

      const text = document.createElement("div");
      text.className = "conv-text";
      const title = document.createElement("div");
      title.className = "conv-title";
      title.textContent = c.title || "제목 없음";
      const meta = document.createElement("div");
      meta.className = "conv-meta";
      meta.textContent = `${formatTime(c.updated_at)} · 메시지 ${c.message_count}개`;
      text.append(title, meta);

      const del = document.createElement("button");
      del.className = "link-btn danger";
      del.type = "button";
      del.textContent = "삭제";
      del.setAttribute("aria-label", `${c.title} 대화 삭제`);
      del.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteConversation(c.id);
      });

      li.append(text, del);
      li.addEventListener("click", () => openConversation(c.id));
      li.addEventListener("keydown", (e) => { if (e.key === "Enter") openConversation(c.id); });
      ul.appendChild(li);
    }
    markActiveConversation();
  }

  function markActiveConversation() {
    document.querySelectorAll(".conv-item").forEach((li) =>
      li.classList.toggle("active", li.dataset.id === state.conversationId)
    );
  }

  async function openConversation(id) {
    showTab("chat");
    clearMessages();
    const loading = addTyping();
    loading.querySelector(".typing-label").textContent = "대화를 불러오는 중…";
    try {
      const conv = await api(`/api/conversations/${encodeURIComponent(id)}`);
      loading.remove();
      state.conversationId = conv.id;
      conv.messages.forEach((m) => addMessage(m.role, m.content));
      markActiveConversation();
    } catch (e) {
      loading.remove();
      addMessage("error", `⚠ ${e.message}`);
    }
  }

  async function deleteConversation(id) {
    if (!confirm("이 대화를 삭제할까요?")) return;
    try {
      await api(`/api/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
      if (state.conversationId === id) {
        state.conversationId = null;
        showWelcome();
      }
      toast("대화를 삭제했어요.");
      loadConversations();
    } catch (e) {
      toast(e.message);
    }
  }

  // ---------------------------------------------------------------- 거래 관리

  function monthRange(ym) {
    const [y, m] = ym.split("-").map(Number);
    const last = new Date(y, m, 0).getDate();
    return { start: `${ym}-01`, end: `${ym}-${String(last).padStart(2, "0")}` };
  }

  async function loadCategories() {
    try {
      const cats = await api("/api/transactions/categories", { auth: false });
      const sel = $("#txCategory");
      sel.innerHTML = "";
      for (const c of cats) {
        const o = document.createElement("option");
        o.value = o.textContent = c;
        sel.appendChild(o);
      }
    } catch (_) { /* 기본 옵션 유지 */ }
  }

  async function loadData() {
    const ym = $("#dataMonth").value;
    const q = ym ? `?start=${monthRange(ym).start}&end=${monthRange(ym).end}&order=desc` : "?order=desc&limit=100";
    const tbody = $("#dataTableBody");
    tbody.innerHTML = '<tr><td colspan="5" class="muted">불러오는 중…</td></tr>';
    try {
      state.dataRows = await api(`/api/transactions${q}`);
      renderDataTable();
    } catch (e) {
      tbody.innerHTML = "";
      setFormMessage(e.message, "err");
    }
  }

  function cell(text, cls) {
    const td = document.createElement("td");
    if (cls) td.className = cls;
    td.textContent = text;
    return td;
  }

  function renderDataTable() {
    const tbody = $("#dataTableBody");
    tbody.innerHTML = "";
    const rows = state.dataRows;
    const total = rows.reduce((s, r) => s + r.amount, 0);
    $("#dataCount").textContent = `${rows.length}건 · 합계 ${won(total)}`;
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="muted">이 기간에 거래가 없어요.</td></tr>';
      return;
    }
    const editingId = $("#dataId").value;
    for (const r of rows) {
      const tr = document.createElement("tr");
      if (r.id === editingId) tr.classList.add("editing");

      const tdMerchant = cell(r.merchant);
      if (r.memo) tdMerchant.title = r.memo;
      const icon = SOURCE_ICON[r.source];
      if (icon) {
        const span = document.createElement("span");
        span.className = "src-icon";
        span.textContent = icon[0];
        span.title = icon[1];
        span.setAttribute("aria-label", icon[1]);
        tdMerchant.appendChild(span);
      }
      const tdCat = document.createElement("td");
      const tag = document.createElement("span");
      tag.className = "cat-tag";
      tag.textContent = r.category;
      tdCat.appendChild(tag);

      const tdAct = document.createElement("td");
      tdAct.className = "actions";
      const edit = document.createElement("button");
      edit.className = "link-btn";
      edit.type = "button";
      edit.textContent = "수정";
      edit.addEventListener("click", () => startEdit(r));
      const del = document.createElement("button");
      del.className = "link-btn danger";
      del.type = "button";
      del.textContent = "삭제";
      del.addEventListener("click", () => deleteData(r));
      tdAct.append(edit, del);

      tr.append(cell(r.date), tdMerchant, tdCat, cell(won(r.amount), "num"), tdAct);
      tbody.appendChild(tr);
    }
  }

  function setFormMessage(msg, kind) {
    const el = $("#dataMessage");
    el.textContent = msg;
    el.className = `form-msg ${kind || ""}`;
  }

  function startEdit(r) {
    $("#dataId").value = r.id;
    $("#txDate").value = r.date;
    $("#txAmount").value = r.amount;
    $("#txMerchant").value = r.merchant;
    const sel = $("#txCategory");
    sel.value = [...sel.options].some((o) => o.value === r.category) ? r.category : "기타";
    $("#txMemo").value = r.memo || "";
    $(".manual-add").open = true;
    $("#dataSubmit").textContent = "수정 저장";
    $("#dataCancel").classList.remove("hidden");
    setFormMessage(`${r.date} ${r.merchant} ${won(r.amount)} 항목을 수정 중이에요.`, "");
    renderDataTable();
    $("#txAmount").focus();
  }

  function resetForm() {
    $("#dataId").value = "";
    $("#txAmount").value = "";
    $("#txMerchant").value = "";
    $("#txMemo").value = "";
    $("#dataSubmit").textContent = "추가";
    $("#dataCancel").classList.add("hidden");
    renderDataTable();
  }

  async function submitData(e) {
    e.preventDefault();
    const id = $("#dataId").value;
    const date = $("#txDate").value;
    const amount = Number($("#txAmount").value);
    const merchant = $("#txMerchant").value.trim();
    if (!date) return setFormMessage("날짜를 입력해 주세요.", "err");
    if (!Number.isInteger(amount) || amount <= 0 || amount > 100000000) {
      return setFormMessage("금액은 1원 ~ 1억 원 사이의 정수여야 해요.", "err");
    }
    if (!merchant) return setFormMessage("가맹점을 입력해 주세요.", "err");
    const body = { date, amount, merchant, category: $("#txCategory").value, memo: $("#txMemo").value.trim() };

    const btn = $("#dataSubmit");
    btn.disabled = true;
    try {
      if (id) {
        await api(`/api/transactions/${encodeURIComponent(id)}`, { method: "PUT", body });
        setFormMessage(`✓ 수정했어요: ${date} ${merchant} ${won(amount)}`, "ok");
      } else {
        await api("/api/transactions", { method: "POST", body });
        setFormMessage(`✓ 추가했어요: ${date} ${merchant} ${won(amount)}`, "ok");
      }
      $("#dataMonth").value = date.slice(0, 7);
      resetForm();
      await Promise.all([loadData(), loadSummary()]);
    } catch (err) {
      setFormMessage(err.message, "err");
    } finally {
      btn.disabled = false;
    }
  }

  async function deleteData(r) {
    if (!confirm(`${r.date} ${r.merchant} ${won(r.amount)} 항목을 삭제할까요?`)) return;
    try {
      await api(`/api/transactions/${encodeURIComponent(r.id)}`, { method: "DELETE" });
      if ($("#dataId").value === r.id) resetForm();
      setFormMessage(`✓ 삭제했어요: ${r.date} ${r.merchant} ${won(r.amount)}`, "ok");
      await Promise.all([loadData(), loadSummary()]);
    } catch (e) {
      setFormMessage(e.message, "err");
    }
  }

  async function exportCsv() {
    try {
      const rows = await api("/api/transactions?order=asc", { timeout: 60000 });
      const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
      const lines = [
        "date,amount,merchant,category,source,memo",
        ...rows.map((r) => [r.date, r.amount, esc(r.merchant), esc(r.category), r.source, esc(r.memo)].join(",")),
      ];
      // BOM: 엑셀에서 한글이 깨지지 않도록
      const blob = new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `transactions_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      toast(`${rows.length}건을 CSV로 내보냈어요.`);
    } catch (e) {
      toast(e.message);
    }
  }

  function initData() {
    $("#dataForm").addEventListener("submit", submitData);
    $("#dataCancel").addEventListener("click", () => { resetForm(); setFormMessage("", ""); });
    $("#dataMonth").addEventListener("change", loadData);
    $("#exportCsv").addEventListener("click", exportCsv);
    $("#txDate").value = new Date().toISOString().slice(0, 10);
    loadCategories();
  }

  // ---------------------------------------------------------------- 이미지 인식 (카드 내역 캡처 · 영수증)
  const upload = { items: [], busy: false };
  const SOURCE_ICON = {
    screenshot: ["📷", "카드 내역 캡처에서 인식"],
    receipt: ["🧾", "영수증 사진에서 인식"],
  };

  // 백엔드 norm_merchant와 같은 규칙: 이미지끼리 겹치는 거래(스크롤 캡처) 찾기용
  const normMerchant = (s) => (s || "").toLowerCase().replace(/\(주\)|㈜|주식회사|\s+|[·.\-_/()]/g, "");

  /** 이미지를 브라우저에서 줄여 JPEG data URL로 (전송량·AI 비용 절감, 원본은 서버로 보내지 않음) */
  function resizeImage(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        // 세로로 긴 캡처는 글씨가 작아지지 않게 폭 기준, 사진은 긴 변 기준으로 축소
        const scale = Math.min(1, 1280 / img.width, 2800 / img.height);
        const w = Math.round(img.width * scale), h = Math.round(img.height * scale);
        const canvas = document.createElement("canvas");
        canvas.width = w; canvas.height = h;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, w, h);
        ctx.drawImage(img, 0, 0, w, h);
        URL.revokeObjectURL(url);
        resolve(canvas.toDataURL("image/jpeg", 0.85));
      };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("이미지를 열 수 없어요. (HEIC 등은 JPG/PNG로 바꿔 주세요)")); };
      img.src = url;
    });
  }

  function openUploadModal() {
    $("#uploadProgress").innerHTML = "";
    $("#reviewSection").classList.add("hidden");
    $("#reviewBody").innerHTML = "";
    $("#reviewCount").textContent = "";
    $("#reviewSave").disabled = true;
    $("#uploadModal").classList.remove("hidden");
  }
  function closeUploadModal() {
    if (upload.busy) return;
    $("#uploadModal").classList.add("hidden");
    upload.items = [];
  }

  async function handleFiles(fileList) {
    const files = [...fileList].filter((f) => f.type.startsWith("image/") || /\.(jpe?g|png|webp|heic)$/i.test(f.name));
    if (!files.length) return;
    if (files.length > 10) { toast("한 번에 최대 10장까지 올릴 수 있어요."); return; }
    openUploadModal();
    upload.busy = true;
    upload.items = [];
    const rows = files.map((f) => {
      const li = document.createElement("li");
      const thumb = document.createElement("img");
      thumb.src = URL.createObjectURL(f);
      thumb.alt = "";
      const name = document.createElement("span");
      name.textContent = f.name;
      const st = document.createElement("span");
      st.className = "state";
      st.textContent = "대기 중";
      li.append(thumb, name, st);
      $("#uploadProgress").appendChild(li);
      return st;
    });

    for (let i = 0; i < files.length; i++) {
      const st = rows[i];
      st.textContent = "AI가 읽는 중…";
      try {
        const dataUrl = await resizeImage(files[i]);
        const res = await api("/api/uploads/extract", { method: "POST", body: { data_url: dataUrl }, timeout: 90000 });
        const source = res.image_type === "receipt" ? "receipt" : "screenshot";
        const kind = { receipt: "영수증", transaction_detail: "거래 상세", card_statement: "거래 내역" }[res.image_type] || "거래 내역";
        if (res.image_type === "other" || !res.items.length) {
          st.className = "state err";
          st.textContent = "거래 내역을 찾지 못했어요 (거래 목록·상세 화면이나 영수증인지 확인해 주세요)";
        } else {
          st.className = "state ok";
          st.textContent = `✓ ${kind} ${res.items.length}건`;
          res.items.forEach((it) => upload.items.push({ ...it, source, notes: [...it.notes] }));
        }
      } catch (e) {
        st.className = "state err";
        st.textContent = `✗ ${e.message}`;
        if (e.status === 429) break; // 한도 초과면 나머지도 실패하므로 중단
      }
    }
    markCrossImageDuplicates();
    upload.busy = false;
    renderReview();
  }

  /** 겹치게 찍은 캡처끼리 같은 거래 → 뒤쪽 것을 중복 표시 */
  function markCrossImageDuplicates() {
    const seen = new Set();
    for (const it of upload.items) {
      const key = `${it.date}|${it.amount}|${normMerchant(it.merchant)}`;
      if (it.date && seen.has(key) && !it.duplicate) {
        it.duplicate = true;
        it.include = false;
        it.notes.push("다른 이미지와 겹쳐요.");
      }
      seen.add(key);
    }
  }

  function categoryOptions(selected) {
    const sel = document.createElement("select");
    for (const o of $("#txCategory").options) {
      const opt = document.createElement("option");
      opt.value = opt.textContent = o.value;
      if (o.value === selected) opt.selected = true;
      sel.appendChild(opt);
    }
    return sel;
  }

  function renderReview() {
    const body = $("#reviewBody");
    body.innerHTML = "";
    if (!upload.items.length) {
      $("#reviewSection").classList.add("hidden");
      updateReviewCount();
      return;
    }
    $("#reviewSection").classList.remove("hidden");
    upload.items.forEach((it) => body.appendChild(reviewRow(it)));
    $("#reviewAll").checked = upload.items.every((i) => i.include);
    updateReviewCount();
  }

  function reviewRow(it) {
      const tr = document.createElement("tr");
      const warn = it.low_confidence || !it.date || it.notes.length > 0;
      tr.classList.toggle("warn", warn && it.include);
      tr.classList.toggle("excluded", !it.include);

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = it.include;
      cb.setAttribute("aria-label", `${it.merchant} 저장`);
      cb.addEventListener("change", () => { it.include = cb.checked; tr.classList.toggle("excluded", !it.include); tr.classList.toggle("warn", warn && it.include); updateReviewCount(); });

      const date = document.createElement("input");
      date.type = "date"; date.value = it.date || "";
      date.addEventListener("change", () => { it.date = date.value || null; updateReviewCount(); });
      const merchant = document.createElement("input");
      merchant.type = "text"; merchant.maxLength = 100; merchant.value = it.merchant;
      merchant.addEventListener("input", () => { it.merchant = merchant.value; });
      const amount = document.createElement("input");
      amount.type = "number"; amount.min = 1; amount.step = 1; amount.value = it.amount;
      amount.addEventListener("input", () => { it.amount = Number(amount.value); });
      const cat = categoryOptions(it.category);
      cat.addEventListener("change", () => { it.category = cat.value; it.category_by = "user"; });

      const notes = document.createElement("td");
      const srcBadge = document.createElement("span");
      srcBadge.className = "badge info";
      srcBadge.textContent = it.source === "receipt" ? "영수증" : "캡처";
      notes.appendChild(srcBadge);
      for (const n of it.notes) {
        const b = document.createElement("span");
        b.className = "badge warn";
        b.textContent = n;
        notes.appendChild(b);
      }

      const td = (el, cls) => { const c = document.createElement("td"); if (cls) c.className = cls; c.appendChild(el); return c; };
      tr.append(td(cb), td(date, "c-date"), td(merchant, "c-merchant"), td(amount, "c-amount"), td(cat, "c-cat"), notes);
      return tr;
  }


  function updateReviewCount() {
    const sel = upload.items.filter((i) => i.include);
    const total = sel.reduce((s, i) => s + (Number(i.amount) || 0), 0);
    $("#reviewCount").textContent = upload.items.length
      ? `${upload.items.length}건 인식 · ${sel.length}건 선택 · ${won(total)}`
      : "";
    $("#reviewSave").disabled = upload.busy || sel.length === 0;
    $("#reviewSave").textContent = sel.length ? `${sel.length}건 저장` : "저장";
  }

  async function saveReview() {
    const sel = upload.items.filter((i) => i.include);
    for (const it of sel) {
      const bad = !it.date ? "날짜" : !(Number.isInteger(it.amount) && it.amount > 0 && it.amount <= 100000000) ? "금액" : !it.merchant.trim() ? "가맹점" : null;
      if (bad) { toast(`${it.merchant || "이름 없는 거래"}: ${bad}을(를) 확인해 주세요.`); return; }
    }
    const btn = $("#reviewSave");
    btn.disabled = true;
    try {
      const items = sel.map((i) => ({
        date: i.date, amount: i.amount, merchant: i.merchant.trim(), category: i.category,
        source: i.source, category_by: i.category_by,
      }));
      const r = await api("/api/transactions/bulk", { method: "POST", body: { items }, timeout: 60000 });
      upload.items = [];
      $("#uploadModal").classList.add("hidden");
      toast(`${r.created}건을 저장했어요.`);
      const latest = sel.map((i) => i.date).sort().at(-1);
      if (latest) $("#dataMonth").value = latest.slice(0, 7);
      await Promise.all([loadData(), loadSummary()]);
    } catch (e) {
      toast(e.message);
      btn.disabled = false;
    }
  }

  function initUpload() {
    const input = $("#uploadInput");
    input.addEventListener("change", () => { handleFiles(input.files); input.value = ""; });
    $("#uploadClose").addEventListener("click", closeUploadModal);
    $("#uploadCancel").addEventListener("click", closeUploadModal);
    $("#reviewSave").addEventListener("click", saveReview);
    $("#reviewAll").addEventListener("change", (e) => {
      upload.items.forEach((i) => { i.include = e.target.checked; });
      renderReview();
    });
    // 지출 내역 탭에 이미지를 끌어다 놓아도 업로드
    const zone = $("#tab-data");
    zone.addEventListener("dragover", (e) => { e.preventDefault(); });
    zone.addEventListener("drop", (e) => { e.preventDefault(); if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files); });
  }

  // ---------------------------------------------------------------- 월 절약 목표
  const goalState = { view: null, month: null };

  function kstMonth() {
    const now = new Date(Date.now() + 9 * 3600 * 1000);
    return now.toISOString().slice(0, 7);
  }
  const monthLabel = (ym) => `${Number(ym.slice(5))}월`;

  async function loadGoal() {
    goalState.month = kstMonth();
    try {
      goalState.view = await api(`/api/goals/${goalState.month}`);
    } catch (e) {
      goalState.view = null;
    }
    renderGoalCard();
  }

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function goalBar(used, budget, status, paceRatio, small) {
    const bar = el("div", `goal-bar ${status}${small ? " small" : ""}`);
    const fill = el("div", "fill");
    fill.style.width = `${Math.min(100, budget ? (used / budget) * 100 : 0)}%`;
    bar.appendChild(fill);
    if (paceRatio != null && paceRatio > 0 && paceRatio < 1) {
      const pace = el("div", "pace");
      pace.style.left = `calc(${paceRatio * 100}% - 1px)`;
      pace.title = "오늘까지의 기준선 (예산을 날짜만큼 나눈 지점)";
      bar.appendChild(pace);
    }
    return bar;
  }

  function renderGoalCard() {
    const card = $("#goalCard");
    if (!card) return;
    const v = goalState.view;
    card.innerHTML = "";
    if (!v) { card.className = "goal-card hidden"; return; }
    const ml = monthLabel(v.month);
    if (!v.goal) {
      card.className = "goal-card empty";
      card.append(el("p", null, `${ml} 절약 목표가 아직 없어요.`));
      const b = el("button", "btn btn-small", "목표 세우기");
      b.type = "button";
      b.addEventListener("click", () => openGoalModal(true));
      card.append(b, el("div", "muted small", "최근 3개월 지출을 바탕으로 추천해 드려요."));
      return;
    }
    card.className = "goal-card";
    const p = v.progress, t = p.total;
    const top = el("div", "goal-top");
    const name = el("span", "goal-name", `${ml} 절약 목표`);
    const right = el("span");
    if (v.inherited_from) {
      const bdg = el("span", "badge inherit", `${monthLabel(v.inherited_from)} 목표 이어서`);
      bdg.title = "이번 달 목표를 따로 정하지 않아 지난 목표를 그대로 적용하고 있어요.";
      right.appendChild(bdg);
    }
    const edit = el("button", "link-btn", "수정");
    edit.type = "button";
    edit.addEventListener("click", () => openGoalModal(false));
    right.appendChild(edit);
    top.append(name, right);

    const amounts = el("div", "goal-amounts");
    amounts.append(el("b", null, won(t.spent)), el("span", "of", ` / ${won(t.budget)} · ${t.used_pct}%`));

    let msg, icon;
    if (t.status === "over") { icon = "✕"; msg = `목표를 ${won(t.spent - t.budget)} 넘었어요.`; }
    else if (t.status === "warning") { icon = "⚠"; msg = `이 페이스면 월말 ${won(t.projected)} (목표 +${(((t.projected - t.budget) / t.budget) * 100).toFixed(1)}%)`; }
    else if (t.projected == null) { icon = "✓"; msg = `남은 예산 ${won(t.remaining)} · 하루 ${won(t.daily_allowance)}씩 쓸 수 있어요.`; }
    else { icon = "✓"; msg = `목표 안쪽이에요 · 하루 ${won(t.daily_allowance)}씩 쓸 수 있어요.`; }
    const status = el("div", `goal-status ${t.status}`, `${icon} ${msg}`);

    card.append(top, amounts, goalBar(t.spent, t.budget, t.status, p.phase === "current" ? p.pace_ratio : null), status);
    if (p.phase === "current") card.append(el("div", "pace-legend", "막대 위 세로선: 오늘까지 써도 되는 지점"));

    if (p.categories.length) {
      const cats = el("div", "goal-cats");
      for (const c of p.categories) {
        const row = el("div", "goal-cat-row");
        row.append(el("span", null, c.category), el("span", `nums${c.status === "over" ? " over" : ""}`, `${won(c.spent)} / ${won(c.limit)}`));
        row.appendChild(goalBar(c.spent, c.limit, c.status, p.phase === "current" ? p.pace_ratio : null, true));
        if (c.status !== "good") row.title = c.status === "over" ? "한도를 넘었어요" : `이 페이스면 월말 ${won(c.projected)}`;
        cats.appendChild(row);
      }
      card.appendChild(cats);
    }
  }

  // ----- 설정 모달
  function limitRow(category = "배달", limit = "", avg = null) {
    const row = el("div", "limit-row");
    const sel = categoryOptions(category);
    const inp = document.createElement("input");
    inp.type = "number"; inp.min = 1; inp.step = 5000; inp.placeholder = "한도(원)"; inp.value = limit;
    const del = el("button", "link-btn danger", "삭제");
    del.type = "button";
    del.addEventListener("click", () => { row.remove(); updateLimitButton(); });
    row.append(sel, inp, del);
    if (avg != null) row.appendChild(el("div", "avg", `최근 월평균 ${won(avg)}`));
    return row;
  }
  function updateLimitButton() {
    $("#goalAddLimit").classList.toggle("hidden", $("#goalLimits").children.length >= 3);
  }
  function updateTotalHint() {
    const v = Number($("#goalTotal").value);
    $("#goalTotalHint").textContent = v > 0 ? `= ${manwon(v)}` : "";
  }

  function openGoalModal(useSuggestion) {
    const v = goalState.view;
    if (!v) return;
    if (!v.editable) { toast("지난 달 목표는 수정할 수 없어요."); return; }
    $("#goalTitle").textContent = `${monthLabel(v.month)} 절약 목표`;
    $("#goalMsg").textContent = "";
    $("#goalSuggestInfo").textContent = "최근 3개월 지출 평균을 바탕으로 계산해요.";
    $("#goalLimits").innerHTML = "";
    $("#goalTotal").value = v.goal ? v.goal.total_budget : "";
    (v.goal ? v.goal.category_limits : []).forEach((c) => $("#goalLimits").appendChild(limitRow(c.category, c.limit)));
    updateLimitButton();
    updateTotalHint();
    // 이 달에 직접 저장한 목표가 있을 때만 해제 가능 (이어받은 목표는 해제 대상 아님)
    $("#goalDelete").classList.toggle("hidden", !(v.goal && !v.inherited_from));
    const hist = (v.goal && v.goal.history) || [];
    $("#goalHistoryBox").classList.toggle("hidden", !hist.length);
    $("#goalHistory").innerHTML = "";
    hist.slice().reverse().forEach((h) => {
      const d = new Date(h.changed_at);
      $("#goalHistory").appendChild(el("li", null, `${d.getMonth() + 1}/${d.getDate()} 변경 전: 총예산 ${won(h.total_budget)}` +
        (h.category_limits.length ? ` · ${h.category_limits.map((c) => `${c.category} ${manwon(c.limit)}`).join(", ")}` : "")));
    });
    $("#goalModal").classList.remove("hidden");
    if (useSuggestion) applySuggestion();
  }

  async function applySuggestion() {
    const btn = $("#goalSuggestBtn");
    btn.disabled = true;
    try {
      const s = await api(`/api/goals/${goalState.view.month}/suggestion`);
      if (!s.available) { $("#goalSuggestInfo").textContent = s.reason; return; }
      $("#goalTotal").value = s.total_budget;
      $("#goalLimits").innerHTML = "";
      s.category_limits.forEach((c) => $("#goalLimits").appendChild(limitRow(c.category, c.limit, c.average)));
      updateLimitButton();
      updateTotalHint();
      const ms = s.basis_months.map(monthLabel).join("·");
      $("#goalSuggestInfo").textContent = `${ms} 평균 ${won(s.total_average)}에서 총예산 10%, 상위 변동 지출 15%를 줄인 값이에요.`;
    } catch (e) {
      $("#goalSuggestInfo").textContent = e.message;
    } finally {
      btn.disabled = false;
    }
  }

  async function saveGoal() {
    const total = Number($("#goalTotal").value);
    if (!Number.isInteger(total) || total <= 0) { $("#goalMsg").textContent = "월 총예산을 입력해 주세요."; return; }
    const limits = [...$("#goalLimits").children].map((row) => ({
      category: row.querySelector("select").value,
      limit: Number(row.querySelector("input").value),
    }));
    if (limits.some((l) => !Number.isInteger(l.limit) || l.limit <= 0)) { $("#goalMsg").textContent = "카테고리 한도 금액을 입력해 주세요."; return; }
    const btn = $("#goalSave");
    btn.disabled = true;
    try {
      goalState.view = await api(`/api/goals/${goalState.view.month}`, { method: "PUT", body: { total_budget: total, category_limits: limits } });
      $("#goalModal").classList.add("hidden");
      renderGoalCard();
      toast("목표를 저장했어요.");
    } catch (e) {
      $("#goalMsg").textContent = e.message;
    } finally {
      btn.disabled = false;
    }
  }

  async function deleteGoal() {
    if (!confirm("이번 달 목표를 해제할까요?")) return;
    try {
      await api(`/api/goals/${goalState.view.month}`, { method: "DELETE" });
      $("#goalModal").classList.add("hidden");
      await loadGoal();
      toast("목표를 해제했어요.");
    } catch (e) {
      $("#goalMsg").textContent = e.message;
    }
  }

  function initGoal() {
    $("#goalClose").addEventListener("click", () => $("#goalModal").classList.add("hidden"));
    $("#goalCancel").addEventListener("click", () => $("#goalModal").classList.add("hidden"));
    $("#goalSave").addEventListener("click", saveGoal);
    $("#goalDelete").addEventListener("click", deleteGoal);
    $("#goalSuggestBtn").addEventListener("click", applySuggestion);
    $("#goalTotal").addEventListener("input", updateTotalHint);
    $("#goalAddLimit").addEventListener("click", () => {
      const used = new Set([...$("#goalLimits").querySelectorAll("select")].map((s) => s.value));
      const next = ["배달", "카페·간식", "식비", "쇼핑", "문화·여가"].find((c) => !used.has(c)) || "기타";
      $("#goalLimits").appendChild(limitRow(next));
      updateLimitButton();
    });
  }

  // ---------------------------------------------------------------- 요약
  async function loadSummary() {
    try {
      const s = await api("/api/transactions/summary");
      renderSummary(s);
      loadGoal();
      return s;
    } catch (e) {
      $("#summaryBody").innerHTML = "";
      const p = document.createElement("p");
      p.className = "muted small";
      p.textContent = `요약을 불러오지 못했어요: ${e.message}`;
      $("#summaryBody").appendChild(p);
      return null;
    }
  }

  function trendWord(trend) {
    if (!trend || trend.startsWith("판단 불가")) return "판단 불가";
    return trend.split(" ")[0];
  }

  function renderSummary(s) {
    state.summary = s;
    const body = $("#summaryBody");
    if (!s || !s.count) {
      body.innerHTML = '<div id="goalCard" class="goal-card hidden"></div><p class="muted small">아직 지출 내역이 없어요. 지출 내역 탭에서 캡처를 올리거나 직접 추가해 보세요.</p>';
      renderGoalCard();
      return;
    }
    const m = s.metrics;
    const cm = s.current_month || {};
    const pct = cm.vs_monthly_average_pct;
    const deltaCls = pct == null ? "muted" : pct > 0 ? "delta-up" : "delta-down";
    const deltaTxt = pct == null
      ? (cm.elapsed_days < 7 ? "월초라 월평균 비교는 7일부터 보여드려요" : "")
      : `월평균 대비 ${pct > 0 ? "▲" : "▼"} ${Math.abs(pct)}% (월말 예상 ${manwon(cm.projected_total)})`;
    const trendDetail = (s.trend || "").slice(trendWord(s.trend).length).trim().replace(/^\(|\)$/g, "");

    body.innerHTML = `
      <div id="goalCard" class="goal-card hidden"></div>
      <div class="hero">
        <div class="hero-label">이번 달 (${cm.month}) · ${cm.elapsed_days}일 경과</div>
        <div class="hero-value">${won(cm.total)}</div>
        <div class="hero-delta ${deltaCls}">${deltaTxt}</div>
      </div>
      <div class="stats">
        <div><div class="stat-label">기간</div><div class="stat-value small">${s.period}</div></div>
        <div><div class="stat-label">데이터 개수</div><div class="stat-value">${s.count.toLocaleString()}건</div></div>
        <div><div class="stat-label">총 지출</div><div class="stat-value">${manwon(m.total)}</div></div>
        <div><div class="stat-label">월평균</div><div class="stat-value">${manwon(m.monthly_average)}</div></div>
        <div><div class="stat-label">일평균</div><div class="stat-value">${won(m.daily_average)}</div></div>
        <div><div class="stat-label">최대 지출</div><div class="stat-value">${manwon(m.max.amount)}</div>
          <div class="stat-label" id="maxMemo"></div></div>
      </div>
      <div class="trend-box">
        <div class="trend-badge">최근 추세: ${trendWord(s.trend)}</div>
        <div class="small muted" id="trendDetail"></div>
      </div>
      <div class="section-title">월별 지출</div>
      <div class="chart" id="monthlyChart"></div>
      <div class="chart-note">점선: 월평균 · 옅은 막대: 진행 중인 달</div>
      <div class="section-title donut-head">
        <span>월별 카테고리</span>
        <span class="month-nav">
          <button id="donutPrev" class="icon-btn tiny" type="button" aria-label="이전 달">‹</button>
          <span id="donutMonth"></span>
          <button id="donutNext" class="icon-btn tiny" type="button" aria-label="다음 달">›</button>
        </span>
      </div>
      <div id="donutChart" class="donut-wrap"></div>
      <ul id="donutLegend" class="donut-legend"></ul>`;

    // 서버에서 온 문자열(메모 등)은 textContent로 넣는다.
    $("#maxMemo").textContent = `${m.max.date} · ${m.max.merchant}`;
    $("#trendDetail").textContent = trendDetail;

    // 도넛: 기본은 이번 달(데이터가 없으면 가장 최근 달)
    const months = Object.keys(s.monthly_categories || {}).sort();
    if (!state.donutMonth || !months.includes(state.donutMonth)) {
      state.donutMonth = months.includes(cm.month) ? cm.month : months.at(-1);
    }
    renderDonut(s);
    renderGoalCard();
    $("#donutPrev").addEventListener("click", () => moveDonut(s, -1));
    $("#donutNext").addEventListener("click", () => moveDonut(s, 1));

    renderMonthlyChart($("#monthlyChart"), s.monthly_totals, m.monthly_average, cm);

    if (!$("#dataMonth").value && cm.month) {
      $("#dataMonth").value = cm.month;
      loadData();
    }
  }

  // ---------------------------------------------------------------- 월별 카테고리 도넛
  // 색은 카테고리에 고정(달이 바뀌어도 '배달'은 항상 주황). 색이 없는 카테고리는 '그 외'로 묶는다.
  const CAT_COLOR = {
    "식비": 1, "배달": 2, "카페·간식": 3, "장보기·생활": 4,
    "쇼핑": 5, "주거·통신": 6, "교통": 7, "문화·여가": 8,
  };

  function moveDonut(s, step) {
    const months = Object.keys(s.monthly_categories || {}).sort();
    const i = months.indexOf(state.donutMonth) + step;
    if (i < 0 || i >= months.length) return;
    state.donutMonth = months[i];
    renderDonut(s);
    renderGoalCard();
  }

  function donutSlices(items) {
    const slices = [];
    let other = 0;
    const otherNames = [];
    for (const c of items) {
      if (CAT_COLOR[c.category]) slices.push({ name: c.category, total: c.total, color: `var(--cat-${CAT_COLOR[c.category]})` });
      else { other += c.total; otherNames.push(c.category); }
    }
    if (other > 0) slices.push({ name: "그 외", total: other, color: "var(--cat-other)", detail: otherNames.join(", ") });
    return slices;
  }

  function renderDonut(s) {
    const month = state.donutMonth;
    const months = Object.keys(s.monthly_categories || {}).sort();
    const wrap = $("#donutChart");
    const legend = $("#donutLegend");
    if (!wrap) return;
    wrap.innerHTML = "";
    legend.innerHTML = "";
    if (!month) { wrap.innerHTML = '<p class="muted small">데이터가 없어요.</p>'; return; }
    const [yy, mm] = month.split("-");
    $("#donutMonth").textContent = `${yy}년 ${Number(mm)}월`;
    $("#donutPrev").disabled = months.indexOf(month) <= 0;
    $("#donutNext").disabled = months.indexOf(month) >= months.length - 1;

    const slices = donutSlices(s.monthly_categories[month] || []);
    const total = slices.reduce((a, c) => a + c.total, 0);
    const size = 168, cx = size / 2, cy = size / 2, R = 78, r = 50;
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", `${yy}년 ${Number(mm)}월 카테고리별 지출: ` + slices.map((c) => `${c.name} ${won(c.total)}`).join(", "));
    const tip = document.createElement("div");
    tip.className = "tooltip hidden";

    const pt = (rad, a) => [cx + rad * Math.sin(a), cy - rad * Math.cos(a)];
    let start = 0;
    const paths = [];
    slices.forEach((c) => {
      const frac = c.total / total;
      const end = start + frac * Math.PI * 2;
      let d;
      if (frac >= 0.9999) {  // 한 카테고리뿐이면 고리 하나
        d = `M${cx} ${cy - R}A${R} ${R} 0 1 1 ${cx - 0.01} ${cy - R}ZM${cx} ${cy - r}A${r} ${r} 0 1 0 ${cx + 0.01} ${cy - r}Z`;
      } else {
        const large = end - start > Math.PI ? 1 : 0;
        const [x1, y1] = pt(R, start), [x2, y2] = pt(R, end), [x3, y3] = pt(r, end), [x4, y4] = pt(r, start);
        d = `M${x1} ${y1}A${R} ${R} 0 ${large} 1 ${x2} ${y2}L${x3} ${y3}A${r} ${r} 0 ${large} 0 ${x4} ${y4}Z`;
      }
      const path = document.createElementNS(ns, "path");
      path.setAttribute("d", d);
      path.setAttribute("fill", c.color);
      path.setAttribute("class", "donut-slice");
      path.setAttribute("fill-rule", "evenodd");
      const pct = (frac * 100).toFixed(1);
      const label = `${c.name} · ${won(c.total)} (${pct}%)${c.detail ? ` — ${c.detail}` : ""}`;
      const mid = (start + end) / 2;
      path.addEventListener("mouseenter", () => {
        paths.forEach((p) => p.classList.toggle("dim", p !== path));
        tip.textContent = label;
        tip.classList.remove("hidden");
        const rect = svg.getBoundingClientRect(), k = rect.width / size;
        const [tx, ty] = pt(R, mid);
        const half = tip.offsetWidth / 2;
        const box = wrap.getBoundingClientRect();
        tip.style.left = `${Math.min(Math.max(rect.left - box.left + tx * k, half), box.width - half)}px`;
        tip.style.top = `${rect.top - box.top + ty * k}px`;
      });
      path.addEventListener("mouseleave", () => { paths.forEach((p) => p.classList.remove("dim")); tip.classList.add("hidden"); });
      paths.push(path);
      svg.appendChild(path);
      start = end;
    });
    // 가운데: 그 달 총액
    const t1 = document.createElementNS(ns, "text");
    t1.setAttribute("x", cx); t1.setAttribute("y", cy - 4); t1.setAttribute("class", "donut-center-label");
    t1.textContent = "총 지출";
    const t2 = document.createElementNS(ns, "text");
    t2.setAttribute("x", cx); t2.setAttribute("y", cy + 15); t2.setAttribute("class", "donut-center-value");
    t2.textContent = manwon(total);
    svg.append(t1, t2);
    wrap.append(svg, tip);

    // 범례: 색 · 이름 · 금액 · 비율 (정확한 비교는 숫자로)
    for (const c of slices) {
      const li = document.createElement("li");
      const dot = document.createElement("span");
      dot.className = "dot";
      dot.style.background = c.color;
      const name = document.createElement("span");
      name.className = "lg-name";
      name.textContent = c.name;
      if (c.detail) name.title = c.detail;
      const amt = document.createElement("span");
      amt.className = "lg-amt";
      amt.textContent = won(c.total);
      const pct = document.createElement("span");
      pct.className = "lg-pct";
      pct.textContent = `${((c.total / total) * 100).toFixed(1)}%`;
      li.append(dot, name, amt, pct);
      legend.appendChild(li);
    }
  }

  function niceStep(max) {
    const raw = max / 4;
    const pow = Math.pow(10, Math.floor(Math.log10(raw)));
    const n = raw / pow;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * pow;
  }

  function renderMonthlyChart(container, monthly, avg, cm) {
    const entries = Object.entries(monthly || {});
    if (!entries.length) return;
    const W = 300, H = 170, padL = 34, padR = 4, padT = 10, padB = 20;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const maxVal = Math.max(...entries.map(([, v]) => v), avg);
    const step = niceStep(maxVal);
    const top = Math.ceil(maxVal / step) * step;
    const y = (v) => padT + plotH - (v / top) * plotH;
    const slot = plotW / entries.length;
    const bw = Math.min(18, slot - 6);
    const ns = "http://www.w3.org/2000/svg";

    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "월별 지출 막대 그래프: " + entries.map(([k, v]) => `${k} ${manwon(v)}`).join(", "));

    const el = (tag, attrs, text) => {
      const n = document.createElementNS(ns, tag);
      for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
      if (text != null) n.textContent = text;
      svg.appendChild(n);
      return n;
    };

    for (let v = 0; v <= top; v += step) {
      el("line", { x1: padL, x2: W - padR, y1: y(v), y2: y(v), class: "grid-line" });
      el("text", { x: padL - 4, y: y(v) + 3, "text-anchor": "end", class: "axis-label" }, v === 0 ? "0" : `${v / 10000}만`);
    }

    const tip = document.createElement("div");
    tip.className = "tooltip hidden";
    const bars = [];
    entries.forEach(([month, v], i) => {
      const cx = padL + slot * i + slot / 2;
      const x = cx - bw / 2, yt = y(v), yb = y(0), r = Math.min(4, (yb - yt) / 2);
      // 위쪽만 둥근 막대 (기준선에 붙은 쪽은 직각)
      const d = `M${x},${yb} V${yt + r} Q${x},${yt} ${x + r},${yt} H${x + bw - r} Q${x + bw},${yt} ${x + bw},${yt + r} V${yb} Z`;
      const partial = cm && month === cm.month;
      const bar = el("path", { d, class: partial ? "bar partial" : "bar" });
      bars.push(bar);
      el("text", { x: cx, y: H - 6, "text-anchor": "middle", class: "axis-label" }, `${Number(month.slice(5))}월`);
      // 막대보다 넓은 투명 히트 영역
      const hit = el("rect", { x: padL + slot * i, y: padT, width: slot, height: plotH, fill: "transparent" });
      const label = partial
        ? `${month} · ${won(v)} (진행 중, 예상 ${manwon(cm.projected_total)})`
        : `${month} · ${won(v)} (월평균 대비 ${v >= avg ? "+" : ""}${(((v - avg) / avg) * 100).toFixed(1)}%)`;
      hit.addEventListener("mouseenter", () => {
        bar.classList.add("hover");
        tip.textContent = label;
        tip.classList.remove("hidden");
        const rect = svg.getBoundingClientRect();
        const scale = rect.width / W;
        const half = tip.offsetWidth / 2; // 패널 밖으로 잘리지 않도록 툴팁 폭 기준으로 위치 보정
        tip.style.left = `${Math.min(Math.max(cx * scale, half), rect.width - half)}px`;
        tip.style.top = `${yt * scale}px`;
      });
      hit.addEventListener("mouseleave", () => {
        bar.classList.remove("hover");
        tip.classList.add("hidden");
      });
    });

    el("line", { x1: padL, x2: W - padR, y1: y(avg), y2: y(avg), class: "avg-line" });

    container.innerHTML = "";
    container.append(svg, tip);
  }

  // ---------------------------------------------------------------- 로그인 / 동의 / 사용자 메뉴
  function showOnly(which) {
    $("#bootScreen").classList.toggle("hidden", which !== "boot");
    $("#authScreen").classList.toggle("hidden", which !== "auth");
    $("#appShell").classList.toggle("hidden", which !== "app");
    $("#userMenu").classList.toggle("hidden", which !== "app");
  }

  function resetAppState() {
    state.user = null;
    state.conversationId = null;
    state.summary = null;
    state.dataRows = [];
    showWelcome();
    $("#conversationList").innerHTML = "";
    $("#dataTableBody").innerHTML = "";
    $("#dataMonth").value = "";
    $("#summaryBody").innerHTML = '<p class="muted small">불러오는 중…</p>';
    setFormMessage("", "");
    upload.items = [];
    $("#uploadModal").classList.add("hidden");
    goalState.view = null;
    $("#goalModal").classList.add("hidden");
    $("#toast").classList.add("hidden");
  }

  let unauthorizedShown = false;
  async function handleUnauthorized(msg) {
    if (unauthorizedShown) return;
    unauthorizedShown = true;
    try { await Auth.logout(); } catch (_) { /* noop */ }
    $("#authError").textContent = msg || "다시 로그인해 주세요.";
  }

  function showConsent() {
    $("#consentCheck").checked = false;
    $("#consentAgree").disabled = true;
    $("#consentModal").classList.remove("hidden");
  }
  function hideConsent() {
    $("#consentModal").classList.add("hidden");
  }

  function renderUser(me) {
    const label = me.is_anonymous ? "체험 모드" : (me.name || me.email || "사용자");
    $("#userLabel").textContent = label;
    $("#userAvatar").textContent = me.is_anonymous ? "?" : label.trim().charAt(0).toUpperCase();
    $("#userEmail").textContent = me.is_anonymous
      ? "체험 모드: 로그아웃하면 데이터가 삭제돼요."
      : (me.email || "");
  }

  /** 로그인된 사용자: 프로필 확인 → (동의) → (체험이면 샘플) → 앱 데이터 로드 */
  async function enterApp() {
    showOnly("boot");
    const me = await api("/api/me", { timeout: 90000 });
    state.user = me;
    renderUser(me);
    if (!me.consented) {
      showOnly("app");
      showConsent();
      return; // 동의 버튼에서 이어서 진행
    }
    await afterConsent();
  }

  async function afterConsent() {
    hideConsent();
    showOnly("app");
    if (state.user && state.user.is_anonymous) {
      const r = await api("/api/me/demo", { method: "POST", timeout: 60000 });
      if (r && r.seeded) toast(`샘플 지출 데이터 ${r.seeded}건을 불러왔어요.`);
    }
    await Promise.all([loadSummary(), loadConversations()]);
  }

  function initAuthUi() {
    $("#googleLoginBtn").addEventListener("click", async () => {
      $("#authError").textContent = "";
      try { await Auth.signInWithGoogle(); } catch (e) { $("#authError").textContent = Auth.authErrorMessage(e); }
    });
    $("#guestLoginBtn").addEventListener("click", async () => {
      $("#authError").textContent = "";
      try { await Auth.signInAsGuest(); } catch (e) { $("#authError").textContent = Auth.authErrorMessage(e); }
    });

    $("#consentCheck").addEventListener("change", (e) => { $("#consentAgree").disabled = !e.target.checked; });
    $("#consentAgree").addEventListener("click", async () => {
      $("#consentAgree").disabled = true;
      try {
        state.user = await api("/api/me/consent", { method: "POST" });
        await afterConsent();
      } catch (e) {
        toast(e.message);
        $("#consentAgree").disabled = false;
      }
    });
    $("#consentDecline").addEventListener("click", async () => {
      hideConsent();
      await signOutFlow("동의하지 않으면 서비스를 이용할 수 없어요.");
    });

    const dd = $("#userDropdown");
    $("#userMenuBtn").addEventListener("click", (e) => {
      e.stopPropagation();
      const open = dd.classList.toggle("hidden") === false;
      $("#userMenuBtn").setAttribute("aria-expanded", open);
    });
    document.addEventListener("click", () => dd.classList.add("hidden"));
    $("#logoutBtn").addEventListener("click", () => signOutFlow());
    $("#deleteMeBtn").addEventListener("click", deleteMe);
  }

  async function signOutFlow(message) {
    // 체험(익명) 계정은 로그아웃하면 다시 들어올 수 없으므로 데이터를 지우고 나간다.
    if (state.user && state.user.is_anonymous) {
      try { await api("/api/me", { method: "DELETE" }); } catch (_) { /* noop */ }
    }
    await Auth.logout();
    if (message) $("#authError").textContent = message;
  }

  async function deleteMe() {
    const ok = confirm("업로드한 지출 내역, 대화 기록, 목표 등 모든 데이터와 계정이 즉시 삭제돼요.\n되돌릴 수 없어요. 삭제할까요?");
    if (!ok) return;
    try {
      await api("/api/me", { method: "DELETE", timeout: 60000 });
      await Auth.logout();
      $("#authError").textContent = "모든 데이터를 삭제했어요.";
    } catch (e) {
      toast(e.message);
    }
  }

  // ---------------------------------------------------------------- 시작
  async function init() {
    initTheme();
    initTabs();
    initChat();
    initData();
    initUpload();
    initGoal();
    $("#refreshSummary").addEventListener("click", loadSummary);

    try {
      Auth = await import("./auth.js");
    } catch (e) {
      showOnly("auth");
      $("#authError").textContent = "로그인 모듈을 불러오지 못했어요. (Firebase 설정 또는 네트워크 확인)";
      console.error(e);
      return;
    }
    initAuthUi();

    const ok = await warmUp();
    if (!ok) {
      $("#authError").textContent = "서버에 연결할 수 없어요. 서버가 켜져 있는지 확인한 뒤 다시 시도해 주세요.";
    }

    // 서버 연결 확인이 실패해도 로그인 감지는 항상 시작한다.
    // (서버가 나중에 켜지면 로그인 버튼만 다시 눌러도 진행되도록)
    Auth.watchAuth(async (user) => {
      unauthorizedShown = false;
      if (!user) {
        resetAppState();
        hideConsent();
        showOnly("auth");
        return;
      }
      try {
        await enterApp();
      } catch (e) {
        if (e.status !== 401) {
          // 서버 오류로 진입 실패 → 로그아웃해 두어야 버튼을 다시 눌렀을 때 처음부터 재시도된다
          const msg = e.message;
          try { await Auth.logout(); } catch (_) { /* noop */ }
          showOnly("auth");
          $("#authError").textContent = msg;
        }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
