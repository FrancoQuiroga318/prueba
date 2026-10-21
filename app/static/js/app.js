// JavaScript nativo para las pantallas de estudio, tarjetas y examen.

const $ = (sel) => document.querySelector(sel);

async function api(url, options = {}) {
  const opts = { ...options };
  if (opts.body !== undefined) {
    opts.method = opts.method || "POST";
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "Error en la solicitud";
    throw new Error(detail);
  }
  return data;
}

function refText(q) {
  return `Referencia: página ${q.page} del PDF${q.from_image ? " (contenido de un diagrama)" : ""}`;
}

function show(el, visible = true) { el.hidden = !visible; }

function shuffle(list) {
  const a = list.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function setUnitInUrl(unit) {
  const url = new URL(location.href);
  if (unit) url.searchParams.set("unidad", unit); else url.searchParams.delete("unidad");
  history.replaceState(null, "", url);
}

// --- Estudiar / Repaso -------------------------------------------------------

function initStudy() {
  const root = $("#study");
  const mode = root.dataset.mode;
  const card = $("#study-card");
  const answerBox = $("#answer-box");
  let queue = [];
  let index = 0;
  let requeued = new Set();
  let tally = { no: 0, parcial: 0, bien: 0 };

  async function start() {
    const unit = $("#unit-select").value;
    setUnitInUrl(unit);
    const params = new URLSearchParams();
    if (unit) params.set("unit_id", unit);
    const url = (mode === "repaso" ? "/api/review" : "/api/questions") + "?" + params;
    try {
      queue = await api(url);
    } catch (err) {
      return showEmpty(err.message);
    }
    index = 0;
    requeued = new Set();
    tally = { no: 0, parcial: 0, bien: 0 };
    show($("#study-done"), false);
    if (!queue.length) {
      return showEmpty(mode === "repaso"
        ? "¡No tenés preguntas pendientes de repaso! Estudiá preguntas nuevas o volvé más tarde."
        : "No hay preguntas para esta selección.");
    }
    show($("#study-empty"), false);
    render();
  }

  function showEmpty(msg) {
    show(card, false);
    $("#study-empty").textContent = msg;
    show($("#study-empty"));
  }

  function render() {
    const q = queue[index];
    show(card);
    show(answerBox, false);
    show($("#reveal-btn"));
    $("#q-counter").textContent = `Pregunta ${index + 1} de ${queue.length}`;
    $("#q-type").textContent = q.type_label;
    $("#q-status").textContent = q.status_label;
    $("#q-topic").textContent = `${q.unit_title} · ${q.topic}`;
    $("#q-text").textContent = q.question;
    $("#user-answer").value = "";
    $("#user-answer").disabled = false;
    $("#user-answer").focus();
  }

  function reveal() {
    const q = queue[index];
    $("#q-answer").textContent = q.answer;
    $("#q-ref").textContent = refText(q);
    $("#user-answer").disabled = true;
    show($("#reveal-btn"), false);
    show(answerBox);
  }

  async function grade(result) {
    const q = queue[index];
    const buttons = answerBox.querySelectorAll("[data-result]");
    buttons.forEach((b) => (b.disabled = true));
    try {
      const saved = await api("/api/answers", {
        body: { question_id: q.id, result, user_answer: $("#user-answer").value, mode },
      });
      tally[result]++;
      // Si no la recordó, vuelve a aparecer una vez al final de esta sesión.
      if (result === "no" && !requeued.has(q.id)) {
        requeued.add(q.id);
        queue.push({ ...q, status: saved.status, status_label: saved.status_label });
      }
      index++;
      if (index < queue.length) render(); else finish();
    } catch (err) {
      alert("No se pudo guardar la respuesta: " + err.message);
    } finally {
      buttons.forEach((b) => (b.disabled = false));
    }
  }

  function finish() {
    show(card, false);
    $("#done-summary").textContent =
      `Respondiste ${tally.no + tally.parcial + tally.bien} preguntas: ` +
      `${tally.bien} bien, ${tally.parcial} parciales y ${tally.no} sin recordar.`;
    show($("#study-done"));
  }

  $("#study-setup").addEventListener("submit", (e) => { e.preventDefault(); start(); });
  $("#reveal-btn").addEventListener("click", reveal);
  answerBox.querySelectorAll("[data-result]").forEach((b) =>
    b.addEventListener("click", () => grade(b.dataset.result)));
  $("#restart-btn").addEventListener("click", start);

  // En repaso, o si se eligió una unidad desde otra pantalla, se empieza directamente.
  if (mode === "repaso" || root.dataset.unit) start();
}

// --- Tarjetas ------------------------------------------------------------------

function initFlashcards() {
  const root = $("#flashcards");
  let cards = [];
  let index = 0;
  let tally = { no: 0, parcial: 0, bien: 0 };

  async function start() {
    const unit = $("#unit-select").value;
    setUnitInUrl(unit);
    try {
      cards = await api("/api/flashcards" + (unit ? "?unit_id=" + encodeURIComponent(unit) : ""));
    } catch (err) {
      $("#cards-empty").textContent = err.message;
      return show($("#cards-empty"));
    }
    if ($("#shuffle").checked) cards = shuffle(cards);
    index = 0;
    tally = { no: 0, parcial: 0, bien: 0 };
    show($("#cards-done"), false);
    show($("#cards-empty"), !cards.length);
    $("#cards-empty").textContent = "No hay tarjetas para esta selección.";
    if (cards.length) render();
  }

  function render() {
    const c = cards[index];
    show($("#card-area"));
    $("#c-counter").textContent = `Tarjeta ${index + 1} de ${cards.length}`;
    $("#c-status").textContent = c.status_label;
    $("#c-topic").textContent = `${c.unit_title} · ${c.topic}`;
    $("#c-front").textContent = c.front;
    $("#c-back").textContent = c.back;
    $("#c-ref").textContent = refText(c);
    show($("#flashcard .front"));
    show($("#flashcard .back"), false);
    show($("#flip-btn"));
    $("#flip-btn").textContent = "Dar vuelta";
    show($("#card-grade"), false);
    $("#card-tally").textContent = `Bien: ${tally.bien} · Parcial: ${tally.parcial} · No: ${tally.no}`;
  }

  function flip() {
    show($("#flashcard .back"));
    show($("#flip-btn"), false);
    show($("#card-grade"));
  }

  async function grade(result) {
    const c = cards[index];
    try {
      await api("/api/answers", { body: { question_id: c.id, result, mode: "tarjetas" } });
    } catch (err) {
      return alert("No se pudo guardar: " + err.message);
    }
    tally[result]++;
    index++;
    if (index < cards.length) return render();
    show($("#card-area"), false);
    $("#cards-summary").textContent =
      `Recordaste bien ${tally.bien}, parcialmente ${tally.parcial} y no recordaste ${tally.no} tarjetas.`;
    show($("#cards-done"));
  }

  $("#cards-setup").addEventListener("submit", (e) => { e.preventDefault(); start(); });
  $("#flip-btn").addEventListener("click", flip);
  $("#flashcard").addEventListener("click", () => { if (!$("#flip-btn").hidden) flip(); });
  $("#card-grade").querySelectorAll("[data-result]").forEach((b) =>
    b.addEventListener("click", () => grade(b.dataset.result)));
  $("#cards-restart").addEventListener("click", start);

  if (root.dataset.unit) start();
}

// --- Examen ------------------------------------------------------------------

function initExam() {
  const unitBoxes = () => [...document.querySelectorAll('input[name="unit"]')];
  let exam = null;
  let answers = [];
  let index = 0;
  let evaluations = {};

  $("#all-units").addEventListener("change", (e) =>
    unitBoxes().forEach((b) => (b.checked = e.target.checked)));
  unitBoxes().forEach((b) => b.addEventListener("change", () => {
    $("#all-units").checked = unitBoxes().every((x) => x.checked);
  }));

  async function start(e) {
    e.preventDefault();
    const unitIds = unitBoxes().filter((b) => b.checked).map((b) => b.value);
    const error = $("#exam-error");
    if (!unitIds.length) {
      error.textContent = "Elegí al menos una unidad.";
      return show(error);
    }
    try {
      exam = await api("/api/exams", { body: { unit_ids: unitIds, count: Number($("#exam-count").value) } });
    } catch (err) {
      error.textContent = err.message;
      return show(error);
    }
    show(error, false);
    answers = exam.questions.map(() => "");
    index = 0;
    evaluations = {};
    show($("#exam-setup"), false);
    renderQuestion();
  }

  function renderQuestion() {
    const q = exam.questions[index];
    show($("#exam-question"));
    $("#e-counter").textContent = `Pregunta ${index + 1} de ${exam.total}`;
    $("#e-type").textContent = q.type_label;
    $("#e-unit").textContent = `${q.unit_title} · ${q.topic}`;
    $("#e-text").textContent = q.question;
    $("#e-answer").value = answers[index];
    $("#e-prev").disabled = index === 0;
    $("#e-next").textContent = index === exam.total - 1 ? "Terminar examen" : "Siguiente";
    $("#e-answer").focus();
  }

  function saveCurrent() { answers[index] = $("#e-answer").value; }

  async function next() {
    saveCurrent();
    if (index < exam.total - 1) {
      index++;
      return renderQuestion();
    }
    if (!confirm("¿Terminar el examen y ver las respuestas correctas?")) return;
    try {
      const data = await api(`/api/exams/${exam.exam_id}/finish`, {
        body: { answers: exam.questions.map((q, i) => ({ question_id: q.id, user_answer: answers[i] })) },
      });
      renderReview(data.questions);
    } catch (err) {
      alert("No se pudo entregar el examen: " + err.message);
    }
  }

  function renderReview(questions) {
    show($("#exam-question"), false);
    const list = $("#review-list");
    list.innerHTML = "";
    questions.forEach((q) => {
      const li = document.createElement("li");
      li.innerHTML = `
        <div class="card">
          <p class="muted small"></p>
          <p class="question"></p>
          <p><strong>Tu respuesta:</strong></p>
          <div class="user-answer"></div>
          <p><strong>Respuesta esperada:</strong></p>
          <div class="answer"></div>
          <p class="ref"></p>
          <div class="grade-buttons">
            <button class="btn btn-no" data-result="no" type="button">No la recordé</button>
            <button class="btn btn-partial" data-result="parcial" type="button">Parcialmente</button>
            <button class="btn btn-ok" data-result="bien" type="button">La recordé bien</button>
          </div>
        </div>`;
      li.querySelector(".muted").textContent = `${q.unit_title} · ${q.topic}`;
      li.querySelector(".question").textContent = q.question;
      li.querySelector(".user-answer").textContent = q.user_answer || "(sin respuesta)";
      li.querySelector(".answer").textContent = q.answer;
      li.querySelector(".ref").textContent = refText(q);
      li.querySelectorAll("[data-result]").forEach((b) => b.addEventListener("click", () => {
        evaluations[q.id] = b.dataset.result;
        li.querySelectorAll("[data-result]").forEach((x) => x.classList.toggle("selected", x === b));
      }));
      list.appendChild(li);
    });
    show($("#exam-review"));
    window.scrollTo(0, 0);
  }

  async function grade() {
    const missing = exam.questions.filter((q) => !evaluations[q.id]).length;
    const error = $("#grade-error");
    if (missing) {
      error.textContent = `Te falta evaluar ${missing} ${missing === 1 ? "pregunta" : "preguntas"}.`;
      return show(error);
    }
    show(error, false);
    try {
      const r = await api(`/api/exams/${exam.exam_id}/grade`, {
        body: { results: exam.questions.map((q) => ({ question_id: q.id, result: evaluations[q.id] })) },
      });
      renderResult(r);
    } catch (err) {
      error.textContent = err.message;
      show(error);
    }
  }

  function renderResult(r) {
    show($("#exam-review"), false);
    const num = (n) => n.toLocaleString("es-AR");
    $("#r-score").textContent = `${num(r.percentage)}%  (${num(r.score)} / ${r.total})`;
    $("#r-counts").textContent =
      `Bien: ${r.counts.bien} · Parcial: ${r.counts.parcial} · No recordadas: ${r.counts.no}`;
    const units = $("#r-units");
    units.innerHTML = "";
    r.by_unit.forEach((u) => {
      const li = document.createElement("li");
      li.textContent = `${u.unit_title}: ${num(u.percentage)}% (${num(u.score)} / ${u.total})`;
      units.appendChild(li);
    });
    const topics = $("#r-topics");
    topics.innerHTML = "";
    if (!r.topics_to_review.length) {
      topics.innerHTML = "<li>¡Excelente! No hay temas pendientes en este examen.</li>";
    }
    r.topics_to_review.forEach((t) => {
      const li = document.createElement("li");
      const pages = (t.pages.length === 1 ? "pág. " : "págs. ") + t.pages.join(", ");
      li.textContent = `${t.unit_title} — ${t.topic} (${pages})`;
      topics.appendChild(li);
    });
    show($("#exam-result"));
    window.scrollTo(0, 0);
  }

  function reset() {
    show($("#exam-result"), false);
    show($("#exam-setup"));
    exam = null;
  }

  $("#exam-setup").addEventListener("submit", start);
  $("#e-next").addEventListener("click", next);
  $("#e-prev").addEventListener("click", () => { saveCurrent(); index--; renderQuestion(); });
  $("#grade-btn").addEventListener("click", grade);
  $("#new-exam").addEventListener("click", reset);
}

document.addEventListener("DOMContentLoaded", () => {
  if ($("#study")) initStudy();
  if ($("#flashcards")) initFlashcards();
  if ($("#exam")) initExam();
});
