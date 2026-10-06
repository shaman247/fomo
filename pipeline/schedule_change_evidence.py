"""Literal, attributable date-change evidence; omission is never a notice.

This parser returns structured old-day/replacement-slot partitions. It does not
merge identities or decide which older sources may be retired.
"""
import re
from datetime import date
from occurrence_times import standardize_time

MONTHS={name.lower():i for i,name in enumerate(('January','February','March','April','May','June','July','August','September','October','November','December'),1)}
MONTHS.update({name[:3]:month for name,month in list(MONTHS.items())})
MONTHS['sept']=9
_MONTH='(?:'+'|'.join(sorted(MONTHS,key=len,reverse=True))+')'
_WEEKDAY=r'(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+)?'
_DATE=r'(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?|'+_MONTH+r'\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)'
_DATE_RE=re.compile(_WEEKDAY+'('+_DATE+')',re.I)
_VERB=r'(?:rescheduled(?:\s+date)?|moved)\s+from\s+'
_SUBJECT=r'(?:(?:this|the)\s+(?:event|program|session|class|workshop|meeting)|event|program|session|class|workshop|meeting)'
_PREFIX=re.compile(r'^(?:(?:please note(?: that)?|date change)[:,]?\s*)?(?:'+_SUBJECT+r'\s+)?(?:(?:was|is|has been|will be)\s+)?'+_VERB,re.I)
_TITLE_SUFFIX=re.compile(r'^(.*?)\s*(?:[-–—:]\s*|[([]\s*|\*+\s*)(?:class\s+)?('+_VERB+r'.+?)\s*[)\]*]*$',re.I)
_TITLE_PREFIX=re.compile(r'^('+_VERB+r'.+?)\s*:\s*(.+)$',re.I)


def _slot(row):
    start=date.fromisoformat(str(row[0]));end=date.fromisoformat(str(row[2])) if row[2] else start
    return start,standardize_time(row[1]),end,standardize_time(row[3])


def _day_candidates(token, anchors, allowed=()):
    token=re.sub(r'(\d)(?:st|nd|rd|th)\b',r'\1',token,flags=re.I).replace(',','')
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',token):return {date.fromisoformat(token)}
        parts=token.replace('.','').split()
        numeric='/' in token
        if numeric:
            parts=token.split('/');a,b=map(int,parts[:2]);year=int(parts[2]) if len(parts)==3 else None
            month_days={(a,b),(b,a)}
            if a != b and 1 <= a <= 12 and 1 <= b <= 12 and not allowed:
                return set()  # distance alone cannot choose MDY versus DMY
        else:
            month_days={(MONTHS[parts[0].lower()],int(parts[1]))};year=int(parts[2]) if len(parts)==3 else None
        if year is not None and year < 100:
            # The actual replacement supplies the century, never today's year.
            years={(anchor.year//100)*100+year+offset for anchor in anchors for offset in (-100,0,100)}
        else:
            years={year} if year else {a.year+shift for a in anchors for shift in (-1,0,1)}
        values=set()
        for year in years:
            for month,day in month_days:
                try:
                    value=date(year,month,day)
                    if any(abs((value-a).days)<=60 for a in anchors):values.add(value)
                except ValueError:pass
        if numeric and a != b and 1 <= a <= 12 and 1 <= b <= 12:
            values &= set(allowed)
        elif len(values)>1 and allowed:values &= set(allowed)
        return values
    except (ValueError,KeyError,IndexError):return set()


def _dates(text, anchors, allowed=()):
    """Parse only an entire explicit date list; ambiguity remains a refusal."""
    remainder=text.strip();days=[];last_token=None
    while remainder:
        match=_DATE_RE.match(remainder)
        if match:
            token=match[1];remainder=remainder[match.end():]
        elif last_token and (match:=re.match(r'(\d{1,2})(?:st|nd|rd|th)?\b',remainder,re.I)):
            # October 15 and 22 is an explicit same-month list, not recurrence.
            month=re.match('('+_MONTH+r')\.?\s+',last_token,re.I)
            if not month:return None
            year=re.search(r'\b(\d{4})$',last_token)
            token=month[1]+' '+match[1]+(' '+year[1] if year else '')
            remainder=remainder[match.end():]
        else:return None
        values=_day_candidates(token,anchors,allowed)
        if len(values)!=1:return None
        days.append(next(iter(values)));last_token=token
        if not remainder.strip():break
        sep=re.match(r'\s*(?:,\s*(?:and\s+)?|and\s+|&\s*)',remainder,re.I)
        if not sep:return None
        remainder=remainder[sep.end():]
        if not remainder:return None
    return tuple(days) if days and len(days)==len(set(days)) else None


def _title(name):
    value=(name or '').strip()
    match=_TITLE_SUFFIX.fullmatch(value) or _TITLE_PREFIX.fullmatch(value)
    if not match:return value,None
    if _TITLE_PREFIX.fullmatch(value):return match[2].strip(),match[1]
    return match[1].strip(),match[2]


def identity_name(name):
    return ' '.join(_title(name)[0].split()).casefold()


def _parse_clause(text, source_slots, old_days, *, header_day=None):
    text=text.strip().strip('.*()[] ')
    prefix=_PREFIX.match(text)
    if not prefix:return None
    body=text[prefix.end():]
    # Reasons and logistical prose cannot supply replacement dates.
    body=re.split(r'\s+due to\s+|\s*;\s*',body,maxsplit=1,flags=re.I)[0].rstrip('.! ')
    parts=re.split(r'\s+to\s+',body,flags=re.I)
    if len(parts)>2:return None
    new_days={s[0] for s in source_slots if s[0]==s[2]}
    if header_day:
        new_days &= {header_day}
    anchors=sorted(new_days)
    if not anchors:return None
    previous=_dates(parts[0],anchors,old_days)
    if not previous:return None
    if len(parts)==2:
        replacement_days=_dates(parts[1],anchors,new_days)
        if not replacement_days or not set(replacement_days)<=new_days:return None
    else:
        # A notice without an explicit replacement cannot pick among dates.
        if len(new_days)!=1:return None
        replacement_days=tuple(new_days)
    replacement={s for s in source_slots if s[0] in replacement_days}
    if (any(s[0]!=s[2] for s in replacement) or len(replacement)!=len(replacement_days)
            or set(previous)&set(replacement_days)
            or any(not any(abs((old-new).days)<=60 for new in replacement_days) for old in previous)):
        return None
    return dict(old_days=frozenset(previous),replacement=frozenset(replacement),quote=text,
                scoped=bool(header_day or len(parts)==2))



def _complete_schedule(text, slots, old_days):
    """A publisher-declared complete window can retire only dates inside it.

    Both boundaries must include a year, and every stated replacement date must
    appear in the source's actual slot partition. A shorter rolling list or a
    generic 'updated schedule' does not make this assertion.
    """
    text=text.strip().strip('.*()[] ')
    pattern=(r'(?:the )?complete revised schedule for this (?:event|program|course|series) '
             r'from (.+?) (?:to|through) (.+?) (?:is|:) (.+)')
    match=re.fullmatch(pattern,text,re.I)
    if not match:return None
    def boundary(value):
        value=value.strip()
        try:
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):return date.fromisoformat(value)
            bits=value.replace(',','').split()
            if len(bits)==3 and re.fullmatch(r'\d{4}',bits[2]):
                return date(int(bits[2]),MONTHS[bits[0].lower()],int(bits[1]))
        except (ValueError,KeyError):pass
        return None
    start,end=boundary(match[1]),boundary(match[2])
    if not start or not end or not 0 <= (end-start).days <= 366:return None
    replacement={row for row in slots if start <= row[0] <= end}
    if not replacement or any(row[0]!=row[2] for row in replacement):return None
    new_days={row[0] for row in replacement}
    stated=_dates(match[3],sorted(new_days),new_days)
    if not stated or set(stated)!=new_days or len(replacement)!=len(new_days):return None
    old=frozenset(day for day in old_days if start <= day <= end and day not in new_days)
    if not old:return None
    return dict(old_days=old,replacement=frozenset(replacement),quote=text,scoped=True,
                window=(start,end))

def changes(source, *, old_days=()):
    """Parse self-event clauses and explicit title notices into disjoint changes.

    A dated grouped-description heading binds a following notice to its own
    replacement date. Multiple unscoped from-only notices remain ambiguous.
    """
    text=source.get('description') or '';name=source.get('name') or ''
    if re.search(r'\bcancell?ed\b',text+' '+name,re.I):return []
    try:slots={_slot(r) for r in source.get('occurrences',[])}
    except (ValueError,TypeError,IndexError):return []
    if not slots:return []
    results=[];heading=None
    _,title_notice=_title(name)
    if title_notice:
        change=_parse_clause(title_notice,slots,old_days)
        if change:results.append(change)
    # Do not split a month abbreviation into a different sentence.
    text=re.sub(r'\b('+_MONTH+r')\.(?=\s+\d)',r'\1',text,flags=re.I)
    for paragraph in text.splitlines():
        header=re.fullmatch(r'(\d{4}-\d{2}-\d{2})(?:\s+[^\n]+)?',paragraph.strip())
        if header:
            try:heading=date.fromisoformat(header[1])
            except ValueError:heading=None
            continue
        for sentence in re.split(r'[!?;]+|(?<=\.)\s+',paragraph):
            change=(_parse_clause(sentence,slots,old_days,header_day=heading)
                    or _complete_schedule(sentence,slots,old_days))
            if change and change not in results:results.append(change)
    # Duplicate title/body notices have different quotes but same partition.
    unique={ (r['old_days'],r['replacement']):r for r in results }
    results=list(unique.values())
    if len(results)>1 and any(not r['scoped'] for r in results):return []
    # An old date cannot acquire competing target partitions in one source.
    for n,left in enumerate(results):
        for right in results[n+1:]:
            if left['old_days']&right['old_days'] and left['replacement']!=right['replacement']:return []
    return results
