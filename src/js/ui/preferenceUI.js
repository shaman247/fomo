/** Editable explicit preferences. The profile never records searches implicitly. */
const PreferenceUI = (() => {
    let getState = () => ({});
    let dialog, finder, typeInput, results, profileList, status, editor;
    let selectedEntry = null;
    let cancelDrag = () => {};
    let timer;
    let suggestionVersion = 0;
    const names = { place: 'Places', tag: 'Tags', event: 'Events', term: 'Searches' };

    function button(text, action) {
        const el = document.createElement('button');
        el.type = 'button'; el.textContent = text;
        el.addEventListener('click', e => { e.stopPropagation(); action(); });
        return el;
    }

    function createControls(type, id, label) {
        const group = document.createElement('span');
        group.className = 'preference-controls';
        group.setAttribute('role', 'group');
        group.setAttribute('aria-label', `Your interest in ${label}`);
        for (const [stance, text] of [[1, 'Interested'], [-1, 'Not interested']]) {
            const b = button(text, () => {
                if (DiscoveryRanking.stance(type, id) === stance) DiscoveryRanking.remove(type, id);
                else if (!DiscoveryRanking.set(type, id, label, stance)) announce('Your profile is full. Remove an entry to add another.');
            });
            b.dataset.preferenceType = type;
            b.dataset.preferenceId = id;
            b.dataset.stance = stance;
            b.setAttribute('aria-pressed', String(DiscoveryRanking.stance(type, id) === stance));
            group.appendChild(b);
        }
        return group;
    }

    function updateFavoriteButton(b) {
        const active = DiscoveryRanking.stance(b.dataset.preferenceType, b.dataset.preferenceId) === 1;
        b.textContent = active ? '★' : '☆';
        b.setAttribute('aria-pressed', String(active));
        const action = `${active ? 'Remove' : 'Add'} ${b.dataset.favoriteLabel} ${active ? 'from' : 'to'} Favorites`;
        b.setAttribute('aria-label', action); b.title = action;
    }

    function createFavoriteButton(type, id, label) {
        const b = button('', () => {
            if (DiscoveryRanking.stance(type, id) === 1) DiscoveryRanking.remove(type, id);
            else if (!DiscoveryRanking.set(type, id, label, 1)) announce('Your Favorites list is full. Remove an entry to add another.');
        });
        b.className = 'favorite-toggle';
        b.dataset.preferenceType = type; b.dataset.preferenceId = id;
        b.dataset.stance = '1'; b.dataset.favoriteLabel = label;
        updateFavoriteButton(b);
        return b;
    }

    function announce(text) {
        if (status) { status.textContent = text; status.hidden = !text; }
        if (!DiscoveryRanking.canPersist() && dialog && !dialog.open && typeof ToastNotifier !== 'undefined') {
            ToastNotifier.showToast(text, 'info', 4000);
        }
    }

    function refreshControls() {
        document.querySelectorAll('[data-preference-type]').forEach(b => {
            if (b.classList.contains('favorite-toggle')) { updateFavoriteButton(b); return; }
            b.setAttribute('aria-pressed', String(DiscoveryRanking.stance(b.dataset.preferenceType,
                b.dataset.preferenceId) === Number(b.dataset.stance)));
        });
    }

    function focusChip(entry) {
        const chip = [...profileList.querySelectorAll('[data-interest-id]')].find(b =>
            b.dataset.interestId === entry.id && b.dataset.interestType === entry.type);
        (chip || finder).focus();
    }

    function closeEditor(restoreFocus = false) {
        const previous = selectedEntry;
        selectedEntry = null;
        editor.hidden = true;
        profileList.querySelectorAll('[aria-expanded]').forEach(b => b.setAttribute('aria-expanded', 'false'));
        if (restoreFocus && previous) focusChip(previous);
    }

    function editEntry(entry) {
        if (selectedEntry?.type === entry.type && selectedEntry.id === entry.id) {
            closeEditor(true); return;
        }
        closeEditor();
        selectedEntry = entry;
        editor.replaceChildren(); editor.hidden = false;
        const title = document.createElement('strong'); title.textContent = entry.label;
        const actions = document.createElement('div'); actions.className = 'interest-edit-actions';
        actions.append(button(entry.stance === 1 ? 'Move to Not interested' : 'Move to Interested', () => {
            closeEditor();
            DiscoveryRanking.set(entry.type, entry.id, entry.label, -entry.stance);
            focusChip(entry);
        }), button('Remove', () => {
            closeEditor(); DiscoveryRanking.remove(entry.type, entry.id); finder.focus();
        }), button('Done', () => closeEditor(true)));
        editor.appendChild(title);
        if (entry.type === 'term') {
            const input = document.createElement('input');
            input.value = entry.label; input.maxLength = 200;
            input.setAttribute('aria-label', 'Edit saved search');
            const save = () => {
                if (!DiscoveryRanking.normalize(input.value)) { announce('Enter a search phrase.'); input.focus(); return; }
                closeEditor();
                DiscoveryRanking.renameTerm(entry.id, input.value);
                focusChip({ type: 'term', id: DiscoveryRanking.normalize(input.value) });
            };
            input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); save(); } });
            editor.append(input, button('Save search', save));
        }
        editor.appendChild(actions);
        const chip = [...profileList.querySelectorAll('[data-interest-id]')].find(b =>
            b.dataset.interestId === entry.id && b.dataset.interestType === entry.type);
        chip?.setAttribute('aria-expanded', 'true');
        editor.querySelector('input, button').focus();
    }

    function makeDraggable(chip, entry) {
        // Pointer events support mouse, pen and touch; clicking provides the same
        // move/remove actions for keyboard users and those who cannot drag.
        chip.addEventListener('pointerdown', down => {
            if (!down.isPrimary || down.button !== 0) return;
            let dragging = false, ghost, target, frame;
            let x = down.clientX, y = down.clientY;
            const origin = chip.getBoundingClientRect();
            chip.setPointerCapture(down.pointerId);
            const highlight = () => {
                target?.classList.remove('is-drop-target');
                target = document.elementFromPoint(x, y)?.closest('.interest-stance');
                target?.classList.add('is-drop-target');
            };
            const scroll = () => {
                const r = profileList.getBoundingClientRect();
                if (x >= r.left && x <= r.right) {
                    if (y < r.top + 45) profileList.scrollTop -= 10;
                    else if (y > r.bottom - 45) profileList.scrollTop += 10;
                }
                highlight(); frame = requestAnimationFrame(scroll);
            };
            const move = e => {
                x = e.clientX; y = e.clientY;
                if (!dragging && Math.hypot(x - down.clientX, y - down.clientY) < 8) return;
                e.preventDefault();
                if (!dragging) {
                    dragging = true; closeEditor(); results.hidden = true;
                    chip.dataset.dragged = 'true'; chip.classList.add('is-dragging');
                    ghost = chip.cloneNode(true); ghost.classList.add('interest-drag-ghost');
                    ghost.removeAttribute('id'); ghost.setAttribute('aria-hidden', 'true'); ghost.tabIndex = -1;
                    ghost.style.width = `${origin.width}px`; dialog.appendChild(ghost);
                    frame = requestAnimationFrame(scroll);
                }
                const bounds = dialog.getBoundingClientRect();
                ghost.style.left = `${x - bounds.left - dialog.clientLeft - Math.min(40, origin.width / 2)}px`;
                ghost.style.top = `${y - bounds.top - dialog.clientTop - origin.height / 2}px`;
                highlight();
            };
            const finish = e => {
                cancelAnimationFrame(frame);
                target?.classList.remove('is-drop-target'); ghost?.remove(); chip.classList.remove('is-dragging');
                chip.removeEventListener('pointermove', move);
                chip.removeEventListener('pointerup', finish);
                chip.removeEventListener('pointercancel', finish);
                chip.removeEventListener('lostpointercapture', finish);
                if (chip.hasPointerCapture(down.pointerId)) chip.releasePointerCapture(down.pointerId);
                cancelDrag = () => {};
                if (dragging && e?.type === 'pointerup' && target) {
                    DiscoveryRanking.set(entry.type, entry.id, entry.label, Number(target.dataset.stance));
                    focusChip(entry);
                }
                // The click following pointerup must not open the chip editor.
                setTimeout(() => delete chip.dataset.dragged, 0);
            };
            cancelDrag = () => finish();
            chip.addEventListener('pointermove', move);
            chip.addEventListener('pointerup', finish);
            chip.addEventListener('pointercancel', finish);
            chip.addEventListener('lostpointercapture', finish);
        });
    }

    const displayCache = {};
    function entryDisplay(entry) {
        const data = getState();
        if (entry.type === 'term') return { emoji: '🔎', label: entry.label };
        if (entry.type === 'tag') {
            const tag = Object.keys(data.tagEmojiMap || {}).find(name => DiscoveryRanking.normalize(name) === entry.id);
            return { emoji: data.tagEmojiMap?.[tag] || '🏷️', label: entry.label };
        }
        const items = (entry.type === 'place' ? data.rawLocations : data.allEvents) || [];
        let cache = displayCache[entry.type];
        if (!cache || cache.items !== items || cache.length !== items.length) {
            cache = displayCache[entry.type] = { items, length: items.length, index: new Map() };
            for (const item of items) cache.index.set(entry.type === 'place' ? DiscoveryRanking.placeKey(item) : String(item.id), item);
        }
        const item = cache.index.get(entry.id);
        return { icon_id: item?.icon_id, emoji: item?.emoji || (entry.type === 'place' ? '📍' : '🎟️'),
            label: item?.name || entry.label.split(' — ')[0] };
    }

    function renderProfile() {
        cancelDrag(); closeEditor();
        const scrollTop = profileList.scrollTop;
        profileList.replaceChildren();
        const entries = DiscoveryRanking.entries();
        for (const [stance, title] of [[1, 'Interested'], [-1, 'Not interested']]) {
            const section = document.createElement('section');
            section.className = 'interest-stance'; section.dataset.stance = stance;
            const heading = document.createElement('h3'); heading.textContent = title;
            heading.id = `interest-stance-${stance}`; section.setAttribute('aria-labelledby', heading.id);
            section.appendChild(heading);
            for (const [type, name] of Object.entries(names)) {
                const group = document.createElement('section'); group.className = 'interest-category';
                const subheading = document.createElement('h4'); subheading.textContent = name;
                const list = document.createElement('ul'); list.className = 'interest-chips';
                list.setAttribute('aria-label', `${title}: ${name}`);
                const subset = entries.filter(e => e.stance === stance && e.type === type);
                for (const entry of subset) {
                    const item = document.createElement('li');
                    const chip = button('', () => { if (!chip.dataset.dragged) editEntry(entry); });
                    const display = entryDisplay(entry);
                    Utils.appendChipContent(chip, display.emoji, display.label, { tagIcon: entry.type === 'tag', iconRecord: display });
                    if (stance === 1) chip.style.setProperty('--chip-color', TagColorManager.getColorForEmoji(display.emoji));
                    chip.className = 'tag-button interest-chip ' + (stance === 1 ? 'state-selected' : 'state-unselected');
                    chip.dataset.interestType = type; chip.dataset.interestId = entry.id;
                    chip.title = entry.label; chip.setAttribute('aria-expanded', 'false');
                    chip.setAttribute('aria-controls', 'interest-editor');
                    makeDraggable(chip, entry); item.appendChild(chip); list.appendChild(item);
                }
                if (!subset.length) {
                    const empty = document.createElement('li'); empty.className = 'interest-empty';
                    empty.textContent = 'None yet'; list.appendChild(empty);
                }
                group.append(subheading, list); section.appendChild(group);
            }
            profileList.appendChild(section);
        }
        profileList.scrollTop = scrollTop;
    }

    async function suggestions() {
        const version = ++suggestionVersion;
        results.replaceChildren();
        const type = typeInput.value;
        const raw = finder.value.trim();
        const query = DiscoveryRanking.normalize(raw);
        results.classList.toggle('is-model-suggestions', !query);
        const data = getState();
        const found = [];
        results.hidden = !query;
        if (!query) {
            if (type === 'term' || typeof SimilarityModel === 'undefined') return;
            if (!await SimilarityModel.load() || version !== suggestionVersion) return;
            const values = type === 'event' ? data.allEvents || []
                : type === 'place' ? data.rawLocations || [] : data.allAvailableTags || [];
            found.push(...await SimilarityModel.suggest(type, values, Utils.isMobileLayout() ? 4 : 6));
            if (version !== suggestionVersion || !dialog.open) return;
            results.hidden = !found.length;
        }
        else if (type === 'term') found.push({ id: query, label: raw });
        else {
            const values = type === 'event' ? data.allEvents || []
                : type === 'place' ? data.rawLocations || [] : data.allAvailableTags || [];
            const seen = new Set();
            const exact = [], partial = [];
            const limit = Utils.isMobileLayout() ? 4 : 6;
            let sliceStart = performance.now();
            let scanned = 0;
            for (const item of values) {
                if (++scanned % 200 === 0 && performance.now() - sliceStart >= 8) {
                    await new Promise(resolve => setTimeout(resolve, 0));
                    if (version !== suggestionVersion) return;
                    sliceStart = performance.now();
                }
                const label = type === 'tag' ? item : item.name;
                const context = type === 'event' ? item.location : type === 'place' ? item.address : '';
                if (!DiscoveryRanking.normalize(`${label} ${context || ''}`).includes(query)) continue;
                const id = type === 'event' ? String(item.id)
                    : type === 'place' ? DiscoveryRanking.placeKey(item) : DiscoveryRanking.normalize(item);
                if (seen.has(id)) continue;
                seen.add(id);
                const bucket = DiscoveryRanking.normalize(label) === query ? exact : partial;
                if (bucket.length < limit) bucket.push({ id, label, context });
            }
            found.push(...(exact.length ? exact : partial).slice(0, limit));
        }
        if (!found.length && query) {
            const row = document.createElement('li');
            row.textContent = 'No matches in loaded events. Try another name or save it as a search term.';
            results.appendChild(row);
        }
        if (!query && found.length) {
            const heading = document.createElement('li');
            heading.className = 'interest-suggestions-label';
            heading.textContent = 'Suggested favorites';
            results.appendChild(heading);
        }
        found.forEach(item => {
            const row = document.createElement('li');
            const savedLabel = item.context ? `${item.label} — ${item.context}` : item.label;
            const title = query ? document.createElement('span') : button('', () => {
                if (!DiscoveryRanking.set(type, item.id, savedLabel, 1)) announce('Your profile is full. Remove an entry to add another.');
            });
            if (query) title.textContent = item.label;
            else {
                title.className = 'tag-button interest-suggestion-chip';
                Utils.appendChipContent(title, type === 'tag' ? data.tagEmojiMap?.[item.label] || '🏷️'
                    : item.emoji || (type === 'place' ? '📍' : '🎟️'), item.label, { tagIcon: type === 'tag' });
                title.setAttribute('aria-label', `Add ${item.label} to Favorites`);
                title.title = savedLabel;
            }
            if (query && item.context) { const context = document.createElement('small'); context.textContent = item.context; title.appendChild(context); }
            row.appendChild(title);
            if (query) row.appendChild(createControls(type, item.id, savedLabel));
            results.appendChild(row);
        });
    }

    function open() {
        renderProfile(); suggestions(); announce('');
        if (!dialog.open) dialog.showModal();
        finder.focus();
    }

    function init(provider) {
        getState = provider;
        dialog = document.createElement('dialog');
        dialog.className = 'modal-content';
        dialog.id = 'interests-dialog'; dialog.setAttribute('aria-labelledby', 'interests-title');
        dialog.innerHTML = `<div class="modal-header"><h2 id="interests-title">⭐ Favorites</h2><button type="button" id="interests-close" class="modal-close-btn" aria-label="Close Favorites">×</button></div>
            <div class="modal-body interests-body"><div class="interests-search-area"><div class="interests-finder"><label>Type<select id="interest-type"><option value="place">Place</option><option value="tag">Tag</option><option value="event">Event</option><option value="term">Search</option></select></label>
            <label>Find or add<input id="interest-finder" type="search" maxlength="200" placeholder="Find a favorite" autocomplete="off" aria-controls="interest-suggestions"></label></div>
            <ul id="interest-suggestions" aria-label="Preference suggestions" hidden></ul></div>
            <div id="interests-entries"></div>
            <div id="interest-editor" role="region" aria-label="Edit favorite" hidden></div>
            <p id="interests-status" role="status" hidden></p></div>`;
        document.body.appendChild(dialog);
        finder = dialog.querySelector('#interest-finder');
        typeInput = dialog.querySelector('#interest-type');
        results = dialog.querySelector('#interest-suggestions');
        profileList = dialog.querySelector('#interests-entries');
        status = dialog.querySelector('#interests-status');
        editor = dialog.querySelector('#interest-editor');
        dialog.addEventListener('close', () => { suggestionVersion++; cancelDrag(); closeEditor(); });
        dialog.addEventListener('cancel', e => {
            if (!editor.hidden || !results.hidden) {
                e.preventDefault(); closeEditor(true); results.hidden = true;
            }
        });
        dialog.addEventListener('click', e => {
            if (!e.target.closest('.interests-search-area')) results.hidden = true;
        });
        dialog.querySelector('#interests-close').addEventListener('click', () => dialog.close());
        dialog.addEventListener('click', e => { if (e.target === dialog) {
            const r = dialog.getBoundingClientRect();
            if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dialog.close();
        } });
        finder.addEventListener('input', () => {
            clearTimeout(timer);
            suggestionVersion++;
            // Stale suggestions must not remain clickable for the new query.
            results.replaceChildren();
            timer = setTimeout(suggestions, 120);
        });
        typeInput.addEventListener('change', suggestions);
        finder.addEventListener('focus', () => { if (!finder.value.trim()) suggestions(); });
        document.querySelectorAll('[data-open-interests]').forEach(b => b.addEventListener('click', open));
        document.addEventListener('fomo:preferences-changed', () => {
            // Keep the focused control mounted while updating its pressed state.
            const focused = document.activeElement;
            const wasInProfile = profileList.contains(focused);
            const restore = wasInProfile ? {
                type: focused.dataset.interestType, id: focused.dataset.interestId
            } : null;
            renderProfile(); refreshControls();
            if (dialog.open && !finder.value.trim()) suggestions();
            if (restore?.id) focusChip(restore);
            if (wasInProfile && !document.contains(focused) && document.activeElement === document.body) finder.focus();
            announce(DiscoveryRanking.canPersist() ? '' : 'Updated for this visit. Browser storage is unavailable.');
        });
    }
    return { init, open, createControls, createFavoriteButton };
})();
