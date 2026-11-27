---
name: fleet-pti-dashboard
description: Maintain the Fleet PTI Streamlit dashboard, including n8n JSON integration, daily driver heatmaps, training follow-up, safety officer assignments, and co-driver reporting.
---

# Fleet PTI dashboard

## Current user-approved rules

- Overview uses colored metric cards (blue context, green recorded, amber review,
  purple days off/crew) with visible descriptions. Driver tracking lists include
  source findings, linked partner findings, review category and suggested next
  steps; do not promote informational notes into source-review flags or assign
  an unrelated author's findings. Keep contextual follow-up distinct from proven
  missing required inspections. CSV retains the displayed review information.

- Overview distinguishes days off plus DVIR anywhere in the period from an own
  DVIR whose date actually matches a supplied day off. Training review counts
  Not done with own dated DVIRs separately from co-driver-only coverage; do not
  change training status based on submission evidence. Top five includes own
  dated submissions across the whole uploaded file up to report end, even with
  zero period submissions. Sort by latest date, then file count, then driver ID;
  show both file and 15-day counts and provide the full drill-down.

- Overview starts with a stakeholder 15-day snapshot ending on Report ending,
  independent of the retained 7/15-day detailed analysis below. Count only primary
  TruckMate roster drivers as people. Either linked driver submitting gives
  coverage; count author inspection entries once in totals. Show days off,
  training Done/Not done, recent dated training, consistency and daily trends.
  For overview days-off grouping, zero AND Not supplied mean No days off reported;
  preserve original information in drill-downs. Keep factual no-submission counts
  separate from training eligibility for follow-up. Preserve detailed pages,
  graphs, driver profiles and heatmaps.

- Simple report: No PTI in entire file and Solo without DVIR have Days off
  filters. A positive selected-period count means Has days off; zero or missing
  means No days off reported, retaining the original Not supplied value. Default
  the entire-file follow-up to No days off reported. Solo without DVIR also filters
  No record in entire file versus Has records in file (including older or undated
  evidence). CSV follows filters; five-sheet Excel retains all rows and categories.

- Latest report scope: Solo with DVIR, Solo without DVIR, and No PTI in entire
  file include only training Done drivers. Apply this to UI, CSV/Excel and the
  detailed Backend solo lists. Keep all Not done/empty/unknown training records
  in PTI training not done and the underlying roster; do not delete those drivers.
  Co-driver group coverage stays unchanged. Invalidate sidebar export caches
  when report membership rules change.


- Days off wording applies to ALL active visible UI, not only the simple report:
  shared table headers/status display, filters, profile calendar, heatmap legend
  and hover text, and overview captions. Preserve raw holiday fields/values and
  map presentation labels so existing upload state/filter calculations still work.


- Latest navigation request keeps all pages: main links are Simple 15-day report,
  PTI training not done, and Overview. Group the other six detailed pages together
  under one Backend expander; do not remove or hide their functionality. Keep
  driver-profile navigation working. Simple report/export labels are Days off,
  Days off by driver and Day off; retain the underlying holiday-date logic.


- Show uploaded safety status in simple reports, training list, driver/profile
  and co-driver tables plus downloads. File-level values use Unsafe > Resolved >
  other non-safe > Safe; missing is Not supplied. Keep primary/CODRIVER ownership
  separate and never invent per-date/equipment safety attribution from grouped
  unique status lists. Missing safety is not Safe and does not change DVIR counts.


- Latest stakeholder export is FIVE sheets: Solo with DVIR, Solo without DVIR,
  Co-driver with DVIR, Co-driver without DVIR (all last 15 days), plus No PTI in
  entire file (neither own nor linked partner evidence anywhere in upload).
  Preserve holiday/training exceptions in these factual lists. Undated positive
  counts are evidence, not never-done. Offer one five-sheet Excel download and
  per-table CSV downloads. This supersedes the former four-sheet export below.


- Simple 15-day report is the stakeholder table/Excel view. Active scope means
  everyone in the TruckMate roster, not Samsara Active. Keep four focused outputs:
  PTI not done, Solo with DVIR, Solo without DVIR, Co-driver groups. Show names,
  stable IDs, vehicles, dated counts, last DVIR, holiday counts and training dates.
  Use a fixed 15-day window ending on the selected source-based report date.
  Either crew member submitting prevents a No DVIR issue; keep known training,
  holiday and missing-date exceptions separate. Excel is generated in memory
  from the current upload, using the artifact-authored template. Do not restart
  a server the user explicitly stopped unless they ask to run it again.

- Latest PTITraining display/filter rule: only DONE (case/whitespace insensitive)
  means Done; blank/null/missing/Unknown/Not/all other values mean Not done.
  Conflicts are Not done plus review flags. Preserve internal source provenance:
  empty/unrecognized is not verified incomplete training and must not newly hide
  DVIR follow-up rows. Explicit Not/Not done/etc retains not-trained exclusion.
  Missing training dates remain unknown. Holiday/account labels are unchanged.
  This overrides older instructions to display Unknown training status.


- Preserve the current upload bytes/filename in session memory across profile
  redirects; transient uploader widget loss must not clear the active data.
  Explicit file removal, Clear, invalid replacement, and new sessions must stay
  empty as appropriate. Verify navigation using a real file uploader, not only a mock.


- Training dates affect no-DVIR follow-up: known untrained, training after period,
  or training on report end are not marked No DVIR. Keep them in full roster with
  date/status. During-period date-gap checks start the next calendar day. Unknown
  or conflicting training dates stay explicitly unknown/review, not silently
  exempted. Keep actual submissions and either-member coverage unchanged.


- Confirmed: every No DVIR list/filter (including co-driver member review) uses
  neither own nor linked partner submitting. Either submitting excludes both from
  No DVIR. Keep author counts unchanged. Team full-file filter is Either member
  has DVIR / Neither member has DVIR, not primary-own-missing.


- Holiday status covers the selected 7/15-day period, with all-period, partial,
  no reported dates and Unknown states. Preserve explicit daily holiday dates;
  never expand two dates into an assumed range. Missing data is not availability.
  Gap dates exclude the person's own holidays and own/linked co-driver DVIR dates.


- Latest coverage rule: in main roster follow-up and combined overview, either the
  driver OR an explicitly linked co-driver submitting is sufficient. Only neither
  submitting is a follow-up issue. Use has_covered_DVIR and coverage period dates,
  not missing own authorship. Keep own counts/authors and source categories intact.
  Team dates are a union, never a sum of both members' daily attendance. This rule
  supersedes earlier own-only roster follow-up interpretation below.


- Latest request restores training display from the uploaded JSON only: PTITraining
  and PTITrainingDate for primary IDs, explicit CODRIVER_ training fields for partners.
  Do not restore a training database or separate upload. Missing values are Unknown.
  Follow-up filters distinguish no dated own DVIR in period from no file evidence.
- Co-driver page has all-members own-DVIR review and separate team inspection tabs.
  Overview combines primary solo/co-driver individuals without giving team credit
  to a member's own DVIR count. These rules supersede the older ban on training UI.


- Source categories are mutually exclusive and assigned in the parser: Co-driver
  first, otherwise Solo with DVIR, otherwise Solo without DVIR. Own timestamp
  arrays or positive own inspection counts are evidence; lookup IDs alone are not.
  A co-driver without own activity remains Co-driver. Period/status filters and
  visualization must never reassign these source categories.

- The active app now uses local uploads and session memory only. Do not re-enable
  database/history/backups, saved-file fallback, training, API polling, or Reload.
  Sidebar uses Get DVIR to open the user's download form plus JSON upload/clear.
- Active files are local_ui.py, upload_model.py and local_views.py. Keep empty startup.
- Actual CODRIVER export: unprefixed activity belongs to Samsara_DriverID;
  CODRIVER_* belongs to CODRIVER_driverID. Shared driverID can be overwritten by
  the partner lookup. matched_on points to the partner slot, COGOELD to the primary.
- This export's reported vehicle/trailer counts are inspection-entry totals.
  Distinct equipment lists are not inspection totals. Preserve that distinction.
- Navigation separates Overview, with-DVIR, without-DVIR, co-driver teams,
  individual detail and data checks. Preserve heatmaps and role-separated activity.

These newer rules supersede legacy integration/storage guidance below.

- Both preTrip and postTrip, including grouped mixtures, count as done.
- Local JSON activity windows and daily defaults end on the latest actual inspection
  date. Track export/file-save time separately; do not default to an empty export day.
  Only fall back to export/file/upload date if no valid inspection dates exist.
- Keep every supplied driver visible; repeated IDs alone do not prove duplicate activity.
- Equipment PTIs count nonempty vehicleIDs plus trailerIDs entries from every source row,
  separately from timestamp-based 7/15-day attendance; ignore numeric count keys for equipment totals.
- For grouped safety statuses use unsafe, then resolved, then another non-safe value, then safe.
  Display actual statuses; resolved alone is done, not Unknown.
- Overview includes direct driver lists for Done, Regular, Below regular, and No records.
  Regular means 4/7 or 8/15 dates. Calendar gaps are not verified compliance misses.

These user-approved updates supersede conflicting older pre-trip-only/count-key guidance below.

Use the existing Streamlit application and its Pandas, Plotly, Pydantic, pytest, and optional SQLite architecture. Read [the project README](../../README.md) for configuration and JSON examples. Check the existing adapter, normalization, analytics, filters, and pages before modifying the reporting contract.

## Reporting and visuals

- Support only 7 and 15 days, including today and the preceding local calendar days. Default to America/Chicago. Store timestamps in UTC.
- Keep fleet overview, driver consistency, driver profiles, co-driver analysis, and defects and safety available. Design for approximately 800 drivers across 15 safety officers. Paginate driver heatmaps and large tables.
- Show a cell per driver and date. Green means recorded PTI, gray means no recorded PTI, yellow means review, and red means unsafe. For a day with multiple records, unsafe takes precedence over review, then recorded. Offer a daily list filtered by date and mark. Keep daily color marks on screen and use the CSV for the sortable driver summary.
- Classify frequency by distinct recorded dates. Frequent means at least half of the selected calendar days. Intermittent means at least one day below that threshold. Distinguish zero recorded activity from undated evidence that needs review. A full roster allows drivers without DVIRs to appear. Label an incomplete population as drivers observed in DVIR records.
- Treat absent records as a prompt to check the other PTI platform. True compliance requires reliable driving opportunities and company policy. Historical unsafe inspections require later inspection and repair evidence to assess current equipment condition.
- Count each original pre-trip DVIR ID once. Preserve other inspection types, original inspection detail, signatures, and defect resolution information. Empty defect arrays mean zero defects.

## Webhook and data matching

- Use one n8n webhook for both `GET ?days=7` and `GET ?days=15`. n8n combines all Samsara pages with verified Cogo ELD, training, and roster or assignment data. Accept the existing direct array, `data` wrapper, or enriched wrapper. Keep credentials in environment settings or Streamlit secrets.
- Match by stable IDs. The DVIR author comes from `authorSignature.signatoryUser.id`. Include zero-submission drivers in the roster and set `rosterComplete` only when the reporting roster is complete. Use current safety officer tags for assignment filters. Historical responsibility requires effective dates.
- Match Cogo team assignments using a verified driver ID crosswalk and the inspection time. Use inline co-driver fields or an explicit assignment keyed by DVIR and author ID. Unknown or ambiguous partners stay unknown. Additional signatures remain signatures. Shared equipment can be reported separately from a confirmed team. Credit the inspection once to the author.
- Show confirmed pairs with both drivers and their assigned officers. The co-driver page officer filter matches either participant.
- Link training data using a verified identifier or a verified crosswalk. Names alone can suggest matches for review. Mark ambiguous or missing training records unknown. Put `training_status` and `training_completed_at` on the driver record. Distinguish incomplete, explicitly not trained, and unknown. For date-only completion, compare from the next local day. Include too-early and undated-evidence cases when evaluating post-training activity.
- Compare current assigned driver IDs and vehicle IDs to pre-trip DVIR authors and vehicle IDs in the selected period. Use driver officer tags or `driverAssignments` and the top-level `vehicleAssignments` array. Show counts per officer and export the assigned IDs with zero matching DVIRs for cross-checking.

## Run and verify

From the dashboard directory, run `streamlit run app.py` and `python -m pytest -q` with the project's Python environment. Demo mode uses `sample_data/sample_dvir.json` with 12 fictional drivers per officer across three officers, illustrating frequent, intermittent, and zero recorded submissions. Verify both periods, officer filtering, and empty datasets when changing the board. Distinguish mocked webhook tests from live verification. If a running Streamlit server picks up a changed caller while retaining an older imported function, restart it and verify the relevant page.
