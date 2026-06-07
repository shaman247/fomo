# Tag System Documentation

This directory contains the tag filtering, search, and color management functionality for the events application.

## Table of Contents

1. [Overview](#overview)
2. [Module Architecture](#module-architecture)
3. [Tag States](#tag-states)
4. [Filtering Logic](#filtering-logic)
5. [Scoring System](#scoring-system)
6. [Data Flow](#data-flow)
7. [Configuration](#configuration)

---

## Overview

The tag system provides advanced filtering and search capabilities with support for:
- Multiple tag states (selected, required, forbidden, unselected)
- Color-coded tag representation
- Multi-tag scoring for search results
- Proximity and temporal scoring

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

#### `tagStateManager.js`
**Purpose**: Manages tag states and button rendering.

**Key Features**:
- Tracks tag states (selected/required/forbidden/unselected)
- Creates and updates tag buttons with proper styling
- Handles state cycling on user interaction
- Applies colors and visual states

**Public API**:
```javascript
TagStateManager.init({ tagStates, colorProvider, onFilterChangeCallback, defaultMarkerColor })
TagStateManager.createInteractiveTagButton(tag)
TagStateManager.setTagState(tag, state)
TagStateManager.getTagState(tag)
```

#### `selectedTagsDisplay.js`
**Purpose**: Manages the display of selected tags above the search input.

> **Retired**: now a no-op stub — selected tags are shown in the FilterPanelUI chip bar.

**Key Features**:
- Displays selected tags as interactive pill buttons
- Skips tags already shown as quick filter chips

**Public API**:
```javascript
SelectedTagsDisplay.init({ containerDOM, quickFilterTags, getSelectedTagsWithColors, createInteractiveTagButton })
SelectedTagsDisplay.render() // Re-render the display
```

#### `searchManager.js`
**Purpose**: Handles search and scoring logic.

**Key Features**:
- Searches across locations, events, and tags
- Multi-tag match scoring
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

Tags can be in one of four states:

1. **`unselected`** (default)
   - Gray background
   - Not included in filtering

2. **`selected`** (click once)
   - Colored background with assigned color
   - Events must match at least ONE selected tag (OR logic)

3. **`required`** (right-click to cycle)
   - Colored background with glow border
   - Events must match ALL required tags (AND logic)
   - Takes precedence over selected tags

4. **`forbidden`** (right-click to cycle)
   - Strikethrough styling
   - Events with this tag are excluded
   - Overrides all other tag states

**State Cycling**: Left-click cycles: unselected <-> selected. Right-click cycles: unselected -> selected -> required -> forbidden -> unselected.

---

## Filtering Logic

Filtering determines which events appear on the map and in results.

### Filter Manager (`filterManager.js`)

**Function**: `filterEventsByTags(tagStates, baseEvents)`

### Filtering Rules (Priority Order)

1. **Forbidden Tags** (Highest Priority)
   - If event has ANY forbidden tag -> **EXCLUDE**
   - Overrides all other rules

2. **Required Tags**
   - If required tags exist, event must have **ALL** required tags -> **INCLUDE**
   - If event doesn't have all required tags -> **EXCLUDE**

3. **Selected Tags**
   - If selected tags exist, event must have **AT LEAST ONE** -> **INCLUDE**
   - OR logic: matches any selected tag

4. **No Tags Selected**
   - **INCLUDE** all events (no filtering)

### Pseudocode

```javascript
function filterEvent(event, tagStates) {
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

  // 3. Check selected tags (OR logic)
  const selectedTags = getSelectedTags(tagStates);
  if (selectedTags.length > 0) {
    return hasAnySelectedTag(eventTags, selectedTags) ? INCLUDE : EXCLUDE;
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

#### Multi-Tag Match
- **Value**: `+3` per matching tag
- **When**: 2+ tags selected AND item has matching tag(s)

**Example**:
```javascript
// Selected: "Art", "Music"
// Event has: ["Art", "Music", "Festival"]

Score contribution:
  Art: 3.0
  Music: 3.0
  Total tag score = 6.0
```

#### Visibility Boost
- **Value**: `+5`
- **When**: Item is currently visible on the map

#### Proximity Bonus
- **Value**: `0` to `+5`
- **When**: Within 20km of map center
- **Formula**: `5 * (1 - distance / 20000)`

#### Temporal Bonus (Events Only)
- **Value**: `0` to `+5`
- **When**: Event within 30 days of selected date
- **Formula**: `5 * (1 - timeDistance / 30days)`
- **Special**: +5 day bonus if ongoing on selected date

#### Exact Tag Match (Tag Search)
- **Value**: `+1000`
- **When**: Searching tags and exact match found

#### Visible Tag Frequency (Tag Search)
- **Value**: `frequency * 5`
- **When**: Tag is used by visible events

### Total Score Example

```javascript
Event: "Art Gallery Opening"
Tags: ["Art", "Gallery"]
Distance: 2km from center
Date: 3 days from selected date
Visible: Yes
Filtered: Yes (matches selected tags)

Selected tags: "Art", "Gallery"

Calculation:
  Base:           1
  Matching:      +10  (event matches filters)
  Tag matches:   +6.0 (Art: 3, Gallery: 3)
  Visibility:    +5   (currently visible)
  Proximity:     +4.5 (2km: 5 * (1 - 2000/20000))
  Temporal:      +4.5 (3 days: 5 * (1 - 3/30))

  Total Score:   31.0
```

## Data Flow

### 1. Tag Selection Flow

```
User clicks tag
    |
TagStateManager.cycleTagState()
    |
State changes: unselected -> selected -> required -> forbidden
    |
TagColorManager.assignColorToTag() (if selected/required)
    |
onFilterChangeCallback() triggers
    |
App.updateSelectedTagsDisplay()
App.filterAndDisplayEvents()
```

### 2. Filtering Flow

```
App.filterAndDisplayEvents()
    |
Get tag states: FilterPanelUI.getTagStates()
    |
FilterManager.filterEventsByTags(tagStates, events)
    |
Filter by rules (forbidden -> required -> selected -> none)
    |
Return filtered events
    |
Update map markers and UI
```

### 3. Search Flow

```
User types in search
    |
App.performSearch(term)
    |
Get selected tags: TagColorManager.getSelectedTagsWithColors()
    |
SearchManager.search(term, frequencies, selectedTagsWithColors)
    |
Create selected tags set for scoring
    |
Search locations, events, tags
    |
Apply scoring for each result
    |
Group and sort results by score
    |
FilterPanelUI.render(results, term, debugMode)
    |
Display search results with scores (if debug mode)
```

---

## Configuration

### Score Weights

**File**: `js/tags/searchManager.js`

**Constants**:
```javascript
const SCORE_WEIGHTS = {
  MATCHING_BOOST: 10,        // Boost for items matching filters
  MULTI_TAG_MATCH: 3,        // Points per matched tag
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

### Debug Mode

Enable debug mode via keyboard shortcut to see:
- Score values next to search results
- Detailed tag information in console
- Filter and search decision logging

---

## Troubleshooting

### Problem: Scoring seems wrong

**Check**:
1. Enable debug mode to see actual scores
2. Check `SCORE_WEIGHTS` constants in searchManager.js

### Problem: Filtering includes wrong events

**Check**:
1. Check tag states (forbidden tags override everything)
2. Check event tags and location tags (both are combined)
3. Verify `eventTagIndex` is properly built

---

## Summary

The tag system provides filtering and search with:
- **4 tag states** for fine-grained control
- **Multi-tag scoring** for relevant ranking
- **Color-coded tags** for visual clarity
- **Optimized performance** via tag indexing
- **Debug capabilities** for troubleshooting
