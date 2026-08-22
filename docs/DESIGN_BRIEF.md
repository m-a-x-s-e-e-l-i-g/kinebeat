# Kinebeat design brief

Status: draft awaiting confirmation

## 1. Feature summary

Kinebeat is a local desktop editor for creators who want a compelling music video
without manually placing every cut and effect. It performs true source separation,
detects instrument events, and generates a complete editable timeline from a song and
an imported footage collection.

The result is intentionally almost automatic. The creator reviews the generated edit,
locks the decisions they like, rearranges clips when desired, and regenerates only the
unlocked clips, effects, or timeline ranges.

## 2. Primary user action

Generate a complete music-synchronised edit, then progressively keep the good decisions
by locking them while regenerating the rest.

## 3. Design direction

Kinebeat should feel fast, exact, kinetic, and creatively permissive. It inherits
Chronophoto's restrained specialist-tool character: near-black work surfaces, clear
hierarchy, media as the brightest object, plain-language controls, local processing,
and visible render state.

Unlike Chronophoto's still-image focus, Kinebeat's memorable visual object is the
musical timeline itself. Instrument events, locked decisions, and short effect bursts
must be readable at a glance without turning the interface into a full professional
non-linear editor.

## 4. Layout strategy

The workspace follows the user's actual sequence:

1. A prominent video preview remains the visual focus.
2. A compact song and footage setup area establishes the two required inputs.
3. A horizontally navigable timeline combines the waveform, instrument-event lanes,
   generated clips, effect markers, and lock state.
4. A contextual inspector exposes mapping and regeneration controls only for the
   current selection.
5. Background analysis and export remain visible and cancellable without blocking
   timeline review.

Advanced audio separation stays behind the automatic workflow. The interface reports
what was detected rather than presenting a stem-mixing workstation.

## 5. Key states

- **First run:** explain the song-first workflow and local processing in one concise
  empty workspace.
- **Song loaded:** show basic song identity and a clear analysis action/state.
- **Analysing music:** show separation and event-analysis progress, allow cancellation,
  and keep the application responsive.
- **Analysis failed:** preserve the selected song, explain the cause plainly, and offer
  retry or replacement.
- **Waiting for footage:** make importing clips the only prominent next action.
- **Generating:** show timeline-generation progress while preserving analysed music and
  imported footage.
- **Generated timeline:** preview, drag clips, lock any clip/effect/range, and regenerate
  any single item, selection, or all unlocked content.
- **Partially locked timeline:** distinguish locked content through shape and labels as
  well as colour.
- **Media unavailable:** retain timeline decisions and identify missing source files
  without silently discarding work.
- **Exporting:** use an immutable project snapshot, visible progress, cancellation, and
  a clear completed-output location.

## 6. Interaction model

The happy path is song, footage, generate, export. Generation always yields a timeline,
not an opaque finished file.

Users can:

- drag clips to change their timeline order;
- lock or unlock an individual clip, individual effect, arbitrary range, or any
  combination of those;
- regenerate one clip/effect, a selected range, or the entire unlocked timeline;
- choose among footage-selection strategies including import order, random,
  least-used-first, movement-based, subject-based, and manual ranking;
- assign detected instrument classes to cuts and effects;
- preview before exporting.

Regeneration must never modify locked decisions. Random generations need a reproducible
seed so the same project can be reopened and rendered deterministically.

## 7. Content requirements

The interface needs concise labels and messages for:

- loading and replacing a song;
- music separation and event-analysis progress;
- detection confidence or degraded analysis;
- importing, ranking, and locating footage;
- generating and regenerating selections;
- explaining exactly what a lock protects;
- unavailable media, unsupported codecs, and insufficient disk/GPU resources;
- preview quality versus source-resolution export;
- local/private processing and optional model downloads;
- export completion and output location.

## 8. Recommended implementation references

- `spatial-design.md` for the preview/timeline/inspector hierarchy;
- `typography.md` for a compact but readable desktop tool;
- `interaction-design.md` for selection, locking, drag-and-drop, and background states;
- `motion-design.md` for timeline regeneration and analysis feedback;
- `color-and-contrast.md` for instrument lanes and accessible lock states;
- `ux-writing.md` for analysis failures and first-run guidance.

## 9. Open questions

- Typical and maximum song length, footage count, total source duration, resolution,
  and frame rate.
- Which effect controls should be present in the first release: probability, duration,
  intensity, random parameter ranges, or all four.
- The first original effect set beyond beat cuts, short light effects, temporal bending,
  and luminance-driven pixel stretching.
- Initial export formats and whether editable Resolve/FCPXML export belongs in the MVP.
- Whether automatic project saving and crash recovery are required in the first usable
  build.
