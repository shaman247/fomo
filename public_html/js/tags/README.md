# Tag System Documentation

This directory contains the tag filtering, search, and related tags functionality for the events application.

## Table of Contents

1. [Overview](#overview)
2. [Module Architecture](#module-architecture)
3. [Tag States](#tag-states)
4. [Related Tags System](#related-tags-system)
5. [Filtering Logic](#filtering-logic)
6. [Scoring System](#scoring-system)
7. [Visual Representation](#visual-representation)
8. [Data Flow](#data-flow)
9. [Configuration](#configuration)

---

## Overview

The tag system provides advanced filtering and search capabilities with support for:
- Multiple tag states (selected, required, forbidden, unselected)
- Related tag enrichment with configurable weights
- Weighted scoring for search results
- Visual distinction between explicit and implicit tag selection
- Color-coded tag representation

---

## Module Architecture

### Core Modules

#### `tagColorManager.js`
**Purpose**: Manages color assignments for selected tags.

**Key Features**:
- Assigns colors from theme-appropriate palette (dark/light)
- Maintains selection order
- Handles color reuse when palette is exhausted
- Reassigns colors on theme changes

**Public API**:
```javascript
TagColorManager.init({ darkPalette, lightPalette })
TagColorManager.getSelectedTags() // Returns array of tag names
TagColorManager.getSelectedTagsWithColors() // Returns [tag, color] tuples
TagColorManager.assignColorToTag(tag)
TagColorManager.unassignColorFromTag(tag)
```

#### `relatedTagsManager.js`
**Purpose**: Manages related tag relationships and enrichment.

**Key Features**:
- Loads related tag data from JSON file
- Enriches selected tags with related tags and weights
- Handles weight conflicts (keeps maximum weight)
- Provides tag name extraction utilities

**Public API**:
```javascript
RelatedTagsManager.init({ relatedTagsUrl })
RelatedTagsManager.enrichSelectedTags(selectedTagsWithColors)
// Returns: [[tag, color, weight], ...] tuples
RelatedTagsManager.getAllTagsFromEnriched(enrichedTags)
// Returns: [tag, ...] array
```

#### `tagStateManager.js`
**Purpose**: Manages tag states and button rendering.

**Key Features**:
- Tracks tag states (selected/required/forbidden/unselected)
- Creates and updates tag buttons with proper styling
- Handles state cycling on user interaction
- Applies colors and visual states including implicit selection

**Public API**:
```javascript
TagStateManager.init({ tagStates, getTagColor, isImplicitlySelected, ... })
TagStateManager.createInteractiveTagButton(tag)
TagStateManager.setTagState(tag, state)
TagStateManager.getTagState(tag)
```

#### `selectedTagsDisplay.js`
**Purpose**: Manages the display of selected tags above the search input.

**Key Features**:
- Displays explicitly selected tags as interactive buttons
- Provides add/remove toggle for related (implicit) tags
- Controls whether implicit tags affect search and map filtering
- Coordinates with TagColorManager for tag data

**Public API**:
```javascript
SelectedTagsDisplay.init({ containerDOM, getSelectedTagsWithColors, createInteractiveTagButton, onRelatedTagsToggle })
SelectedTagsDisplay.render() // Re-render the display
SelectedTagsDisplay.isIncludingRelatedTags() // Returns boolean
SelectedTagsDisplay.setIncludeRelatedTags(include) // Set toggle state
SelectedTagsDisplay.getEffectiveSelectedTags() // Returns tag names based on toggle state
SelectedTagsDisplay.getEffectiveSelectedTagsWithColors() // Returns [tag, color, weight] tuples
```

#### `searchManager.js`
**Purpose**: Handles search and scoring logic.

**Key Features**:
- Searches across locations, events, and tags
- Weighted tag scoring with related tag support
- Proximity-based scoring
- Temporal scoring for events
- Visibility and matching bonuses

**Public API**:
```javascript
SearchManager.init({ appState })
SearchManager.search(term, dynamicFrequencies, selectedTagsWithColors)
SearchManager.groupAndSortResults(results, term, getSelectedLocationKey, getTagState)
```

---

## Tag States

Tags can be in one of four explicit states, plus one implicit state:

### Explicit States
1. **`unselected`** (default)
   - Gray background
   - Not included in filtering

2. **`selected`** (click once)
   - Red background with assigned color
   - Events must match at least ONE selected tag (OR logic)
   - Weight: 1.0 for scoring

3. **`required`** (click twice)
   - Red background with glow border
   - Events must match ALL required tags (AND logic)
   - Weight: 1.0 for scoring
   - Takes precedence over selected tags

4. **`forbidden`** (click three times)
   - Strikethrough styling
   - Events with this tag are excluded
   - Overrides all other tag states

### Implicit State
5. **`related`** (implicit via relationships)
   - Semi-transparent red background with dashed border
   - Not directly clicked by user
   - Included via related tag relationships
   - Weight: configured in `related_tags.json` (e.g., 0.7, 0.8)

**State Cycling**: Click repeatedly to cycle: unselected → selected → required → forbidden → unselected

---

## Related Tags System

### Purpose
Automatically include semantically related tags when a tag is selected, with configurable weights for scoring.

### Configuration File
**Location**: `public_html/data/related_tags.json`

**Format**:
```json
{
  "ParentTag": [
    ["RelatedTag1", weight],
    ["RelatedTag2", weight]
  ]
}
```

**Example**:
```json
{
  "Art": [
    ["Contemporary Art", 0.8],
    ["Digital Art", 0.7]
  ],
  "Family": [
    ["Kids", 0.8]
  ]
}
```

### Weight Semantics

**Range**: 0.0 to 1.0

**Interpretation**:
- `1.0` = Full weight (same as explicitly selected)
- `0.8` = 80% as relevant as the parent tag
- `0.5` = 50% as relevant as the parent tag

**Usage in System**:
1. **Filtering**: Related tags are treated as selected (binary: included or not)
2. **Scoring**: Related tags contribute proportionally to their weight
   - Score contribution = `weight × MULTI_TAG_MATCH` (default: `weight × 3`)

### Enrichment Process

**Step 1: Get Selected Tags**
```javascript
const selectedTagsWithColors = TagColorManager.getSelectedTagsWithColors();
// Example: [["Art", "#b03540"], ["Family", "#3d8578"]]
```

**Step 2: Enrich with Related Tags**
```javascript
const enrichedTags = RelatedTagsManager.enrichSelectedTags(selectedTagsWithColors);
// Returns: [
//   ["Art", "#b03540", 1.0],              // explicit
//   ["Contemporary Art", "#b03540", 0.8], // related
//   ["Digital Art", "#b03540", 0.7],      // related
//   ["Family", "#3d8578", 1.0],           // explicit
//   ["Kids", "#3d8578", 0.8]              // related
// ]
```

**Step 3: Extract Tag Names**
```javascript
const allTags = RelatedTagsManager.getAllTagsFromEnriched(enrichedTags);
// Returns: ["Art", "Contemporary Art", "Digital Art", "Family", "Kids"]
```

### Conflict Resolution

**Scenario**: Tag appears as both explicit and related
- **Result**: Explicit selection wins (weight = 1.0)

**Scenario**: Tag is related to multiple selected tags with different weights
- **Result**: Maximum weight wins

**Example**:
```javascript
Selected: ["Art", "Gallery"]
Related:
  - Art → Contemporary Art (0.7)
  - Gallery → Contemporary Art (0.9)
Result: Contemporary Art weight = 0.9
```

---

## Filtering Logic

Filtering determines which events appear on the map and in results.

### Filter Manager (`filterManager.js`)

**Function**: `filterEventsByTags(tagStates, baseEvents, enrichedSelectedTags)`

### Filtering Rules (Priority Order)

1. **Forbidden Tags** (Highest Priority)
   - If event has ANY forbidden tag → **EXCLUDE**
   - Overrides all other rules

2. **Required Tags**
   - If required tags exist, event must have **ALL** required tags → **INCLUDE**
   - If event doesn't have all required tags → **EXCLUDE**

3. **Selected Tags** (including related)
   - If selected tags exist (explicit or implicit), event must have **AT LEAST ONE** → **INCLUDE**
   - Uses enriched tag list (includes related tags)
   - OR logic: matches any selected/related tag

4. **No Tags Selected**
   - **INCLUDE** all events (no filtering)

### Pseudocode

```javascript
function filterEvent(event, tagStates, enrichedSelectedTags) {
  const eventTags = getEventAndLocationTags(event);

  // 1. Check forbidden tags
  if (hasForbiddenTag(eventTags, tagStates)) {
    return EXCLUDE;
  }

  // 2. Check required tags (AND logic)
  const requiredTags = getRequiredTags(tagStates);
  if (requiredTags.length > 0) {
    return hasAllRequiredTags(eventTags, requiredTags) ? INCLUDE : EXCLUDE;
  }

  // 3. Check selected tags (OR logic, includes related tags)
  if (enrichedSelectedTags.length > 0) {
    return hasAnySelectedTag(eventTags, enrichedSelectedTags) ? INCLUDE : EXCLUDE;
  }

  // 4. No filters active
  return INCLUDE;
}
```

### Tag Index Optimization

For performance, filtering uses a tag index:
```javascript
eventTagIndex = {
  "Art": [event1.id, event5.id, event12.id],
  "Music": [event2.id, event8.id],
  // ...
}
```

This allows quick lookup of events by tag without iterating all events.

---

## Scoring System

Scoring ranks search results by relevance.

### Score Components

#### Base Score
- **Value**: `1`
- All results start with this base

#### Matching Boost
- **Value**: `+10`
- **When**: Item matches current filter criteria
- **Purpose**: Prioritize filtered items

#### Multi-Tag Match (Weighted)
- **Value**: `weight × 3` per matching tag
- **When**: 2+ tags selected AND item has matching tag(s)
- **Calculation**:
  ```javascript
  for each tag in item:
    if tag in selectedTagsWithWeights:
      score += weight × 3
  ```

**Examples**:
```javascript
// Selected: "Art" (explicit, w=1.0), "Contemporary Art" (related, w=0.8)
// Event has: ["Contemporary Art", "Gallery"]

Score contribution:
  Contemporary Art: 0.8 × 3 = 2.4
  Total weighted score = 2.4
```

```javascript
// Selected: "Art" (w=1.0), "Music" (w=1.0)
// Event has: ["Art", "Music", "Festival"]

Score contribution:
  Art: 1.0 × 3 = 3.0
  Music: 1.0 × 3 = 3.0
  Total weighted score = 6.0
```

#### Visibility Boost
- **Value**: `+5`
- **When**: Item is currently visible on the map
- **Purpose**: Prioritize items in current viewport

#### Proximity Bonus
- **Value**: `0` to `+5`
- **When**: Within 20km of map center
- **Formula**: `5 × (1 - distance / 20000)`
- **Purpose**: Prefer nearby items

#### Temporal Bonus (Events Only)
- **Value**: `0` to `+5`
- **When**: Event within 30 days of selected date
- **Formula**: `5 × (1 - timeDistance / 30days)`
- **Special**: +5 day bonus if ongoing on selected date
- **Purpose**: Prefer temporally relevant events

#### Exact Tag Match (Tag Search)
- **Value**: `+1000`
- **When**: Searching tags and exact match found
- **Purpose**: Exact matches appear first

#### Visible Tag Frequency (Tag Search)
- **Value**: `frequency × 5`
- **When**: Tag is used by visible events
- **Purpose**: Suggest relevant tags based on visible content

### Total Score Example

```javascript
Event: "Art Gallery Opening"
Tags: ["Contemporary Art", "Gallery"]
Distance: 2km from center
Date: 3 days from selected date
Visible: Yes
Filtered: Yes (matches selected tags)

Selected tags: "Art" (w=1.0), "Contemporary Art" (related w=0.8)

Calculation:
  Base:           1
  Matching:      +10  (event matches filters)
  Weighted tags: +2.4 (Contemporary Art: 0.8 × 3)
  Visibility:    +5   (currently visible)
  Proximity:     +4.5 (2km: 5 × (1 - 2000/20000))
  Temporal:      +4.5 (3 days: 5 × (1 - 3/30))

  Total Score:   27.4
```

## Data Flow

### 1. Tag Selection Flow

```
User clicks tag
    ↓
TagStateManager.cycleTagState()
    ↓
State changes: unselected → selected → required → forbidden
    ↓
TagColorManager.assignColorToTag() (if selected/required)
    ↓
onFilterChangeCallback() triggers
    ↓
App.updateSelectedTagsDisplay()
App.filterAndDisplayEvents()
```

### 2. Filtering Flow

```
App.filterAndDisplayEvents()
    ↓
Get selected tags: TagColorManager.getSelectedTagsWithColors()
    ↓
Enrich with related: RelatedTagsManager.enrichSelectedTags()
    ↓
Extract all tags: RelatedTagsManager.getAllTagsFromEnriched()
    ↓
Identify implicit tags: enriched - explicit
    ↓
Store in state.implicitlySelectedTags
    ↓
FilterManager.filterEventsByTags(tagStates, events, enrichedTags)
    ↓
Filter by rules (forbidden → required → selected → none)
    ↓
Return filtered events
    ↓
Update map markers and UI
```

### 3. Search Flow

```
User types in search
    ↓
App.performSearch(term)
    ↓
Get selected tags: TagColorManager.getSelectedTagsWithColors()
    ↓
Enrich with related: RelatedTagsManager.enrichSelectedTags()
    ↓
SearchManager.search(term, frequencies, enrichedTagsWithWeights)
    ↓
Create weights map: tag → weight
    ↓
Search locations, events, tags
    ↓
Apply weighted scoring for each result
    ↓
Group and sort results by score
    ↓
FilterPanelUI.render(results, term, debugMode)
    ↓
Display search results with scores (if debug mode)
```

### 4. Related Tag Application

```
Explicit selection: User clicks "Art"
    ↓
TagColorManager: ["Art" → color "#b03540"]
    ↓
RelatedTagsManager.enrichSelectedTags([["Art", "#b03540"]])
    ↓
Load related_tags.json: "Art" → [["Contemporary Art", 0.8], ...]
    ↓
Build enriched list:
  ["Art", "#b03540", 1.0]              ← explicit
  ["Contemporary Art", "#b03540", 0.8] ← implicit
  ["Digital Art", "#b03540", 0.7]      ← implicit
    ↓
Filtering: Include events with Art OR Contemporary Art OR Digital Art
    ↓
Scoring: Weight matches by configured weights
    ↓
Visual: Mark "Contemporary Art" and "Digital Art" with .state-related class
```

---

## Configuration

### Related Tags JSON

**File**: `public_html/data/related_tags.json`

**Structure**:
```json
{
  "ParentTag": [
    ["RelatedTag", weight],
    ...
  ]
}
```

**Guidelines**:
- Use weights 0.0 - 1.0 for typical relationships
- Use weights > 1.0 for special emphasis (rare)
- Parent tag = explicitly selectable tag
- Related tags = implicitly included when parent selected
- Relationships are one-way (Art → Contemporary Art doesn't imply Contemporary Art → Art)

**Bidirectional Relationships** (if needed):
```json
{
  "Art": [["Contemporary Art", 0.8]],
  "Contemporary Art": [["Art", 0.8]]
}
```

### Score Weights

**File**: `js/tags/searchManager.js`

**Constants**:
```javascript
const SCORE_WEIGHTS = {
  MATCHING_BOOST: 10,        // Boost for items matching filters
  MULTI_TAG_MATCH: 3,        // Points per matched tag (× weight)
  VISIBILITY_BOOST: 5,       // Boost for visible items
  MAX_PROXIMITY_BONUS: 5,    // Max proximity bonus
  MAX_TEMPORAL_BONUS: 5,     // Max temporal bonus (events)
  EXACT_TAG_MATCH: 1000,     // Exact tag match in search
  VISIBLE_TAG_MULTIPLIER: 5  // Visible tag frequency multiplier
};
```

**Tuning Tips**:
- Increase `MULTI_TAG_MATCH` to emphasize multi-tag events
- Increase `VISIBILITY_BOOST` to prioritize visible items more
- Increase `MATCHING_BOOST` to strongly prefer filtered items
- Adjust `MAX_PROXIMITY_BONUS` for spatial relevance importance

### Color Palettes

**File**: `js/script.js` - `App.config`

**Configuration**:
```javascript
TAG_COLOR_PALETTE_DARK: [
  '#b03540', '#3d8578', '#c07030', ...
],
TAG_COLOR_PALETTE_LIGHT: [
  '#e08085', '#85c0b0', '#e8a875', ...
]
```

Colors are assigned in order as tags are selected. When palette is exhausted, colors wrap around.

---

## Debugging

### Console Logging

The system includes comprehensive console logging for debugging:

**Tag Enrichment**:
```
[RelatedTagsManager] enrichSelectedTags called
  Input tags: ["Art"]
  Initialized: true
  Added selected tag: Art with weight 1.0
  Found 2 related tags for: Art
    Added related tag: Contemporary Art with weight 0.8
    Added related tag: Digital Art with weight 0.7
  Output enriched tags: ["Art(1)", "Contemporary Art(0.8)", "Digital Art(0.7)"]
```

**Filtering**:
```
[App] updateFilteredEvents - using enriched tags for filtering: ["Art", "Contemporary Art", "Digital Art"]
[App] Implicitly selected (related) tags: ["Contemporary Art", "Digital Art"]
[FilterManager] filterEventsByTags called
  Selected tags (enriched): ["Art", "Contemporary Art", "Digital Art"]
  Filtered to 127 events using enriched tags
```

**Search**:
```
[App] performSearch called with term: "gallery"
[App] Selected tags from TagColorManager: ["Art"]
[App] Enriched tags: ["Art(1)", "Contemporary Art(0.8)", "Digital Art(0.7)"]
[SearchManager] performSearch called with term: gallery
  Selected tags with weights: Art(1), Contemporary Art(0.8), Digital Art(0.7)
    [SearchManager] Weighted tag matches: Contemporary Art(w:0.8, s:2.4), Gallery(w:1, s:3.0) Total: 5.4
[App] Search returned 42 results
```

### Debug Mode

Enable debug mode via keyboard shortcut to see:
- Score values next to search results
- Detailed tag weight information in console
- Filter and search decision logging

---

## Best Practices

### Adding Related Tags

1. **Semantic Relationships**: Only relate semantically similar tags
   - Good: "Art" → "Contemporary Art", "Digital Art"
   - Bad: "Art" → "Food", "Sports"

2. **Weight Calibration**:
   - Start with 0.7-0.9 for close relationships
   - Use 0.5-0.6 for looser relationships
   - Reserve 1.0 for equivalent terms

3. **Avoid Circular Dependencies**: While supported, they may cause unexpected behavior

4. **Test Impact**: After adding relationships, test filtering and scoring behavior

### Performance Considerations

1. **Tag Index**: The system uses tag indexes for fast filtering. Don't bypass this.

2. **Related Tags**: Keep relationship depth to 1 level (avoid chains)

3. **Search Debouncing**: Already implemented in the UI

4. **Console Logging**: Disable verbose logging in production if needed

### Maintenance

1. **Review related_tags.json** periodically
2. **Monitor tag usage patterns** in your dataset
3. **Adjust score weights** based on user feedback
4. **Clean up unused tags** from the configuration

---

## Future Enhancements

Potential improvements to consider:

1. **Bidirectional Relationships**: Auto-generate reverse relationships
2. **Tag Hierarchies**: Support parent-child tag trees
3. **Dynamic Weight Learning**: Adjust weights based on user behavior
4. **Tag Aliases**: Support multiple names for same concept
5. **Tag Recommendations**: Suggest tags based on selected tags
6. **Bulk Tag Operations**: Select/deselect multiple tags at once
7. **Tag Groups**: Group related tags for easier selection
8. **Saved Tag Combinations**: Save frequently used tag combinations

---

## Troubleshooting

### Problem: Related tags not appearing

**Check**:
1. Is `related_tags.json` loaded? Check console for errors.
2. Is `RelatedTagsManager.init()` called?
3. Are tag names spelled exactly the same (case-sensitive)?
4. Check console for enrichment logs.

### Problem: Related tags have wrong styling

**Check**:
1. Is `state.implicitlySelectedTags` populated? Check console logs.
2. Is `isImplicitlySelected` callback passed to TagStateManager?
3. Is CSS class `.state-related` defined in `tags.css`?

### Problem: Scoring seems wrong

**Check**:
1. Enable debug mode to see actual scores
2. Check console for weighted tag match logs
3. Verify weights in `related_tags.json`
4. Check `SCORE_WEIGHTS` constants in searchManager.js

### Problem: Filtering includes wrong events

**Check**:
1. Check console for enriched tags list
2. Verify tag states (forbidden tags override everything)
3. Check event tags and location tags (both are combined)
4. Verify `eventTagIndex` is properly built

---

## Summary

The tag system provides a sophisticated filtering and search experience with:
- **4 explicit states** + 1 implicit state for fine-grained control
- **Related tag enrichment** for semantic expansion
- **Weighted scoring** for relevant ranking
- **Visual distinction** between explicit and implicit selection
- **Optimized performance** via tag indexing
- **Debug capabilities** for troubleshooting

By combining these features, users can efficiently discover events that match their interests, even when using different terminology or conceptual frameworks.
