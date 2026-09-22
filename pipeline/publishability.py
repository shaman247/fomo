"""Shared SQL eligibility rule; safe to import in lightweight data consumers."""

# Aggregator trust gate, shared by the frontend export and the public dataset:
# an event is publishable when it has no website, its website is a primary
# source or still enabled, or at least one of its sources is a primary site.
# Enabled aggregators (RA, Eventbrite, Partiful, …) are trusted discovery feeds.
# Expects the `events e` / `LEFT JOIN websites w` aliases.
PUBLISHABLE_WEBSITE_GATE = """
            w.id IS NULL
            OR w.source_type = 'primary'
            OR w.disabled = FALSE
            OR EXISTS (
                SELECT 1 FROM event_sources es
                JOIN crawl_events ce ON es.crawl_event_id = ce.id
                JOIN crawl_results cr ON ce.crawl_result_id = cr.id
                JOIN websites w2 ON cr.website_id = w2.id
                WHERE es.event_id = e.id AND w2.source_type = 'primary'
            )
"""
