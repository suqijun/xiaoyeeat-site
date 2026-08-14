(() => {
  const callBtn = document.getElementById("callBtn");
  const callLabel = document.getElementById("callLabel");
  const headline = document.getElementById("headline");
  const subline = document.getElementById("subline");
  const orb = document.getElementById("orb");
  const statusDot = document.getElementById("statusDot");
  const hint = document.getElementById("hint");
  const leadSource = document.getElementById("leadSource");
  const leadName = document.getElementById("leadName");
  const leadMeta = document.getElementById("leadMeta");
  const roleYouBody = document.getElementById("roleYouBody");
  const notePanel = document.getElementById("notePanel");
  const noteForm = document.getElementById("noteForm");
  const noteFields = document.getElementById("noteFields");
  const noteEditActions = document.getElementById("noteEditActions");
  const noteStatus = document.getElementById("noteStatus");
  const noteDismiss = document.getElementById("noteDismiss");
  const noteEditBtn = document.getElementById("noteEditBtn");
  const noteCancelEdit = document.getElementById("noteCancelEdit");
  const noteDestinations = document.getElementById("noteDestinations");
  const noteDestText = document.getElementById("noteDestText");
  const transcriptLog = document.getElementById("transcriptLog");
  const panelForm = document.getElementById("panelForm");
  const panelTranscript = document.getElementById("panelTranscript");
  const tabForm = document.getElementById("tabForm");
  const tabTranscript = document.getElementById("tabTranscript");
  const noteChromeRight = document.querySelector(".note-chrome-right");
  const noteLeadTitle = document.getElementById("noteLeadTitle");
  const noteLeadMeta = document.getElementById("noteLeadMeta");
  const invalidReasonField = document.getElementById("invalidReasonField");
  const EMPTY = "—";

  const INPUT_RATE = 16000;
  const OUTPUT_RATE = 24000;
  const FRAME_MS = 20;
  const FRAME_SAMPLES = (INPUT_RATE * FRAME_MS) / 1000;

  let ws = null;
  let mediaStream = null;
  let audioContext = null;
  let processor = null;
  let sourceNode = null;
  let inCall = false;
  let connecting = false;
  let lastError = "";
  let nextPlayTime = 0;
  const activeSources = new Set();
  let lead = null;
  let enums = null;
  let callLog = [];
  let lastFinalUser = "";
  let currentNote = null;
  let currentNoteId = null;

  function fillSelect(el, options, includeEmpty) {
    if (!el) return;
    el.innerHTML = "";
    if (includeEmpty) {
      const o = document.createElement("option");
      o.value = "";
      o.textContent = "—";
      el.appendChild(o);
    }
    (options || []).forEach((v) => {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = v;
      el.appendChild(o);
    });
  }

  function fillDestCheckboxes(options) {
    noteDestinations.innerHTML = "";
    (options || []).forEach((v) => {
      const id = `dest_${encodeURIComponent(v)}`;
      const label = document.createElement("label");
      label.className = "check-item";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.name = "destinations";
      input.value = v;
      input.id = id;
      const span = document.createElement("span");
      span.textContent = v;
      label.appendChild(input);
      label.appendChild(span);
      noteDestinations.appendChild(label);
    });
  }

  function syncDestChipState() {
    noteDestinations.querySelectorAll(".check-item").forEach((label) => {
      const input = label.querySelector('input[type="checkbox"]');
      label.classList.toggle("is-on", Boolean(input && input.checked));
    });
  }

  function getSelectedDestinations() {
    return Array.from(
      noteDestinations.querySelectorAll('input[name="destinations"]:checked')
    ).map((el) => el.value);
  }

  function setSelectedDestinations(list) {
    const set = new Set(list || []);
    noteDestinations.querySelectorAll('input[name="destinations"]').forEach((el) => {
      el.checked = set.has(el.value);
    });
    syncDestChipState();
    updateDestText(list);
  }

  function updateDestText(list) {
    const items = (list || []).filter(Boolean);
    const text = items.length ? items.join("、") : EMPTY;
    noteDestText.textContent = text;
    noteDestText.classList.toggle("is-empty", !items.length);
  }

  function isViewMode() {
    return noteForm.classList.contains("is-view");
  }

  function displayText(value) {
    const s = String(value || "").trim();
    if (isViewMode()) return s || EMPTY;
    return s;
  }

  function realText(value) {
    const s = String(value || "").trim();
    return !s || s === EMPTY ? "" : s;
  }

  function setTextControl(el, value) {
    const shown = displayText(value);
    el.value = shown;
    el.classList.toggle("is-empty", isViewMode() && shown === EMPTY);
  }

  function syncInvalidReasonVisibility() {
    const valid = document.getElementById("noteResult").value === "有效";
    if (!invalidReasonField) return;
    invalidReasonField.hidden = valid && isViewMode();
    if (valid && !isViewMode()) {
      document.getElementById("noteInvalidReason").value = "";
    }
  }

  function refreshNoteHeader(record) {
    const contact = lead?.contact || {};
    const company = (contact.company || "").replace(/^[^·]*·\s*/, "") || contact.company || "";
    const name = contact.name || "联系人";
    noteLeadTitle.textContent = company ? `${name} · ${company}` : name;
    const result = record?.ai_result || "";
    const saved = record?.edited ? "已人工修订" : "已自动保存";
    noteLeadMeta.textContent = result ? `${saved} · 线索${result}` : saved;
  }

  function normalizeDestinations(slots) {
    if (Array.isArray(slots.destinations) && slots.destinations.length) {
      return slots.destinations.filter(Boolean);
    }
    const raw = slots.destination || slots.destination_or_route || "";
    if (!raw) return [];
    return String(raw)
      .split(/[、,，/|]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  async function loadEnums() {
    try {
      const res = await fetch("/api/enums");
      const body = await res.json();
      enums = body.enums || {};
      fillSelect(document.getElementById("noteOrigin"), enums.origins || [], true);
      fillDestCheckboxes(enums.destinations || []);
      fillSelect(document.getElementById("noteIntent"), enums.intents || ["高", "中", "低", "无"]);
      fillSelect(document.getElementById("noteInvalidReason"), enums.invalid_reasons || [], true);
      fillSelect(document.getElementById("noteMethod"), enums.visit_methods || ["电话拜访"]);
      fillSelect(document.getElementById("noteNext"), enums.next_actions || [], true);
    } catch (err) {
      console.error("loadEnums failed", err);
      enums = {};
    }
  }

  async function loadLead() {
    try {
      const res = await fetch("/api/lead");
      lead = await res.json();
      const contact = lead.contact || {};
      const referrer = lead.referrer || {};
      leadSource.textContent = lead.source || "员工推荐";
      leadName.textContent = `${contact.name || "联系人"} · ${contact.company || ""}`;
      leadMeta.textContent = [
        referrer.name ? `推荐人：${referrer.dept || ""} ${referrer.name}` : "",
        referrer.note || "",
        contact.phone_display ? `电话 ${contact.phone_display}` : "",
        contact.city ? `城市 ${contact.city}` : "",
      ]
        .filter(Boolean)
        .join("\n");
      roleYouBody.textContent = `接通后用麦克风应答，扮演「${contact.name || "联系人"}」。`;
      subline.textContent = "点下方按钮开始；小陈会先开口";
    } catch (_) {
      leadName.textContent = "线索加载失败";
    }
  }

  function setUI(state, message) {
    orb.dataset.state = state;
    if (statusDot) {
      statusDot.dataset.state = lastError && state === "idle" ? "error" : state;
    }
    if (state === "idle") {
      headline.textContent = lastError ? "接通失败" : "待接听";
      subline.textContent = lastError
        ? lastError
        : "点下方按钮开始；小陈会先开口";
      callBtn.classList.remove("is-active");
      callLabel.textContent = "接听";
      hint.textContent = lastError || "需要麦克风权限。再点一次可挂断。";
    } else if (state === "connecting") {
      headline.textContent = "正在接通…";
      subline.textContent = message || "连接语音服务";
      callBtn.classList.add("is-active");
      callLabel.textContent = "挂断";
      hint.textContent = "请稍候";
    } else if (state === "in_call") {
      headline.textContent = "通话中";
      subline.textContent = message || "你是被叫方，直接开口即可";
      callBtn.classList.add("is-active");
      callLabel.textContent = "挂断";
      hint.textContent = "再点一次结束通话；结束后自动生成拜访小记";
    } else if (state === "speaking") {
      orb.dataset.state = "speaking";
      if (statusDot) statusDot.dataset.state = "speaking";
    }
  }

  function stopPlayback() {
    for (const src of activeSources) {
      try {
        src.stop();
      } catch (_) {}
    }
    activeSources.clear();
    nextPlayTime = 0;
    if (inCall) setUI("in_call");
  }

  function ensureAudioContext() {
    if (!audioContext) audioContext = new AudioContext({ sampleRate: OUTPUT_RATE });
    if (audioContext.state === "suspended") return audioContext.resume();
    return Promise.resolve();
  }

  function playPcm16(bytes) {
    if (!audioContext || !bytes || bytes.byteLength < 2) return;
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const samples = bytes.byteLength / 2;
    const buffer = audioContext.createBuffer(1, samples, OUTPUT_RATE);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < samples; i++) channel[i] = view.getInt16(i * 2, true) / 32768;
    const src = audioContext.createBufferSource();
    src.buffer = buffer;
    src.connect(audioContext.destination);
    const now = audioContext.currentTime;
    if (nextPlayTime < now + 0.02) nextPlayTime = now + 0.02;
    src.start(nextPlayTime);
    nextPlayTime += buffer.duration;
    activeSources.add(src);
    src.onended = () => activeSources.delete(src);
    setUI("speaking");
  }

  function floatTo16BitPCM(float32) {
    const out = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
      const s = Math.max(-1, Math.min(1, float32[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }

  function downsampleBuffer(buffer, inRate, outRate) {
    if (inRate === outRate) return floatTo16BitPCM(buffer);
    const ratio = inRate / outRate;
    const newLen = Math.round(buffer.length / ratio);
    const result = new Float32Array(newLen);
    for (let i = 0; i < newLen; i++) result[i] = buffer[Math.floor(i * ratio)];
    return floatTo16BitPCM(result);
  }

  async function startMic(sendBytes) {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      video: false,
    });
    await ensureAudioContext();
    sourceNode = audioContext.createMediaStreamSource(mediaStream);
    processor = audioContext.createScriptProcessor(4096, 1, 1);
    let pending = new Int16Array(0);
    processor.onaudioprocess = (event) => {
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      const input = event.inputBuffer.getChannelData(0);
      const pcm = downsampleBuffer(input, audioContext.sampleRate, INPUT_RATE);
      const merged = new Int16Array(pending.length + pcm.length);
      merged.set(pending);
      merged.set(pcm, pending.length);
      let offset = 0;
      while (offset + FRAME_SAMPLES <= merged.length) {
        const frame = merged.subarray(offset, offset + FRAME_SAMPLES);
        sendBytes(frame.buffer.slice(frame.byteOffset, frame.byteOffset + frame.byteLength));
        offset += FRAME_SAMPLES;
      }
      pending = merged.subarray(offset);
    };
    const mute = audioContext.createGain();
    mute.gain.value = 0;
    sourceNode.connect(processor);
    processor.connect(mute);
    mute.connect(audioContext.destination);
  }

  function stopMic() {
    if (processor) {
      processor.disconnect();
      processor.onaudioprocess = null;
      processor = null;
    }
    if (sourceNode) {
      sourceNode.disconnect();
      sourceNode = null;
    }
    if (mediaStream) {
      mediaStream.getTracks().forEach((t) => t.stop());
      mediaStream = null;
    }
  }

  function switchTab(tab) {
    const isForm = tab === "form";
    tabForm.classList.toggle("is-active", isForm);
    tabTranscript.classList.toggle("is-active", !isForm);
    tabForm.setAttribute("aria-selected", String(isForm));
    tabTranscript.setAttribute("aria-selected", String(!isForm));
    panelForm.hidden = !isForm;
    panelTranscript.hidden = isForm;
    if (noteChromeRight) {
      noteChromeRight.classList.toggle("is-transcript", !isForm);
    }
    if (!isForm && noteForm.classList.contains("is-edit")) {
      if (currentNote) fillNoteForm(currentNote);
      showViewMode();
    }
  }

  function mergeTranscript(log) {
    const merged = [];
    for (const row of log || []) {
      const role = row.role || "";
      const text = String(row.text || "").trim();
      if (!text) continue;
      const last = merged[merged.length - 1];
      if (last && last.role === role) {
        const a = last.text;
        const needSpace = /[A-Za-z0-9]$/.test(a) && /^[A-Za-z0-9]/.test(text);
        last.text = a + (needSpace ? " " : "") + text;
      } else {
        merged.push({ role, text });
      }
    }
    return merged;
  }

  function renderTranscriptLog(log) {
    const rows = mergeTranscript(log);
    if (!rows.length) {
      transcriptLog.innerHTML = '<p class="transcript-empty">暂无录音稿</p>';
      return;
    }
    transcriptLog.innerHTML = rows
      .map((row) => {
        const who = row.role === "user" ? "你" : "小陈";
        const text = String(row.text || "").replace(/</g, "&lt;");
        return `<div class="transcript-line"><span class="transcript-who">${who}</span><p>${text}</p></div>`;
      })
      .join("");
  }

  function fillNoteForm(record) {
    const slots = record.slots || {};
    document.getElementById("noteResult").value = record.ai_result || "无效";
    document.getElementById("noteInvalidReason").value = record.ai_invalid_reason || "";
    document.getElementById("noteIntent").value = record.ai_intent || "无";
    document.getElementById("noteNeed").value =
      slots.has_shipping_need === "是" || slots.has_shipping_need === "否"
        ? slots.has_shipping_need
        : "";
    document.getElementById("noteOrigin").value = slots.origin || "";
    setSelectedDestinations(normalizeDestinations(slots));
    setTextControl(document.getElementById("noteVolume"), slots.monthly_volume || "");
    setTextControl(document.getElementById("noteContactAlt"), slots.contact_alt || "");
    document.getElementById("noteMethod").value = record.visit_method || "电话拜访";
    setTextControl(document.getElementById("noteSummary"), record.communication_summary || "");
    document.getElementById("noteNext").value = slots.next_action || "";
    syncInvalidReasonVisibility();
    refreshNoteHeader(record);
  }

  function showViewMode() {
    noteForm.classList.add("is-view");
    noteForm.classList.remove("is-edit");
    noteFields.disabled = true;
    if (noteChromeRight) noteChromeRight.classList.remove("is-editing");
    if (currentNote) fillNoteForm(currentNote);
  }

  function showEditMode() {
    noteForm.classList.remove("is-view");
    noteForm.classList.add("is-edit");
    noteFields.disabled = false;
    if (noteChromeRight) noteChromeRight.classList.add("is-editing");
    fillNoteForm(currentNote || {});
  }

  function draftToRecord(draft, endedAt) {
    const slots = draft.slots || {};
    const destinations = normalizeDestinations({
      ...slots,
      destinations: draft.destinations || slots.destinations,
    });
    const destLabel = destinations.join("、");
    return {
      lead_id: lead?.lead_id,
      ended_at: endedAt,
      visit_method: draft.visit_method || "电话拜访",
      judgment_source: "call_transcript_extract",
      ai_result: draft.ai_result || draft.result,
      ai_invalid_reason: draft.ai_invalid_reason || draft.invalid_reason || "",
      ai_intent: draft.ai_intent || draft.intent || "",
      ai_followable: Boolean(draft.ai_followable ?? draft.followable === "是"),
      slots: {
        has_shipping_need: slots.has_shipping_need || "",
        origin: slots.origin || "",
        destinations,
        destination: destLabel,
        destination_or_route: destLabel,
        monthly_volume: slots.monthly_volume || "",
        contact_alt: slots.contact_alt || "",
        next_action: slots.next_action || "无需跟进",
      },
      communication_summary: draft.communication_summary || draft.summary || "",
      transcript: callLog,
      edited: false,
    };
  }

  async function autoSaveVisitNote() {
    notePanel.hidden = false;
    switchTab("form");
    noteStatus.textContent = "正在根据通话内容生成并保存拜访小记…";
    showViewMode();
    renderTranscriptLog(callLog);
    try {
      const extractRes = await fetch("/api/extract-visit-note", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript: callLog, lead_id: lead?.lead_id }),
      });
      const extractBody = await extractRes.json();
      if (!extractRes.ok || !extractBody.ok) throw new Error(extractBody.message || "抽取失败");

      const endedAt = new Date().toISOString();
      const payload = draftToRecord(extractBody.draft || {}, endedAt);
      const saveRes = await fetch("/api/visit-notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const saveBody = await saveRes.json();
      if (!saveRes.ok || !saveBody.ok) throw new Error(saveBody.message || "保存失败");

      currentNote = saveBody.record || payload;
      currentNoteId = saveBody.note_id;
      showViewMode();
      renderTranscriptLog(currentNote.transcript || callLog);
      noteStatus.textContent = "";
    } catch (err) {
      noteStatus.textContent = err.message || String(err);
    }
  }

  async function hangup({ showNote = true, preserveError = false } = {}) {
    const hadCall = inCall || callLog.length > 0;
    const errorText = preserveError ? lastError : "";
    inCall = false;
    connecting = false;
    stopPlayback();
    stopMic();
    if (ws) {
      const socket = ws;
      ws = null;
      socket.onclose = null;
      if (socket.readyState === WebSocket.OPEN) {
        try {
          socket.send(JSON.stringify({ type: "hangup" }));
        } catch (_) {}
        try {
          socket.close();
        } catch (_) {}
      }
    }
    lastError = errorText;
    setUI("idle");
    if (showNote && hadCall && !lastError) await autoSaveVisitNote();
  }

  async function startCall() {
    if (inCall || connecting) {
      await hangup({ showNote: true });
      return;
    }
    lastError = "";
    connecting = true;
    setUI("connecting");
    callLog = [];
    lastFinalUser = "";
    notePanel.hidden = true;
    currentNote = null;
    currentNoteId = null;

    try {
      await ensureAudioContext();
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws/call`);
      ws.binaryType = "arraybuffer";

      ws.onmessage = async (event) => {
        if (event.data instanceof ArrayBuffer) {
          playPcm16(new Uint8Array(event.data));
          return;
        }
        const msg = JSON.parse(event.data);
        if (msg.type === "status") {
          if (msg.state === "in_call") {
            inCall = true;
            connecting = false;
            lastError = "";
            setUI("in_call");
            try {
              await startMic((buf) => {
                if (ws && ws.readyState === WebSocket.OPEN) ws.send(buf);
              });
            } catch (_) {
              lastError = "麦克风权限被拒绝，请允许后重拨";
              await hangup({ showNote: false, preserveError: true });
            }
          } else if (msg.state === "connecting") {
            setUI("connecting");
          } else if (msg.state === "ended") {
            await hangup({ showNote: true });
          } else if (msg.state === "idle") {
            if (inCall) await hangup({ showNote: true });
            else if (connecting && !lastError) {
              connecting = false;
              setUI("idle");
            }
          }
        } else if (msg.type === "interrupt") {
          stopPlayback();
        } else if (msg.type === "asr") {
          if (!msg.interim && msg.text && msg.text !== lastFinalUser) {
            lastFinalUser = msg.text;
            callLog.push({ role: "user", text: msg.text });
          }
        } else if (msg.type === "bot_text") {
          if (msg.text) callLog.push({ role: "bot", text: msg.text });
        } else if (msg.type === "tts_end") {
          if (inCall) setUI("in_call");
        } else if (msg.type === "error") {
          lastError = msg.message || "接通失败";
          connecting = false;
          setUI("idle");
        }
      };

      ws.onerror = () => {
        lastError = "WebSocket 连接失败，请确认服务已启动";
        connecting = false;
        setUI("idle");
      };

      ws.onclose = () => {
        if (inCall) hangup({ showNote: true });
        else if (connecting) {
          connecting = false;
          if (!lastError) lastError = "通话连接已断开";
          setUI("idle");
        }
      };
    } catch (err) {
      lastError = err.message || String(err);
      connecting = false;
      setUI("idle");
    }
  }

  tabForm.addEventListener("click", () => switchTab("form"));
  tabTranscript.addEventListener("click", () => switchTab("transcript"));

  noteDismiss.addEventListener("click", () => {
    notePanel.hidden = true;
  });
  noteEditBtn.addEventListener("click", () => {
    switchTab("form");
    showEditMode();
  });
  noteCancelEdit.addEventListener("click", () => {
    showViewMode();
  });
  noteDestinations.addEventListener("change", () => {
    syncDestChipState();
    updateDestText(getSelectedDestinations());
  });
  noteDestinations.addEventListener("click", (event) => {
    // 确保点到文案也能触发；并立刻刷新选中样式
    const label = event.target.closest(".check-item");
    if (!label || noteForm.classList.contains("is-view")) return;
    requestAnimationFrame(() => {
      syncDestChipState();
      updateDestText(getSelectedDestinations());
    });
  });
  document.getElementById("noteResult").addEventListener("change", syncInvalidReasonVisibility);

  noteForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(noteForm).entries());
    const destinations = getSelectedDestinations();
    const destLabel = destinations.join("、");
    const result = data.result || "无效";
    const payload = {
      note_id: currentNoteId,
      lead_id: lead?.lead_id,
      ended_at: currentNote?.ended_at || new Date().toISOString(),
      visit_method: data.visit_method || "电话拜访",
      judgment_source: "call_transcript_extract",
      ai_result: result,
      ai_invalid_reason: result === "有效" ? "" : realText(data.invalid_reason),
      ai_intent: data.intent,
      ai_followable: result === "有效",
      slots: {
        has_shipping_need:
          data.has_shipping_need === "是" || data.has_shipping_need === "否"
            ? data.has_shipping_need
            : "",
        origin: data.origin || "",
        destinations,
        destination: destLabel,
        destination_or_route: destLabel,
        monthly_volume: realText(data.monthly_volume),
        contact_alt: realText(data.contact_alt),
        next_action: data.next_action || "",
      },
      communication_summary: realText(data.summary),
      transcript: callLog,
      edited: true,
    };
    noteStatus.textContent = "保存中…";
    try {
      const res = await fetch("/api/visit-notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await res.json();
      if (!res.ok || !body.ok) throw new Error(body.message || "保存失败");
      currentNote = body.record || payload;
      currentNoteId = body.note_id || currentNoteId;
      showViewMode();
      noteStatus.textContent = "";
    } catch (err) {
      noteStatus.textContent = err.message || String(err);
    }
  });

  if (callBtn) callBtn.addEventListener("click", startCall);
  Promise.all([loadEnums(), loadLead()])
    .then(() => setUI("idle"))
    .catch((err) => {
      console.error(err);
      setUI("idle");
    });
})();
