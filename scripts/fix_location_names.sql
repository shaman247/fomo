-- =============================================================================
-- Location name/short_name/very_short_name cleanup
-- Generated 2026-02-08
--
-- Guidelines:
--   name:            Full location name (any length)
--   short_name:      Map label & filter panel display (10-25 chars ideal)
--   very_short_name: Ultra-compact map label fallback (<10 chars)
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- FIX 1: Data error — short_name is an address (Poster House)
-- ─────────────────────────────────────────────────────────────────────────────

UPDATE locations SET short_name = NULL
WHERE id = 1791 AND short_name = '119 W 23rd St, New York, NY 10011';


-- ─────────────────────────────────────────────────────────────────────────────
-- FIX 2: Redundant short_name = name → set short_name to NULL
-- (64 locations where short_name is identical to name, providing no value)
-- ─────────────────────────────────────────────────────────────────────────────

UPDATE locations SET short_name = NULL
WHERE short_name = name AND LENGTH(name) > 10;


-- ─────────────────────────────────────────────────────────────────────────────
-- FIX 3: Duplicate short_name — "ISCP" used by two different venues
-- The Intrepid's common abbreviation is "Intrepid", not "ISCP"
-- ─────────────────────────────────────────────────────────────────────────────

UPDATE locations
SET short_name = 'Intrepid Museum', very_short_name = 'Intrepid'
WHERE id = 413 AND name = 'Intrepid Sea, Air & Space Museum';


-- ─────────────────────────────────────────────────────────────────────────────
-- FIX 4: Acronym short_names → move to very_short_name
-- These are all <=6 char abbreviations sitting in short_name with no
-- very_short_name set. Move them to very_short_name.
-- For names > 30 chars, also set a medium-length short_name.
-- ─────────────────────────────────────────────────────────────────────────────

-- Names <= 30 chars: just move acronym to vsn, no short_name needed
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3523; -- Arts Project of Cherry Grove (28) → vsn: APCG
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3637; -- Arts Society of Kingston (24) → vsn: ASK
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3524; -- BACCA Arts Center (17) → vsn: BACCA
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3518; -- Catskill Art Space (18) → vsn: CAS
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 2712; -- City College of New York (24) → vsn: CCNY
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3373; -- Delaware Valley Arts Alliance (29) → vsn: DVAA
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3569; -- Downtown Music Gallery (22) → vsn: DMG
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3721; -- Fourth Arts Block (17) → vsn: FABnyc
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3535; -- Hudson Valley MOCA (18) → vsn: HVMOCA
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3374; -- Hudson Valley Writers Center (28) → vsn: HVWC
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3357; -- Inter-Media Art Center (22) → vsn: IMAC
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3368; -- Long Island Children's Museum (29) → vsn: LICM
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 1521; -- Manhattan Neighborhood Network (30) → vsn: MNN
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3203; -- Mayo Performing Arts Center (27) → vsn: MPAC
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 2797; -- New Jersey City University (26) → vsn: NJCU
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 2982; -- New York Theatre Workshop (25) → vsn: NYTW
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3066; -- Please Don't Tell (PDT) (23) → vsn: PDT
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3496; -- Poetry Society of America (25) → vsn: PSA
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3697; -- School of American Ballet (25) → vsn: SAB
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3720; -- Tiger Strikes Asteroid (22) → vsn: TSA
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3403; -- Women's Studio Workshop (23) → vsn: WSW
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3578; -- TEMPO Performing Arts Center (28) → vsn: TEMPO
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 3413; -- Theatre of the Oppressed NYC (28) → vsn: TONYC
UPDATE locations SET very_short_name = short_name, short_name = NULL WHERE id = 2734; -- U.S. Merchant Marine Academy (28) → vsn: USMMA

-- Names > 30 chars: move acronym to vsn AND set a medium short_name
UPDATE locations SET very_short_name = 'AAWW',   short_name = 'Asian American Writers'    WHERE id = 3417; -- Asian American Writers' Workshop (32)
UPDATE locations SET very_short_name = 'BCTR',   short_name = 'Brooklyn Theatre Research' WHERE id = 2561; -- Brooklyn Center for Theatre Research (36)
UPDATE locations SET very_short_name = 'CARA',   short_name = NULL                        WHERE id = 3723; -- CARA (Center for Art, Research and Alliances) — name starts with CARA
UPDATE locations SET very_short_name = 'CPR',    short_name = 'Performance Research'      WHERE id = 3399; -- Center for Performance Research (31)
UPDATE locations SET very_short_name = 'HICCC',  short_name = 'Irving Cancer Center'      WHERE id = 2703; -- Herbert Irving Comprehensive Cancer Center (42)
UPDATE locations SET very_short_name = 'ISAW',   short_name = 'Ancient World Institute'   WHERE id = 2720; -- Institute for the Study of the Ancient World (44)
UPDATE locations SET very_short_name = 'ISCP',   short_name = 'Intl Studio & Curatorial'  WHERE id = 3707; -- International Studio & Curatorial Program (41)
UPDATE locations SET very_short_name = 'JASA',   short_name = 'Jewish Assoc. for Aging'   WHERE id = 2105; -- Jewish Association Serving the Aging (36)
UPDATE locations SET very_short_name = 'KCBC',   short_name = NULL                        WHERE id = 2979; -- KCBC (Kings County Brewers Collective) — name starts with KCBC
UPDATE locations SET very_short_name = 'KCCNY',  short_name = 'Korean Cultural Center'    WHERE id = 3319; -- Korean Cultural Center New York (31)
UPDATE locations SET very_short_name = 'LPAC',   short_name = 'LaGuardia PAC'             WHERE id = 3456; -- LaGuardia Performing Arts Center (32)
UPDATE locations SET very_short_name = 'MOSA',   short_name = NULL                        WHERE id = 3571; -- MOSA at Our Saviour's Atonement (31) — name starts with MOSA
UPDATE locations SET very_short_name = 'MoMath', short_name = 'Museum of Math'            WHERE id = 2607; -- National Museum of Mathematics (MoMath) (39)
UPDATE locations SET very_short_name = 'NJPAC',  short_name = 'NJ Performing Arts'        WHERE id = 2969; -- New Jersey Performing Arts Center (33)
UPDATE locations SET very_short_name = 'DORIS',  short_name = 'NYC Records & Info'        WHERE id = 1544; -- NYC Dept of Records and Information Services (58)
UPDATE locations SET very_short_name = 'QPAC',   short_name = 'Queensborough PAC'         WHERE id = 3337; -- Queensborough Performing Arts Center (36)
UPDATE locations SET very_short_name = 'SOPAC',  short_name = 'South Orange PAC'          WHERE id = 2973; -- South Orange Performing Arts Center (35)
UPDATE locations SET very_short_name = 'SSRC',   short_name = 'Social Science Research'   WHERE id = 2898; -- Social Science Research Council (31)
UPDATE locations SET very_short_name = 'VLA',    short_name = 'Volunteer Lawyers'         WHERE id = 3627; -- Volunteer Lawyers for the Arts (30)
UPDATE locations SET very_short_name = 'WAAM',   short_name = 'Woodstock Artists'         WHERE id = 3409; -- Woodstock Artists Association & Museum (38)
UPDATE locations SET very_short_name = 'WHBPAC', short_name = 'Westhampton Beach PAC'     WHERE id = 3218; -- Westhampton Beach Performing Arts Center (40)
UPDATE locations SET very_short_name = 'WPPAC',  short_name = 'White Plains PAC'          WHERE id = 3193; -- White Plains Performing Arts Center (35)


-- ─────────────────────────────────────────────────────────────────────────────
-- FIX 5: Too-long very_short_names (> 10 chars) → shorten
-- (ID 959 handled in Fix 7 below)
-- ─────────────────────────────────────────────────────────────────────────────

UPDATE locations SET very_short_name = 'AAAL'      WHERE id = 1814; -- American Academy of Arts and Letters — was "Arts & Letters" (14)
UPDATE locations SET very_short_name = 'Palisades' WHERE id = 1916; -- Palisades Interstate Park — was "Palisades Park" (14)
-- ID 634 (Ornithology Jazz Club): "Ornithology" (11 chars) — borderline, leave as-is
-- ID 705 (Foster Park Rec Center): "Foster Park" (11 chars) — borderline, leave as-is


-- ─────────────────────────────────────────────────────────────────────────────
-- FIX 6: Too-long short_names (> 25 chars) → shorten
-- ─────────────────────────────────────────────────────────────────────────────

-- Already have very_short_name — just shorten the short_name
UPDATE locations SET short_name = 'Caribbean Cultural Ctr'  WHERE id = 2289; -- was "Caribbean Cultural Center African Diaspora Institute" (52), vsn: CCCADI
UPDATE locations SET short_name = 'African Diasporan Arts'  WHERE id = 1532; -- was "Museum of Contemporary African Diasporan Arts" (45), vsn: MoCADA
UPDATE locations SET short_name = 'Jamaica Arts & Learning' WHERE id = 433;  -- was "Jamaica Center for Arts and Learning" (36), vsn: JCAL
UPDATE locations SET short_name = 'Niarchos Foundation'     WHERE id = 791;  -- was "Stavros Niarchos Foundation Library" (35), vsn: SNFL
UPDATE locations SET short_name = 'Jamaica Performing Arts' WHERE id = 434;  -- was "Jamaica Performing Arts Center" (30), vsn: JPAC
UPDATE locations SET short_name = 'American Indian Museum'  WHERE id = 1273; -- was "Museum of the American Indian" (29), vsn: NMAI
UPDATE locations SET short_name = 'Kew Gardens Center',         very_short_name = 'KGCC' WHERE id = 1965; -- was "Kew Gardens Community Center" (28), vsn: KGCC

-- No very_short_name — shorten short_name and add vsn where obvious
UPDATE locations SET short_name = 'Charles Young Playground'                   WHERE id = 122;  -- was "Brig. Gen. Charles Young Playground" (35)
UPDATE locations SET short_name = NULL,  very_short_name = 'ICP'  WHERE id = 412;  -- was "International Center of Photography" (35)
UPDATE locations SET short_name = 'Ethical Culture'                            WHERE id = 611;  -- was "NY Society for Ethical Culture" (30)
UPDATE locations SET short_name = 'R&H Sound Archives'                        WHERE id = 885;  -- was "Rodgers and Hammerstein Archives" (32)
UPDATE locations SET short_name = 'Forest Hills Center',      very_short_name = 'FHCC' WHERE id = 1963; -- was "Forest Hills Community Center" (29)
UPDATE locations SET short_name = 'Atlantic Cornerstone'                      WHERE id = 3290; -- was "Atlantic Terminal Cornerstone" (29)
UPDATE locations SET short_name = 'Sugar Hill Museum'                         WHERE id = 799;  -- was "Sugar Hill Children's Museum" (28)
UPDATE locations SET short_name = 'St. Paul & St. Andrew'                     WHERE id = 1573; -- was "St. Paul & St. Andrew Church" (28)
UPDATE locations SET short_name = 'NY Insight Meditation'                     WHERE id = 607;  -- was "NY Insight Meditation Center" (28)
UPDATE locations SET short_name = 'St. Nicholas Garden'                       WHERE id = 1563; -- was "St. Nicholas Miracle Garden" (27)
UPDATE locations SET short_name = 'Gouverneur Farmstand'                      WHERE id = 623;  -- was "Gouverneur Health Farmstand" (27)
UPDATE locations SET short_name = 'Episcopal Sunnyside'                       WHERE id = 3491; -- was "Episcopal Mission Sunnyside" (27)
UPDATE locations SET short_name = 'Foster Park & Rec'                         WHERE id = 705;  -- was "Rev. T. Wendell Foster Park" (27), vsn already: "Foster Park"
UPDATE locations SET short_name = 'Sacred Hearts Church'                      WHERE id = 2258; -- was "Sacred Hearts & St. Stephen" (27)
UPDATE locations SET short_name = 'Lenfest Center'                            WHERE id = 217;  -- was "Lenfest Center for the Arts" (27)
UPDATE locations SET short_name = 'Resnick-Passlof'                           WHERE id = 1869; -- was "Resnick-Passlof Foundation" (26)
UPDATE locations SET short_name = 'NYPL Schwarzman'                           WHERE id = 609;  -- was "NYPL - Schwarzman Building" (26)
UPDATE locations SET short_name = 'Fairfield Inn'                             WHERE id = 2438; -- was "Fairfield Inn Times Square" (26)
UPDATE locations SET short_name = 'Reformed Church'                           WHERE id = 3732; -- was "Reformed Church Bronxville" (26)
UPDATE locations SET short_name = 'Italian Cultural Inst'                     WHERE id = 424;  -- was "Italian Cultural Institute" (26)


-- ─────────────────────────────────────────────────────────────────────────────
-- FIX 7: Long names with active events — add short_name and/or very_short_name
-- ─────────────────────────────────────────────────────────────────────────────

UPDATE locations SET short_name = 'Bronx Historical Society', very_short_name = 'BCHS'
WHERE id = 2021; -- Bronx County Historical Society Research Center (47)

UPDATE locations SET short_name = 'Jamaica Bay Wildlife'
WHERE id = 2037; -- Jamaica Bay Wildlife Refuge Visitor Center (42)

UPDATE locations SET short_name = 'Adelphi Performing Arts'
WHERE id = 3452; -- Adelphi University Performing Arts Center (41)

UPDATE locations SET short_name = 'Vanderbilt Hall'
WHERE id = 943;  -- Vanderbilt Hall at Grand Central Terminal (41)

UPDATE locations SET short_name = 'Weill Recital Hall', very_short_name = 'Carnegie'
WHERE id = 959;  -- Weill Recital Hall at Carnegie Hall (35) — was vsn: "Carnegie Hall" (13, too long)

UPDATE locations SET short_name = 'Cathedral of St. John'
WHERE id = 183;  -- Cathedral of St. John the Divine (32)

-- ID 734 (Schomburg Center for Research in Black Culture): already has short_name = "Schomburg Center" — no change needed
