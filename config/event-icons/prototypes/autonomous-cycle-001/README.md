# Cycle 001 construction sources

Original SVGs for kintsugi, ikebana, arcade gaming, personal oral storytelling and bead stringing. No external artwork or brand marks are copied. `scene.py` defines three mesh scenes; `flat_art.py` draws two simple flat diagrams. `project.py` is adapted from this repository's technique-ten projector and clips faces by relative depth before merging visible paint regions. Polygon normals handle collapsed pole vertices. Broad petal paint reduces ikebana from 11,897 raw / 3,933 gzip bytes to 6,534 / 2,374.

Run from repository root with the existing venv:

```sh
./venv/bin/python config/event-icons/prototypes/autonomous-cycle-001/scene.py
./venv/bin/python config/event-icons/prototypes/autonomous-cycle-001/views.py
./venv/bin/python config/event-icons/prototypes/autonomous-cycle-001/project.py
./venv/bin/python config/event-icons/prototypes/autonomous-cycle-001/flat_art.py
```

Outputs go to `.scratch/icon-cycles-20260909/cycle-001/`. `views.py` creates six orthographic views from the authoritative meshes. The final styled projections use the same scene geometry. Camera, dimensions and contact assumptions live in `scene.py`; the [geometry record](geometry-review.json) describes visual inspection coverage. New source changes require fresh visual review. Existing final records are in [cycle acceptance](../../20260909-autonomous-cycle-001-visual.json).

Kintsugi's connected ceramic bowl and gold repair seams follow the material description from [Japan House London](https://www.japanhouselondon.uk/read-and-watch/kintsugi/). Ikebana uses an illustrative asymmetric arrangement in a shallow vessel with stems fixed in a kenzan, a construction described in [Web Japan's ikebana factsheet](https://web-japan.org/factsheet/en/pdf/e27_ikebana.pdf); it does not reproduce a named school's formal arrangement. The generic arcade cabinet uses a screen, supported control deck, joystick and action buttons, consistent with [HighScoreSaves' arcade control explanation](https://www.highscoresaves.com/Arcade-Knowledge-News/How-Do-Arcade-Controls-Work-Joysticks-Buttons-Microswitches-and-Ground/). These sources informed structure, not copied paths or textures.

The storytelling picture is a flat microphone/speech-bubble diagram. It deliberately avoids a book and does not assert that every oral story is a children's read-aloud session. Bead stringing is a flat overhead diagram with a continuous needle-thread connection and an unfinished string of beads. No human figure was generated in this cycle.
