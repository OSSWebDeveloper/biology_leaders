// Test yechish ekrani: javoblar darhol serverga saqlanadi, vaqtni server belgilaydi
(function () {
  const root = document.getElementById('exam');
  const data = JSON.parse(document.getElementById('exam-data').textContent);
  const questions = data.questions;
  const tg = window.Telegram && window.Telegram.WebApp;
  const $ = id => document.getElementById(id);
  let index = 0;
  // Savol rasmi kattaligi: telefonda ayrim PDF matnlari mayda bo'ladi
  const SCALES = [100, 125, 150, 180, 220];
  let scale = 100;
  try { scale = SCALES.includes(Number(localStorage.getItem('q-scale'))) ? Number(localStorage.getItem('q-scale')) : 100; } catch (e) { /* yopiq */ }

  // Oxirgi ko'rilgan savolni eslab qolish (qulaylik uchun; bo'lmasa ham ishlaydi)
  const posKey = 'attempt-pos-' + root.dataset.attempt;
  try { index = Math.min(Number(localStorage.getItem(posKey)) || 0, questions.length - 1); } catch (e) { /* yopiq */ }

  if (tg && tg.initData && tg.isVersionAtLeast('6.2')) tg.enableClosingConfirmation();

  // ---------- Saqlash navbati ----------
  const pending = new Map();
  let sending = false;
  const state = $('save-state');

  function setState(text, isError) {
    state.textContent = text;
    state.classList.toggle('err', !!isError);
  }

  function queue(q) {
    pending.set(q.id, q.kind === 'open'
      ? { question: q.id, value_a: q.value_a, value_b: q.value_b }
      : { question: q.id, choice: q.choice });
    setState('Saqlanmoqda…');
    flush();
  }

  async function flush() {
    if (sending || !pending.size) return;
    sending = true;
    const [id, body] = pending.entries().next().value;
    try {
      const response = await fetch(root.dataset.saveUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
        body: JSON.stringify(body),
      });
      if (response.status === 409) { location.href = root.dataset.resultUrl; return; }
      if (!response.ok) throw new Error(response.status);
      if (pending.get(id) === body) pending.delete(id);
      const result = await response.json();
      deadline = Date.now() + result.seconds_left * 1000;
      setState(pending.size ? 'Saqlanmoqda…' : 'Saqlandi');
      sending = false;
      flush();
    } catch (error) {
      sending = false;
      setState('Internet yo\'q — javob saqlanmadi, qayta urinilmoqda', true);
      setTimeout(flush, 3000);
    }
  }
  window.addEventListener('online', flush);

  // ---------- Vaqt ----------
  let deadline = Date.now() + data.seconds_left * 1000;
  let finishing = false;
  const timer = $('timer');

  function tick() {
    const left = Math.max(0, Math.round((deadline - Date.now()) / 1000));
    const h = Math.floor(left / 3600), m = Math.floor(left % 3600 / 60), s = left % 60;
    timer.textContent = (h ? h + ':' : '') + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    timer.classList.toggle('low', left <= 300);
    if (left <= 0 && !finishing) {
      finishing = true;
      setState('Vaqt tugadi, yakunlanmoqda…');
      submitFinish();
    }
  }
  setInterval(tick, 1000);
  tick();

  function submitFinish() {
    if (tg && tg.initData && tg.isVersionAtLeast('6.2')) tg.disableClosingConfirmation();
    $('finish-form').submit();
  }

  // ---------- Savol ko'rsatish ----------
  const isDone = q => q.kind === 'open' ? !!(q.value_a || q.value_b) : !!q.choice;

  function esc(text) {
    const box = document.createElement('div');
    box.textContent = text;
    return box.innerHTML;
  }

  function math(element) {
    if (window.renderMathInElement) {
      renderMathInElement(element, { delimiters: [{ left: '$', right: '$', display: false }], throwOnError: false });
    }
  }

  function render() {
    const q = questions[index];
    try { localStorage.setItem(posKey, index); } catch (e) { /* yopiq */ }
    const typeLabel = { mcq: 'Bitta javobni tanlang', matching: 'Moslashtiring: A–F', open: 'Javobni yozing' }[q.kind];
    let html = `<div class="q-head"><span class="q-num">${q.number}-savol</span><span class="muted small">${typeLabel}</span>${q.image ? '<span class="zoom-btns"><button type="button" data-z="-1" aria-label="Kichraytirish">A−</button><button type="button" data-z="1" aria-label="Kattalashtirish">A+</button></span>' : ''}</div>`;
    html += '<div class="card qcard">';
    if (q.text) html += `<div class="qtext">${esc(q.text)}</div>`;
    if (q.image) html += `<div class="qscroll"><img class="qimg" src="${q.image}" alt="${q.number}-savol sharti" style="width:${scale}%"></div>`;
    if (!q.text && !q.image) html += '<p class="muted mb0">Savol guruhga yuborilgan faylda.</p>';
    html += '</div>';

    if (q.kind === 'open') {
      html += part(q, 'a', q.part_a) + (q.two_parts ? part(q, 'b', q.part_b) : '');
      html += '<div class="keys" id="keys">' + ['√', 'π', '/', '-', ','].map(k => `<button type="button" data-k="${k}">${k}</button>`).join('') + '</div>';
      html += '<p class="muted small mt mb0">Masalan: 2√5, 16/3, 8π, -1/16, 3,5</p>';
    } else {
      const listed = q.options && q.options.length;
      const cls = listed ? 'listed' : (q.letters.length > 4 ? 'six' : '');
      html += `<div class="opts ${cls}">` + [...q.letters].map((letter, i) =>
        `<button type="button" class="opt ${q.choice === letter ? 'on' : ''}" data-v="${letter}" aria-pressed="${q.choice === letter}">` +
        (listed ? `<b>${letter})</b> <span>${esc(q.options[i] || '')}</span>` : letter) + '</button>').join('') + '</div>';
    }
    const body = $('q-body');
    body.innerHTML = html;
    math(body);
    bind(q);
    $('prev').disabled = index === 0;
    $('next').textContent = index === questions.length - 1 ? 'Yakunlash' : 'Keyingi →';
    window.scrollTo(0, 0);
  }

  function part(q, name, text) {
    return `<div class="part card mb0"><label for="v-${name}">${q.two_parts ? `<b>${name})</b> ` : ''}${text ? esc(text) : (q.two_parts ? 'javob' : 'Javobingiz')}</label>
      <input id="v-${name}" data-part="${name}" value="${esc(q['value_' + name]).replace(/"/g, '&quot;')}" maxlength="64"
        autocomplete="off" autocapitalize="off" spellcheck="false" inputmode="text"></div>`;
  }

  function bind(q) {
    const body = $('q-body');
    body.querySelectorAll('.opt').forEach(button => button.addEventListener('click', () => {
      q.choice = q.choice === button.dataset.v ? '' : button.dataset.v;
      body.querySelectorAll('.opt').forEach(b => {
        const on = b.dataset.v === q.choice;
        b.classList.toggle('on', on);
        b.setAttribute('aria-pressed', on);
      });
      if (tg && tg.HapticFeedback && tg.isVersionAtLeast('6.1')) tg.HapticFeedback.selectionChanged();
      queue(q);
      drawGrid();
    }));

    let timerId, lastInput = body.querySelector('input[data-part]');
    body.querySelectorAll('input[data-part]').forEach(input => {
      input.addEventListener('focus', () => { lastInput = input; });
      input.addEventListener('input', () => {
        q['value_' + input.dataset.part] = input.value.trim();
        clearTimeout(timerId);
        timerId = setTimeout(() => queue(q), 500);
        drawGrid();
      });
      input.addEventListener('blur', () => { clearTimeout(timerId); queue(q); });
    });
    const keys = $('keys');
    if (keys) keys.addEventListener('mousedown', e => e.preventDefault()); // fokus inputda qolsin
    if (keys) keys.addEventListener('click', event => {
      const key = event.target.dataset.k;
      if (!key || !lastInput) return;
      const start = lastInput.selectionStart == null ? lastInput.value.length : lastInput.selectionStart;  // «??» eski WebView'da ishlamaydi
      const end = lastInput.selectionEnd == null ? start : lastInput.selectionEnd;
      lastInput.setRangeText(key, start, end, 'end');
      lastInput.focus();
      lastInput.dispatchEvent(new Event('input'));
    });

    body.querySelectorAll('[data-z]').forEach(button => button.addEventListener('click', () => {
      const next = SCALES[SCALES.indexOf(scale) + Number(button.dataset.z)];
      if (!next) return;
      scale = next;
      body.querySelector('.qimg').style.width = scale + '%';
      try { localStorage.setItem('q-scale', scale); } catch (e) { /* yopiq */ }
    }));

    const image = body.querySelector('.qimg');
    if (image) image.addEventListener('click', () => {
      $('zoom-img').src = image.src;
      $('zoom-img').alt = image.alt;
      $('zoom').classList.add('open');
    });
  }

  // ---------- Javoblar varag'i: savollar faylda bo'lsa hammasi bitta sahifada ----------
  const sheetMode = questions.every(q => !q.text && !q.image);

  function renderSheet() {
    let html = '';
    let kind = null;
    questions.forEach((q, i) => {
      if (q.kind !== kind) {
        if (kind) html += '<div class="sec-gap"></div>';
        kind = q.kind;
        if (kind === 'open') {
          html += '<div class="keys sheet-keys" id="keys">' + ['√', 'π', '/', '-', ','].map(k => `<button type="button" data-k="${k}">${k}</button>`).join('') + '</div>';
        }
      }
      html += `<div class="row" data-i="${i}"><span class="row-num">${q.number}</span>`;
      if (q.kind === 'open') {
        html += '<div class="row-inputs">' + (q.two_parts ? ['a', 'b'] : ['a']).map(name =>
          `<input data-part="${name}" value="${esc(q['value_' + name]).replace(/"/g, '&quot;')}" maxlength="64" placeholder="${q.two_parts ? name + ')' : 'javob'}"
            aria-label="${q.number}-savol ${q.two_parts ? name + ') ' : ''}javobi" autocomplete="off" autocapitalize="off" spellcheck="false">`).join('') + '</div>';
      } else {
        html += `<div class="opts ${q.letters.length > 4 ? 'six' : ''}">` + [...q.letters].map(letter =>
          `<button type="button" class="opt ${q.choice === letter ? 'on' : ''}" data-v="${letter}" aria-pressed="${q.choice === letter}" aria-label="${q.number}-savol ${letter}">${letter}</button>`).join('') + '</div>';
      }
      html += '</div>';
    });
    const body = $('q-body');
    body.classList.add('answer-sheet');
    body.innerHTML = html;
    body.querySelectorAll('.row').forEach(row => bindRow(row, questions[Number(row.dataset.i)]));

    let lastInput = body.querySelector('input[data-part]');
    body.addEventListener('focusin', e => { if (e.target.matches('input[data-part]')) lastInput = e.target; });
    const keys = $('keys');
    if (keys) {
      keys.addEventListener('mousedown', e => e.preventDefault());
      keys.addEventListener('click', event => {
        const key = event.target.dataset.k;
        if (!key || !lastInput) return;
        const start = lastInput.selectionStart == null ? lastInput.value.length : lastInput.selectionStart;  // «??» eski WebView'da ishlamaydi
        const end = lastInput.selectionEnd == null ? start : lastInput.selectionEnd;
        lastInput.setRangeText(key, start, end, 'end');
        lastInput.focus();
        lastInput.dispatchEvent(new Event('input'));
      });
    }
    $('prev').hidden = true;
    $('grid-btn').hidden = true;
    $('next').textContent = 'Testni yakunlash';
  }

  function bindRow(row, q) {
    row.querySelectorAll('.opt').forEach(button => button.addEventListener('click', () => {
      q.choice = q.choice === button.dataset.v ? '' : button.dataset.v;
      row.querySelectorAll('.opt').forEach(b => {
        const on = b.dataset.v === q.choice;
        b.classList.toggle('on', on);
        b.setAttribute('aria-pressed', on);
      });
      if (tg && tg.HapticFeedback && tg.isVersionAtLeast('6.1')) tg.HapticFeedback.selectionChanged();
      queue(q);
      drawGrid();
    }));
    let timerId;
    row.querySelectorAll('input[data-part]').forEach(input => {
      input.addEventListener('input', () => {
        q['value_' + input.dataset.part] = input.value.trim();
        clearTimeout(timerId);
        timerId = setTimeout(() => queue(q), 500);
        drawGrid();
      });
      input.addEventListener('blur', () => { clearTimeout(timerId); queue(q); });
    });
  }

  // ---------- Savollar to'ri ----------
  const sheet = $('sheet');

  function drawGrid() {
    const grid = $('num-grid');
    grid.innerHTML = questions.map((q, i) =>
      `<button type="button" class="num ${isDone(q) ? 'done' : ''} ${i === index ? 'now' : ''}" data-i="${i}">${q.number}</button>`).join('');
    const done = questions.filter(isDone).length;
    $('progress').textContent = `${done} / ${questions.length}`;
    $('sheet-summary').textContent = done === questions.length
      ? 'Barcha savollarga javob berdingiz.'
      : `Javobsiz: ${questions.length - done} ta. Noto'g'ri javob uchun ball ayirilmaydi.`;
  }

  function go(next) {
    index = next;
    render();
    drawGrid();
  }

  $('num-grid').addEventListener('click', event => {
    const i = event.target.dataset.i;
    if (i !== undefined) { sheet.classList.remove('open'); go(Number(i)); }
  });
  $('grid-btn').addEventListener('click', () => { drawGrid(); sheet.classList.add('open'); });
  sheet.addEventListener('click', event => { if (event.target === sheet) sheet.classList.remove('open'); });
  $('zoom-close').addEventListener('click', () => $('zoom').classList.remove('open'));
  $('prev').addEventListener('click', () => index > 0 && go(index - 1));
  $('next').addEventListener('click', () => {
    if (sheetMode) $('finish-btn').click();
    else if (index < questions.length - 1) go(index + 1);
    else { drawGrid(); sheet.classList.add('open'); }
  });
  $('finish-btn').addEventListener('click', () => {
    const left = questions.length - questions.filter(isDone).length;
    const text = left ? `${left} ta savol javobsiz. Testni yakunlaysizmi?` : 'Testni yakunlaysizmi?';
    askConfirm(text, () => {
      if (!pending.size) return submitFinish();
      flush();
      setState('Javoblar saqlanmoqda…');
      const wait = setInterval(() => {
        if (!pending.size) { clearInterval(wait); submitFinish(); }
      }, 300);
      setTimeout(() => { clearInterval(wait); setState('Saqlanmagan javoblar bor, internetni tekshiring', true); }, 15000);
    });
  });

  if (sheetMode) renderSheet(); else render();
  drawGrid();
})();
