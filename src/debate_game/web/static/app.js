const form = document.querySelector("#debateForm");
const motionInput = document.querySelector("#motion");
const maxRoundsInput = document.querySelector("#maxRounds");
const startButton = document.querySelector("#startButton");
const cancelButton = document.querySelector("#cancelButton");
const formMessage = document.querySelector("#formMessage");
const connectionBadge = document.querySelector("#connectionBadge");
const connectionText = document.querySelector("#connectionText");
const emptyState = document.querySelector("#emptyState");
const motionCard = document.querySelector("#motionCard");
const motionText = document.querySelector("#motionText");
const roundText = document.querySelector("#roundText");
const timeline = document.querySelector("#timeline");
const resultCard = document.querySelector("#resultCard");
const resultWinner = document.querySelector("#resultWinner");
const resultMeta = document.querySelector("#resultMeta");
const bubbleTemplate = document.querySelector("#bubbleTemplate");

const roleNames = {
  pro: "正方 · Affirmative",
  con: "反方 · Negative",
  judge: "裁判 · Judge",
};
const roleInitials = { pro: "正", con: "反", judge: "裁" };
const eventNames = [
  "debate_started",
  "thinking_started",
  "speech_started",
  "content_delta",
  "speech_finished",
  "generation_failed",
  "retrying",
  "cancellation_requested",
  "debate_finished",
  "debate_failed",
  "debate_cancelled",
];

let sessionId = null;
let eventSource = null;
let terminal = true;
let scrollQueued = false;
const bubbles = new Map();

function setConnection(state, text) {
  connectionBadge.dataset.state = state;
  connectionText.textContent = text;
}

function setRunning(running) {
  startButton.disabled = running;
  cancelButton.disabled = !running;
  motionInput.disabled = running;
  maxRoundsInput.disabled = running;
}

function resetArena() {
  timeline.replaceChildren();
  bubbles.clear();
  resultCard.classList.add("hidden");
  emptyState.classList.add("hidden");
  motionCard.classList.remove("hidden");
  formMessage.textContent = "";
}

function bubbleKey(role, round) {
  return `${role}:${round ?? "final"}`;
}

function scheduleScroll(element) {
  if (scrollQueued) return;
  scrollQueued = true;
  requestAnimationFrame(() => {
    element.scrollIntoView({ behavior: "auto", block: "end" });
    scrollQueued = false;
  });
}

function ensureBubble(role, round) {
  const key = bubbleKey(role, round);
  if (bubbles.has(key)) return bubbles.get(key);

  const fragment = bubbleTemplate.content.cloneNode(true);
  const turn = fragment.querySelector(".turn");
  turn.dataset.role = role;
  turn.dataset.round = round ?? "final";
  turn.classList.add(role);
  turn.querySelector(".avatar").textContent = roleInitials[role] ?? "AI";
  turn.querySelector(".speaker").textContent = roleNames[role] ?? role;
  turn.querySelector(".round-label").textContent =
    role === "judge" ? "终局裁决" : `第 ${round} 轮`;
  timeline.append(fragment);
  const inserted = timeline.lastElementChild;
  bubbles.set(key, inserted);
  inserted.scrollIntoView({ behavior: "smooth", block: "end" });
  return inserted;
}

function finishTerminal(state, statusText) {
  terminal = true;
  setRunning(false);
  setConnection(state, statusText);
  localStorage.removeItem("debateSessionId");
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

function handleEvent(name, data) {
  if (name === "debate_started") {
    motionText.textContent = data.motion;
    roundText.textContent = `最多 ${data.max_rounds} 轮`;
    setConnection("live", "辩论进行中");
    return;
  }

  if (name === "thinking_started") {
    const turn = ensureBubble(data.role, data.round);
    turn.classList.add("thinking-active");
    turn.querySelector(".thinking-label").textContent =
      data.role === "judge" ? "正在评议全部交锋…" : "正在组织论点…";
    return;
  }

  if (name === "speech_started") {
    const turn = ensureBubble(data.role, data.round);
    turn.classList.remove("thinking-active");
    turn.classList.add("speaking");
    turn.querySelector(".thinking").classList.add("hidden");
    turn.querySelector(".turn-meta").textContent =
      `思考 ${Number(data.thinking_seconds).toFixed(1)} 秒`;
    return;
  }

  if (name === "content_delta") {
    const turn = ensureBubble(data.role, data.round);
    turn.querySelector(".speech").append(document.createTextNode(data.text));
    scheduleScroll(turn);
    return;
  }

  if (name === "speech_finished") {
    const turn = ensureBubble(data.role, data.round);
    turn.classList.remove("speaking", "thinking-active");
    turn.classList.add("complete");
    turn.querySelector(".turn-meta").textContent =
      `完成于 ${Number(data.elapsed_seconds).toFixed(1)} 秒`;
    return;
  }

  if (name === "retrying") {
    const turn = ensureBubble(data.role, data.round);
    turn.querySelector(".thinking-label").textContent =
      `请求失败，正在重试（${data.attempt}/${data.total_attempts}）…`;
    return;
  }

  if (name === "cancellation_requested") {
    setConnection("pending", "正在停止");
    formMessage.textContent = "已发送停止请求，等待当前模型流结束。";
    cancelButton.disabled = true;
    return;
  }

  if (name === "debate_finished") {
    resultCard.classList.remove("hidden");
    const winner = data.winner === "pro" ? "正方获胜" : "反方获胜";
    const reason = data.reason === "concession" ? "对方主动认输" : "裁判终局裁决";
    resultWinner.textContent = winner;
    resultMeta.textContent =
      `${reason} · ${data.completed_rounds} 个完整轮回 · ` +
      `${Number(data.elapsed_seconds).toFixed(1)} 秒`;
    resultCard.scrollIntoView({ behavior: "smooth", block: "center" });
    finishTerminal("done", "辩论已结束");
    return;
  }

  if (name === "debate_failed") {
    resultCard.classList.remove("hidden");
    resultWinner.textContent = "对局失败";
    resultMeta.textContent = data.message || "模型服务返回了无法处理的响应。";
    finishTerminal("error", "对局失败");
    return;
  }

  if (name === "debate_cancelled") {
    resultCard.classList.remove("hidden");
    resultWinner.textContent = "对局已停止";
    resultMeta.textContent = "本次对局由用户主动终止。";
    finishTerminal("idle", "已停止");
  }
}

function connectEvents(id) {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/api/debates/${id}/events`);
  for (const name of eventNames) {
    eventSource.addEventListener(name, (event) => {
      try {
        handleEvent(name, JSON.parse(event.data));
      } catch (error) {
        console.error("Unable to process debate event", name, error);
      }
    });
  }
  eventSource.onopen = () => setConnection("live", "实时连接正常");
  eventSource.onerror = () => {
    if (!terminal) setConnection("pending", "正在重新连接");
  };
}

async function readError(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // Fall through to a generic message.
  }
  return `请求失败（HTTP ${response.status}）`;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const motion = motionInput.value.trim();
  const maxRounds = Number(maxRoundsInput.value);
  if (!motion) {
    formMessage.textContent = "请输入辩题。";
    motionInput.focus();
    return;
  }

  resetArena();
  terminal = false;
  setRunning(true);
  setConnection("pending", "正在创建对局");
  motionText.textContent = motion;
  roundText.textContent = `最多 ${maxRounds} 轮`;

  try {
    const response = await fetch("/api/debates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ motion, max_rounds: maxRounds }),
    });
    if (!response.ok) throw new Error(await readError(response));
    const session = await response.json();
    sessionId = session.id;
    localStorage.setItem("debateSessionId", sessionId);
    connectEvents(sessionId);
  } catch (error) {
    formMessage.textContent = error.message;
    finishTerminal("error", "启动失败");
  }
});

cancelButton.addEventListener("click", async () => {
  if (!sessionId || terminal) return;
  cancelButton.disabled = true;
  try {
    const response = await fetch(`/api/debates/${sessionId}/cancel`, { method: "POST" });
    if (!response.ok) throw new Error(await readError(response));
  } catch (error) {
    formMessage.textContent = error.message;
    cancelButton.disabled = false;
  }
});

async function resumePreviousSession() {
  const previousId = localStorage.getItem("debateSessionId");
  if (!previousId) return;
  try {
    const response = await fetch(`/api/debates/${previousId}`);
    if (!response.ok) {
      localStorage.removeItem("debateSessionId");
      return;
    }
    const session = await response.json();
    resetArena();
    sessionId = previousId;
    terminal = false;
    motionInput.value = session.motion;
    maxRoundsInput.value = session.max_rounds;
    motionText.textContent = session.motion;
    roundText.textContent = `最多 ${session.max_rounds} 轮`;
    setRunning(!["finished", "failed", "cancelled"].includes(session.status));
    connectEvents(previousId);
  } catch {
    localStorage.removeItem("debateSessionId");
  }
}

resumePreviousSession();
