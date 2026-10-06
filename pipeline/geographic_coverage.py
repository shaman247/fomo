"""Config-driven postal coverage shared by source ingestion and audits.

Coverage policy belongs only to config/<city>.yaml; unknown addresses remain
unknown, and callers must not treat them as exclusions.
"""
import re

import city_config

# "…, NY 10012" / "…, NJ 07030-1234" — the state+ZIP tail of a US address.
_STATE_ZIP_RE = re.compile(r',\s*([A-Z]{2})\s+(\d{5})(?:-\d{4})?\b')


class CoverageArea:
    """Decides whether a `locations` row sits inside the coverage area.

    Deliberately postal, never nominal: substring-matching place names against
    an address is what produced ~40% false positives the first time round
    ("Saratoga Ave" and "Buffalo Ave" are Brooklyn streets; "Macombs Dam Park"
    is the Bronx). A ZIP cannot be talked into being somewhere it is not.
    """

    def __init__(self, cfg=None):
        cfg = cfg if cfg is not None else city_config.coverage()
        self.zip3 = {state: set(zips)
                     for state, zips in (cfg.get('zip3') or {}).items()}
        self.zip5_only = {key: set(zips)
                          for key, zips in (cfg.get('zip5_only') or {}).items()}
        self.bbox = cfg.get('bbox') or {}
        self.configured = bool(self.zip3)

    # -- postal ------------------------------------------------------------
    def classify_address(self, address):
        """('in'|'out'|'unknown', detail) for a postal address string."""
        if not self.configured:
            return 'unknown', 'no coverage configured'
        if not address:
            return 'unknown', 'no address'
        m = _STATE_ZIP_RE.search(str(address))
        if not m:
            return 'unknown', 'no parseable <ST> <ZIP> in address'
        state, zipcode = m.group(1), m.group(2)
        where = f"{state} {zipcode}"
        if state not in self.zip3:
            return 'out', f"state {state} is outside the coverage area"
        zip3 = zipcode[:3]
        if zip3 not in self.zip3[state]:
            return 'out', f"ZIP {where} (ZIP3 {zip3} outside the coverage area)"
        carve_out = self.zip5_only.get(f"{state}:{zip3}")
        if carve_out is not None and zipcode not in carve_out:
            return 'out', (f"ZIP {where} (ZIP3 {zip3} straddles the coverage "
                           f"boundary and {zipcode} is on the outside)")
        return 'in', f"ZIP {where}"

    # -- coordinates -------------------------------------------------------
    def classify_coords(self, lat, lng, margin_deg=0.0):
        """('in'|'out'|'unknown', detail) for a lat/lng pair.

        Coarse on purpose — the envelope is a rectangle around the whole metro
        region, so 'in' means only "not a gross outlier". Never use it to
        adjudicate a county line; that is what the ZIP test is for.

        `margin_deg` slackens the rectangle. Used by the address-vs-coords
        sanity check, which must only fire on grossly wrong coordinates.
        """
        if not self.bbox:
            return 'unknown', 'no bbox configured'
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            return 'unknown', 'no coordinates'
        if not (self.bbox['min_lat'] - margin_deg <= lat <= self.bbox['max_lat'] + margin_deg
                and self.bbox['min_lng'] - margin_deg <= lng <= self.bbox['max_lng'] + margin_deg):
            return 'out', (f"coordinates ({lat:.4f}, {lng:.4f}) fall outside "
                           f"the coverage envelope")
        return 'in', f"coordinates ({lat:.4f}, {lng:.4f})"

    # How far outside the bbox a coordinate must fall before it counts as
    # contradicting an in-coverage ZIP. The bbox is a rectangle drawn around an
    # irregular region, so several deliberately-covered ZIP3s sit just outside
    # it — NJ 088 (Hunterdon: Clinton 08809 is 0.07 deg west of min_lng) is the
    # known case, and config/nyc.yaml keeps it on purpose. 0.5 deg is ~55 km:
    # wide enough to ignore every such edge, tight enough that a coordinate in
    # the wrong state still surfaces.
    COORD_CONTRADICTION_MARGIN_DEG = 0.5

    # -- combined ----------------------------------------------------------
    def evaluate_location(self, event):
        """Return (tier, reason) for the event's mapped location, or None.

        **The ZIP test always wins when there is a parseable ZIP** — that is the
        contract stated in `config/nyc.yaml`, because the bbox is "far too loose
        to adjudicate a county line". Coordinates are therefore only used (a) as
        the fallback when the address has no parseable `<ST> <ZIP>`, and (b) as a
        gross-outlier sanity check, which needs a wide margin so it cannot
        override a deliberate coverage decision.
        """
        if not self.configured or not event.get('location_id'):
            return None
        verdict, detail = self.classify_address(event.get('location_address'))

        if verdict == 'out':
            return ('LOCATION',
                    f"mapped location {event.get('mapped_to')!r} is out of "
                    f"area: {detail}")
        if verdict == 'unknown':
            # No usable ZIP — the envelope is the only signal left, used tight.
            coord_verdict, coord_detail = self.classify_coords(
                event.get('location_lat'), event.get('location_lng'))
            if coord_verdict == 'out':
                return ('LOCATION',
                        f"mapped location {event.get('mapped_to')!r} is out of "
                        f"area: {detail}, and {coord_detail}")
            return None

        # verdict == 'in': the ZIP has settled coverage. Only a coordinate that
        # is wrong by a wide margin (i.e. a data error, not a boundary nicety)
        # is worth a human look, and it is a data-integrity flag rather than a
        # coverage one.
        coord_verdict, coord_detail = self.classify_coords(
            event.get('location_lat'), event.get('location_lng'),
            margin_deg=self.COORD_CONTRADICTION_MARGIN_DEG)
        if coord_verdict == 'out':
            return ('REVIEW',
                    f"mapped location {event.get('mapped_to')!r} disagrees with "
                    f"itself: {detail} is in coverage but {coord_detail} — one "
                    f"of the two fields is wrong")
        return None

