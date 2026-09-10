'use strict';
const $ = id => document.getElementById(id);
const labels = {good: 'Looks good', redo: '3D redo', unsure: 'Unsure'};
let icons = [], reviews = {}, token, activeId, inspectionIds = [], timer, saving = false;
let pending = new Map();
const cards = new Map();
const draftKey = 'fomo-icon-review-pending-v1';

function changed(icon) {
  return reviews[icon.id] && reviews[icon.id].source_sha256 !== icon.sha256;
}
function statusOf(icon) {
  return changed(icon) ? 'unreviewed' : (reviews[icon.id]?.status || 'unreviewed');
}
function saveMessage(message, error = false) {
  $('save-state').textContent = message;
  $('save-state').classList.toggle('error', error);
  $('detail-save-state').textContent = message;
  $('retry').hidden = !error;
}
function persistDrafts() {
  try { localStorage.setItem(draftKey, JSON.stringify([...pending])); }
  catch { saveMessage('Browser backup unavailable; keep this page open until saved.', true); }
}
function edit(icon, patch) {
  reviews[icon.id] = {...reviews[icon.id], status: statusOf(icon), notes: reviews[icon.id]?.notes || '',
    ...patch, source_sha256: icon.sha256};
  pending.set(icon.id, {id: icon.id, sha256: icon.sha256,
    status: reviews[icon.id].status, notes: reviews[icon.id].notes});
  persistDrafts();
  saveMessage('Saving feedback…');
  updateCard(icon);
  if (activeId === icon.id) updateDetailChoices(icon);
  updateProgress();
  clearTimeout(timer);
  timer = setTimeout(flush, 300);
}
async function flush() {
  if (saving) return;
  saving = true;
  try {
    while (pending.size) {
      const [id, draft] = pending.entries().next().value;
      const response = await fetch('/api/feedback', {method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Viewer-Token': token}, body: JSON.stringify(draft)});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Save failed');
      if (pending.get(id) === draft) {
        pending.delete(id);
        reviews[id] = result;
      }
      persistDrafts();
    }
    saveMessage('All feedback saved on this computer.');
  } catch (error) {
    saveMessage(`Not saved yet — ${error.message}. Retry when connected.`, true);
  } finally { saving = false; }
}
function updateProgress() {
  const count = status => icons.filter(i => statusOf(i) === status).length;
  $('progress').textContent = `${icons.length - count('unreviewed')} / ${icons.length} reviewed · ${count('redo')} flagged for 3D redo · ${count('unsure')} unsure`;
}
function visibleIcons() {
  const query = $('search').value.toLowerCase().trim();
  const filter = $('filter').value;
  const selected = icons.filter(i => {
    const matches = [i.label, i.id, i.use_for || ''].join(' ').toLowerCase().includes(query);
    return matches && (filter === 'all' || filter === statusOf(i)
      || (filter === 'notes' && reviews[i.id]?.notes?.trim())
      || (filter === 'changed' && changed(i)) || (filter === 'prototype' && i.kind === 'prototype'));
  });
  if ($('sort').value === 'name') selected.sort((a, b) => a.label.localeCompare(b.label));
  if ($('sort').value === 'size') selected.sort((a, b) => b.raw_bytes - a.raw_bytes);
  return selected;
}
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function picture(icon, size) {
  const img = element('img');
  img.src = icon.url;
  img.alt = icon.label;
  img.width = size;
  img.height = size;
  return img;
}
function samples(icon) {
  const row = element('div', 'sizes');
  for (const size of [16, 24, 32]) {
    const sample = element('div', 'size-sample');
    sample.append(picture(icon, size), element('span', '', `${size} px`));
    row.append(sample);
  }
  return row;
}
function choices(icon) {
  const row = element('div', 'choices');
  for (const [status, label] of Object.entries(labels)) {
    const button = element('button', '', label);
    button.dataset.status = status;
    button.setAttribute('aria-label', `${label}: ${icon.label}`);
    button.onclick = () => edit(icon, {status});
    row.append(button);
  }
  return row;
}
function markChoices(row, icon) {
  for (const button of row.querySelectorAll('button[data-status]')) {
    button.setAttribute('aria-pressed', String(button.dataset.status === statusOf(icon)));
  }
}
function updateCard(icon) {
  const card = cards.get(icon.id);
  if (!card) return;
  card.dataset.status = statusOf(icon);
  markChoices(card, icon);
  const line = card.querySelector('.review-line');
  line.classList.toggle('changed', !!changed(icon));
  line.firstChild.textContent = changed(icon) ? 'Artwork changed · review again' : labels[statusOf(icon)] || 'Unreviewed';
  line.querySelector('button').hidden = statusOf(icon) === 'unreviewed';
  const notes = card.querySelector('textarea');
  if (document.activeElement !== notes) notes.value = reviews[icon.id]?.notes || '';
}
function render() {
  const visible = visibleIcons();
  cards.clear();
  $('gallery').replaceChildren();
  $('result-count').textContent = `${visible.length} icons shown · ${icons.filter(i => i.kind === 'catalog').length} catalog icons + ${icons.filter(i => i.kind === 'prototype').length} prototype · click artwork to inspect`;
  $('empty').hidden = visible.length > 0;
  for (const icon of visible) {
    const card = element('article', 'card');
    card.dataset.id = icon.id;
    const top = element('div', 'card-top');
    top.append(element('span', 'badge', icon.kind === 'prototype' ? 'Prototype' : 'Custom'),
      element('span', '', `${(icon.raw_bytes / 1000).toFixed(1)} KB`));
    const art = element('button', 'art-button');
    art.setAttribute('aria-label', `Inspect ${icon.label}`);
    art.append(picture(icon, 144));
    art.onclick = () => { inspectionIds = visible.map(i => i.id); openDetail(icon.id); };
    const body = element('div', 'card-body');
    const reviewLine = element('div', 'review-line');
    const undo = element('button', 'undo', 'Undo rating');
    undo.onclick = () => edit(icon, {status: 'unreviewed'});
    reviewLine.append(element('span'), undo);
    const noteLabel = element('label', 'note-label', 'Notes');
    const notes = element('textarea');
    notes.rows = 2;
    notes.maxLength = 10000;
    notes.placeholder = 'What looks wrong?';
    notes.setAttribute('aria-label', `Notes for ${icon.label}`);
    notes.value = reviews[icon.id]?.notes || '';
    notes.oninput = () => edit(icon, {notes: notes.value});
    noteLabel.append(notes);
    body.append(element('h2', '', icon.label), element('p', 'icon-id', icon.id), samples(icon),
      choices(icon), reviewLine, noteLabel);
    card.append(top, art, body);
    cards.set(icon.id, card);
    $('gallery').append(card);
    updateCard(icon);
  }
  updateProgress();
}
function updateDetailChoices(icon) { markChoices($('detail-choices'), icon); }
function openDetail(id) {
  activeId = id;
  const icon = icons.find(i => i.id === id);
  const index = inspectionIds.indexOf(id);
  $('detail-title').textContent = icon.label;
  $('detail-position').textContent = `Inspect artwork · ${index + 1} of ${inspectionIds.length}`;
  $('detail-art').replaceChildren(picture(icon, 320));
  $('detail-sizes').replaceChildren(...samples(icon).children);
  $('detail-meta').textContent = `${icon.id} · ${(icon.raw_bytes / 1000).toFixed(2)} KB raw / ${(icon.gzip_bytes / 1000).toFixed(2)} KB gzip`;
  $('detail-choices').replaceChildren(...choices(icon).children);
  updateDetailChoices(icon);
  $('detail-notes').value = reviews[id]?.notes || '';
  $('detail-notes').oninput = () => edit(icon, {notes: $('detail-notes').value});
  $('prev').disabled = index <= 0;
  $('next').disabled = index >= inspectionIds.length - 1;
  if (!$('detail').open) $('detail').showModal();
}
function move(direction) {
  const next = inspectionIds[inspectionIds.indexOf(activeId) + direction];
  if (next) openDetail(next);
}
$('prev').onclick = () => move(-1);
$('next').onclick = () => move(1);
$('close').onclick = () => $('detail').close();
$('detail').addEventListener('close', () => {
  const previous = activeId;
  activeId = null;
  render();
  cards.get(previous)?.querySelector('.art-button').focus({preventScroll: true});
});
document.addEventListener('keydown', event => {
  if (!$('detail').open || /INPUT|TEXTAREA|SELECT/.test(event.target.tagName)
      || event.ctrlKey || event.metaKey || event.altKey) return;
  if (['ArrowLeft', 'ArrowRight', '1', '2', '3'].includes(event.key)) event.preventDefault();
  if (event.key === 'ArrowLeft') move(-1);
  if (event.key === 'ArrowRight') move(1);
  const status = {'1': 'good', '2': 'redo', '3': 'unsure'}[event.key];
  if (status) edit(icons.find(i => i.id === activeId), {status});
});
for (const id of ['filter', 'sort']) $(id).onchange = render;
$('search').oninput = render;
$('theme').onchange = () => { document.documentElement.dataset.theme = $('theme').value; };
$('retry').onclick = flush;
window.addEventListener('online', flush);
window.addEventListener('beforeunload', event => {
  if (pending.size) { event.preventDefault(); event.returnValue = ''; }
});
$('export').onclick = () => {
  const data = {schema_version: 1, exported_at: new Date().toISOString(), reviews: {}};
  for (const icon of icons) {
    if (!reviews[icon.id]) continue;
    data.reviews[icon.id] = {icon_id: icon.id, label: icon.label, source: icon.source, ...reviews[icon.id]};
  }
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'}));
  const link = element('a');
  link.href = url;
  link.download = `custom-icon-feedback-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
async function init() {
  try {
    const responses = await Promise.all([fetch('/api/catalog'), fetch('/api/feedback')]);
    if (responses.some(r => !r.ok)) throw new Error('Could not load the local catalog');
    const [catalog, feedback] = await Promise.all(responses.map(r => r.json()));
    icons = catalog.icons;
    token = catalog.token;
    reviews = feedback.reviews;
    try {
      const drafts = JSON.parse(localStorage.getItem(draftKey) || '[]');
      for (const [id, draft] of drafts) {
        const icon = icons.find(i => i.id === id && i.sha256 === draft.sha256);
        if (!icon) continue;
        pending.set(id, draft);
        reviews[id] = {...reviews[id], status: draft.status, notes: draft.notes, source_sha256: draft.sha256};
      }
    } catch { /* Disk feedback remains the source if browser storage is unavailable. */ }
    render();
    if (pending.size) await flush();
  } catch (error) {
    $('progress').textContent = 'Could not load icons';
    saveMessage(`${error.message}. Reload to try again.`, true);
  }
}
init();
