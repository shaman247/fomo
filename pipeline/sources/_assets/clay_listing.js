// Scratch candidate ONLY: enrich the exact Clay Art Center listing, no date expansion.
await (async () => {
  'use strict';
  const ORIGIN = 'https://www.clayartcenter.org';
  const PATH = '/events-at-clayartcenter';
  const TOUR_ID = '630f9f3bcc5a9c1188842856';
  const TOUR_PATH = PATH + '/2022/9/guided-tours-of-exhibitions-and-studios';
  const TOUR_TITLE = 'Guided Tours of Exhibitions and Studios';
  const BOUNDARY = 'Our Upcoming Exhibition Schedule:';
  const AUDIT = '__clayListingReview';
  const require = (ok, why) => { if (!ok) throw new Error(why); };
  const normalized = s => s.replace(/\s+/g, ' ').trim();
  const htmlText = html => {
    require(typeof html === 'string', 'HTML field is not a string');
    const parsed = new DOMParser().parseFromString(html, 'text/html');
    parsed.querySelectorAll('script,style,noscript,template').forEach(n => n.remove());
    parsed.querySelectorAll('br,p,div,h1,h2,h3,h4,h5,h6,li').forEach(n => n.appendChild(parsed.createTextNode(' ')));
    return normalized(parsed.body.textContent || '');
  };
  const text = (tag, value) => {
    const node = document.createElement(tag); node.textContent = value; return node;
  };
  try {
    require(location.origin === ORIGIN && location.pathname.replace(/\/$/, '') === PATH && !location.search,
      'Exact original listing URL required');
    require(!document.getElementById('clay-events-reviewed'), 'Already formatted');
    const response = await fetch(ORIGIN + PATH + '?format=json', {credentials: 'same-origin'});
    require(response.ok, 'Listing JSON request failed: ' + response.status);
    const data = await response.json();
    require(data.collection && data.collection.id === '5eb2c842cdf8c53b23d74ab9' && data.collection.fullUrl === PATH,
      'Wrong collection identity');
    require(data.website && data.website.timeZone === 'America/New_York', 'Publisher timezone changed');
    require(Array.isArray(data.upcoming) && data.upcoming.length > 0 && Array.isArray(data.past), 'Missing listing partitions');
    const tz = data.website.timeZone;
    const fmt = new Intl.DateTimeFormat('en-US', {timeZone: tz, weekday: 'short', month: 'long', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true});
    const main = document.querySelector('main, #content, .content');
    require(main, 'No listing content root');
    const selectors = '.eventlist, .events-collection-list, .sqs-block-events, .summary-block-collection-type-events, [class*="eventlist-event"], #sqs-events';
    require(main.querySelectorAll(selectors).length > 0, 'Original listing container absent');
    const ids = new Set(), urls = new Set(), records = [];
    let tourCount = 0, tourAudit;
    for (const ev of data.upcoming) {
      require(ev && typeof ev.id === 'string' && !ids.has(ev.id), 'Missing or duplicate item identity');
      ids.add(ev.id);
      require(typeof ev.title === 'string' && ev.title.trim() && typeof ev.fullUrl === 'string', 'Missing title or item URL');
      const url = new URL(ev.fullUrl, ORIGIN);
      require(url.origin === ORIGIN && url.pathname.startsWith(PATH + '/') && !url.search && !url.hash && !urls.has(url.href), 'Invalid or duplicate item URL');
      urls.add(url.href);
      require(Number.isFinite(ev.startDate) && Number.isFinite(ev.endDate) && ev.endDate >= ev.startDate,
        'Invalid administrative timestamps');
      const title = htmlText(ev.title);
      const identitySignals = [ev.id === TOUR_ID, url.pathname === TOUR_PATH, title === TOUR_TITLE];
      require(identitySignals.every(Boolean) || identitySignals.every(v => !v), 'Partial tour identity mismatch');
      const isTour = identitySignals.every(Boolean);
      const loc = ev.location || {};
      const address = [loc.addressTitle, loc.addressLine1, loc.addressLine2].filter(Boolean).join(', ');
      let description;
      if (isTour) {
        tourCount++;
        const full = htmlText(ev.body);
        require(full.split(BOUNDARY).length === 2, 'Tour exhibition boundary absent or ambiguous');
        description = full.slice(0, full.indexOf(BOUNDARY)).trim();
        require(/every Wednesday at 11\.30am, except for holidays\./.test(description), 'Tour schedule or holiday qualifier changed');
        require(description.includes('no appointment is necessary') && description.includes('Blue Door off the parking lot') && description.includes('mail@clayartcenter.org'), 'Tour participation/context evidence missing');
        tourAudit = {id: ev.id, url: url.href, title, startDate: ev.startDate, endDate: ev.endDate,
          administrativeHeaderOmitted: true, bodyBeforeBoundary: description,
          omittedNestedExhibitionBody: full.slice(full.indexOf(BOUNDARY)), rawBody: ev.body};
      } else {
        // Preserve the existing sibling excerpt-first, 600-character scope.
        description = htmlText(ev.excerpt || ev.body || '').slice(0, 600);
      }
      records.push({id: ev.id, url: url.href, title, address, description, isTour,
        startDate: ev.startDate, endDate: ev.endDate});
    }
    require(tourCount === 1 && records.length === data.upcoming.length, 'Tour or listing inventory incomplete');
    // Build every replacement node off-page. No source DOM changes before validation.
    const replacement = document.createElement('ul'); replacement.id = 'clay-events-reviewed';
    for (const record of records) {
      const li = document.createElement('li'); li.dataset.sourceItemId = record.id;
      const heading = document.createElement('h3'), link = text('a', record.title); link.href = record.url;
      heading.appendChild(link); li.appendChild(heading);
      li.appendChild(text('p', 'CLAY-ITEM-V1 id=' + record.id));
      if (!record.isTour) {
        const dates = document.createElement('p'); dates.appendChild(text('strong', fmt.format(record.startDate) + ' – ' + fmt.format(record.endDate)));
        li.appendChild(dates);
      }
      li.appendChild(text('p', record.address));
      if (record.isTour) li.appendChild(text('p', 'CLAY-TOUR-PROSE-V1 id=' + TOUR_ID + ' BEGIN'));
      li.appendChild(text('p', record.description));
      if (record.isTour) li.appendChild(text('p', 'CLAY-TOUR-PROSE-V1 id=' + TOUR_ID + ' END'));
      li.appendChild(text('p', 'Publisher time zone: ' + tz));
      replacement.appendChild(li);
    }
    require(replacement.children.length === records.length && replacement.querySelectorAll('h3 a').length === records.length,
      'Rendered inventory mismatch');
    const staged = main.cloneNode(true);
    staged.querySelectorAll(selectors).forEach(node => node.remove());
    staged.appendChild(text('p', 'CLAY-LISTING-V1 count=' + records.length + ' timezone=' + tz));
    staged.appendChild(replacement);
    const audit = {status: 'validated', timeZone: tz, sourceURL: response.url, upcomingCount: records.length,
      pastCount: data.past.length, pagination: data.pagination || null,
      paginationScope: 'Native upcoming partition only; historical pagination audited separately; no inferred event-date cursor',
      sourceIds: records.map(r => r.id), tour: tourAudit};
    // One DOM commit. A preceding failure leaves the original DOM untouched.
    main.replaceChildren(...Array.from(staged.childNodes));
    window[AUDIT] = audit;
  } catch (error) {
    window[AUDIT] = {status: 'failed', reason: String(error && error.message || error)};
    console.error('Clay listing candidate preserved original DOM:', window[AUDIT].reason);
  }
})();
