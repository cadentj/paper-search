# Google Scholar Profile Onboarding Plan

## Summary

Allow researchers to onboard from a public Google Scholar profile URL. From the
Filters page, the user can click `Connect Google Scholar`, enter their profile
URL in a modal, verify that the URL resolves to a usable public research
profile, and start a separate background import job.

The import should propose draft filters from the researcher's publication
history without blocking the existing text/PDF filter generation flow. Google
Scholar parsing should be bounded and best-effort. Once publications are
identified, enrich them through open scholarly APIs where possible, with
Semantic Scholar as the preferred v1 source.

## Key Changes

- Add a `Connect Google Scholar` button to the top-right area of the Filters
  page, outside the current research-context input group.
- Add a modal that accepts a Google Scholar profile URL, verifies it, shows a
  compact profile preview, and starts the import.
- Add a new background job kind, `google_scholar_import`, independent from
  `onboarding_generation` and `document_processing`.
- Persist Google Scholar imports in a dedicated table so verification,
  progress, discovered publications, and errors are inspectable.
- Reuse existing draft filters:
  - Generated filters should be stored as `Filter(status="draft")`.
  - Drafts should continue to appear in the existing Draft Filters section.
  - Drafts remain inactive until the user accepts them.

## Backend Implementation

- Add a model such as `ResearchProfileImport` with:
  - `id`
  - `status`
  - `source_type`, with v1 value `"google_scholar"`
  - `source_url`
  - `normalized_url`
  - `external_profile_id`, populated from the Scholar `user` query param
  - `display_name`
  - `affiliation`
  - `interests`
  - `citation_metrics`
  - `publications`
  - `error`
  - timestamps
- Add schemas for:
  - verifying a Scholar URL
  - starting an import
  - returning a verified profile preview
  - returning import job state through the jobs API
- Add onboarding endpoints:
  - `POST /onboarding/google-scholar/verify`
  - `POST /onboarding/google-scholar/imports`
- Add a jobs endpoint:
  - `GET /jobs/google-scholar-import/{job_id}`
- Verification flow:
  - Validate that the URL is a supported Google Scholar citations profile URL.
  - Extract and normalize the `user` id.
  - Fetch the public profile page.
  - Parse name, affiliation, interests, citation metrics, and a small
    publication preview.
  - Return 400 with a user-readable reason if the URL is malformed, not public,
    blocked, or does not look like a Scholar profile.
- Import worker flow:
  - Mark the import and job as running.
  - Fetch bounded publication pages from the public Scholar profile.
  - Default cap: first 100 publications, or fewer if the profile ends earlier.
  - Do not use login, CAPTCHA bypass, proxy rotation, or other anti-bot bypass.
  - Parse publication title, year, citation count, and available publication
    links from Scholar.
  - Enrich each parsed publication through Semantic Scholar by title and author
    name.
  - Prefer enriched fields such as title, abstract, year, authors, venue,
    citation count, fields of study, external IDs, and URL.
  - Continue on partial enrichment failures and record them in job progress or
    import metadata.
  - Build a profile-context text from profile metadata, interests, top/recent
    publications, enriched abstracts, and fields of study.
  - Feed that context into the existing filter-generation path.
  - Create draft filters incrementally as the LLM returns complete filter
    objects.
  - Mark the import and job completed, or failed with a clear error.
- Add settings:
  - `SEMANTIC_SCHOLAR_API_KEY`, optional
  - `GOOGLE_SCHOLAR_IMPORT_MAX_PUBLICATIONS`, default `100`
  - `GOOGLE_SCHOLAR_IMPORT_TIMEOUT_SECONDS`, default suitable for a background
    job
- Keep the current text/PDF onboarding generation code path unchanged except
  for shared helper extraction if needed.

## Frontend Implementation

- Update `frontend/src/app/dashboard/filters/page.tsx`.
- Add a `Connect Google Scholar` button in the page header area, aligned to the
  right of the title/description block.
- Add a modal with states:
  - empty URL
  - verifying
  - verified
  - rejected
  - import queued/running
  - import failed
- Verified preview should show:
  - researcher name
  - affiliation
  - interests, if present
  - publication preview count/sample titles
- The modal should reject unsupported URLs with inline error text and keep the
  URL input editable.
- Starting the import should store the returned job id in local component state.
- Add `api.verifyGoogleScholarProfile`,
  `api.createGoogleScholarImport`, and `api.getGoogleScholarImportJob`.
- Add a React Query polling hook for the new job endpoint.
- While the Scholar import is active, show a small status card near Draft
  Filters, separate from the existing document-processing chips and existing
  generation status.
- Merge returned draft filters into the existing `["filters", "draft"]` query
  cache the same way `useOnboardingGenerationJob` does today.
- The existing research-context input, PDF upload, and document processing
  controls must remain usable while the Scholar import runs.

## Parsing And Enrichment Details

- Supported v1 URL shape:
  - `https://scholar.google.com/citations?user=<id>`
  - Allow extra query params such as `hl`, but canonicalize storage to the
    profile URL with the extracted `user` id.
- Scholar parser should be isolated in a service module so tests can use static
  HTML fixtures.
- Parser output should not be trusted as final publication metadata. Treat it
  as seed data for Semantic Scholar enrichment.
- Semantic Scholar matching should require a strong title match and at least
  one compatible author signal when possible.
- If Semantic Scholar cannot confidently match a publication, keep the Scholar
  title/year as a weak signal but avoid inventing abstracts or fields.
- Limit prompt context to the highest-signal publication evidence:
  - researcher profile interests
  - recent publications
  - highly cited publications
  - enriched abstracts and fields of study

## Test Plan

- Backend API:
  - Reject malformed URLs.
  - Reject non-Scholar URLs.
  - Normalize valid Scholar profile URLs with extra query params.
  - Return a verified preview from mocked Scholar HTML.
  - Create a `ResearchProfileImport` row and `google_scholar_import` job.
  - Mark import and job failed if queue enqueue fails.
- Backend worker:
  - Parse mocked Scholar profile HTML.
  - Parse mocked publication rows/pages.
  - Enrich mocked publications through a fake Semantic Scholar client.
  - Continue when some publications fail enrichment.
  - Create draft filters with a source marker tying them to the Scholar import
    job.
  - Mark the job completed and expose progress.
- Jobs API:
  - Return job status, import subject, and newly created draft filters.
  - Support incremental polling without duplicating draft filters in the UI.
- Frontend:
  - Button opens the modal.
  - Invalid URL shows a rejection state.
  - Verified URL enables the start-import action.
  - Running import shows status without disabling text/PDF generation.
  - Draft filters returned from the import appear in Draft Filters.
  - Accept Drafts continues to promote Scholar-generated drafts normally.

## Assumptions

- V1 supports public Google Scholar profile URLs only.
- Direct Google Scholar parsing is bounded, best-effort, and not treated as an
  official API integration.
- The implementation will not attempt login, CAPTCHA solving, proxy rotation,
  or high-volume crawling.
- Semantic Scholar is the preferred enrichment source because it provides an
  official Academic Graph API for paper and author metadata.
- A Google Scholar export upload fallback is out of scope for this v1 plan.
- The current single-user prototype does not need multi-user account linking or
  OAuth-style profile ownership verification.
