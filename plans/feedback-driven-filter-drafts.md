# Feedback-Driven Filter Drafts

## Summary

Add per-match thumbs up/down feedback in Daily results. Each vote is stored and immediately enqueues a feedback reflection job that proposes new draft filters linked to the parent filter that produced the match. The parent filter remains active; accepting a feedback draft creates an additional active filter. Add a Filters sidebar notification dot for unseen feedback-generated drafts. Add a Daily schedule setting in Settings, but persist it only and do not wire it to a scheduler yet.

## Key Changes

- Add a `paper_match_feedback` table/model:
  - `paper_match_id`, `search_run_id`, `filter_id`, `paper_id`
  - `value`: `"up"` or `"down"`
  - optional `note` reserved for future natural-language feedback
  - `created_at`, `updated_at`
  - enforce one current feedback row per paper match, updated if the user changes vote.
- Add feedback draft metadata to filter definitions for draft filters:
  - `source: "feedback"`
  - `parent_filter_id`
  - `feedback_id`
  - `paper_match_id`
  - `rationale`
  - keep `status: "draft"` so daily search ignores them until accepted.
- Add API endpoints:
  - `POST /paper-matches/{match_id}/feedback` with `{ value: "up" | "down" }`, returns feedback plus job id.
  - `GET /feedback/notifications` returning unseen feedback-draft count.
  - `POST /feedback/notifications/seen` marks current feedback drafts as seen.
  - Reuse existing draft promotion endpoint for accepting feedback drafts as new active filters.
- Add a feedback reflection worker job:
  - Loads the voted match, parent filter, paper metadata/abstract, match rationale, and nearby feedback for that parent filter.
  - Calls the LLM to propose 1-3 child draft filters that express "more like this" for upvotes and "avoid/deprioritize this subtopic" for downvotes.
  - Does not edit, archive, or replace the parent filter.
  - Stores draft filters linked to the parent filter and feedback event.
- Add frontend feedback controls:
  - Put compact thumbs up/down icon buttons on each `PaperMatchCard`.
  - Optimistically show selected state; allow changing between up/down.
  - On vote, call the new endpoint and invalidate feedback notification/filter draft queries.
- Add Filters page review UI:
  - Add a top "Feedback Suggestions" section for draft filters with `source: "feedback"`.
  - Group drafts by parent filter.
  - Show rationale and source paper title where available.
  - Accepting drafts promotes them to active filters; archiving/removing drafts dismisses them.
  - When the Filters page opens, call mark-seen so the sidebar dot clears.
- Add sidebar notification:
  - `AppShell` polls or queries feedback notification status.
  - Show a small dot on the Filters nav item when unseen feedback drafts exist.
- Add Settings-only daily schedule option:
  - Add persisted app setting for daily run time, e.g. `"daily_search_time": "09:00"`.
  - Show a time input/control in Settings.
  - Save and display it, but do not enqueue or run scheduled jobs yet.
  - Label it as configured but not active for the prototype.

## Public Interfaces / Types

- Add frontend types for `PaperMatchFeedback`, `FeedbackNotificationStatus`, and feedback draft metadata.
- Extend `PaperMatch` responses with optional current feedback value if practical; otherwise fetch feedback state through the feedback endpoint/list.
- Extend filter draft rendering to distinguish onboarding drafts from feedback-generated drafts using `definition.source`.

## Test Plan

- Backend API tests:
  - Creating up/down feedback for a valid match stores one row and enqueues a reflection job.
  - Re-voting the same match updates the existing row.
  - Invalid match IDs return 404.
  - Feedback drafts appear in `/filters?status=draft` and are linked to parent filter metadata.
  - Notification count increments for unseen feedback drafts and clears after mark-seen.
  - Daily schedule setting can be saved and read but does not enqueue jobs.
- Worker tests:
  - Reflection job creates draft filters from mocked LLM output.
  - Upvote/downvote context is included in the prompt.
  - Parent filter remains active and unchanged.
- Frontend tests:
  - Daily match cards render thumbs up/down and call the feedback API.
  - Sidebar shows/hides Filters notification dot.
  - Filters page shows feedback suggestions grouped by parent filter and clears notification on open.
  - Settings daily schedule control persists its value.

## Assumptions

- Feedback reflection runs immediately per vote, with no debounce or batching.
- Both thumbs up and thumbs down can generate draft filters.
- Feedback-generated filters are always reviewable drafts first; no automatic active-filter edits.
- Accepting a feedback draft adds it as a new active filter and does not replace the parent filter.
- Daily search scheduling is settings-only for now and intentionally not connected to background execution.
