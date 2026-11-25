# Active dashboard logic

The Simple 15-day report is an additional focused, table-only view with an Excel
download. Its driver scope is TruckMate membership, as confirmed by the user.
Its period is always 15 dates ending on the report-ending date; 7-day settings on
other pages do not change this report. Its follow-up list respects either-member
coverage, training exclusions, reported holidays on applicable dates, and undated
inspection review. Solo with/without tables partition all solo roster drivers by
dated activity in this period. Exact source crew rows retain all linked IDs and
unmapped members; team rows must not be summed when groups overlap. No data is
loaded into the running app from a sample or from generated Excel workbooks.

The active app is strictly local-upload and session-memory based. It uses
src/local_ui.py, src/upload_model.py and src/local_views.py. No history database,
training store, snapshot loader, API fetch or configured local report is read.
An empty or cleared uploader yields no tables, metrics or plots.

Primary roster identity is Samsara_DriverID (Tms_ID fallback). In explicit
CODRIVER exports, unprefixed counts/timestamps belong to this primary identity;
CODRIVER_* belongs to CODRIVER_driverID. Generic driverID may be overwritten by
a partner lookup and is retained only as a source ambiguity, never substituted
for primary identity. Native owner/partner records are separate. Legacy grouped
exports without explicit partner blocks retain their stated author IDs.

UTC start/end pairs plus author/occurrence are fallback event identities; identical
repeated blocks are counted once. Full-file reported counts are separate from
period dated counts. Distinct inventory names/IDs are not per-event mappings.
The latest actual timestamp determines the default report date; workflow timestamps
never create activity. Without any usable dates the calendar has a reference date
and the UI explicitly states that no inspection dates were supplied.

The primary roster is partitioned before period calculations: Co-driver first,
then Solo with DVIR, then Solo without DVIR. The three sets are disjoint. Co-driver
rows without an own submission stay in Co-driver teams. Date controls never move
a person between these categories; no-record-in-period filters stay inside the
source category. A person with only reported summary counts is
shown with data-review flags rather than being treated as verified non-submission.
Holiday dates without a record are purple; records on holiday dates remain recorded.
Regularity is 4/7 or 8/15 distinct dates. Team regularity uses the union of member
dates, while individual counts/records stay separate.

Source crew IDs, names, vehicleName and matched_on define exact crews. The matched
slot identifies the partner for the actual export; COGOELD identifies the primary.
Missing third-member identities remain unmapped. Current source relationships do
not prove historical team timing. Account activation is independent of attendance
and holiday state, and lower-case lookup IDs control whose status can be applied.

All filters and exports operate on the currently uploaded data only. Upload
replacement and clearing discard the session model. CSVs are generated in memory.

Training status now comes from uploaded PTITraining fields only, joined to explicit
primary/partner IDs. No partner completion is inferred from primary training.
Both period-without-dated-DVIR and file-without-any-evidence follow-up flags are
separate from categories and regularity; missing training remains Unknown.

Latest coverage rule for main roster and combined overview: own OR explicitly
linked crew member DVIR counts as covered. No own record alone does not indicate
a follow-up issue. Only neither submitting does. Period dates are a union of
linked authors' dates; actual author attribution and own totals do not change.
Training follow-up in these coverage views uses the same own-or-co-driver rule;
explicit own-author views keep own-only filters. This supersedes earlier own-only
roster follow-up wording.

Holiday status is now period-wide: all dates, some dates, no reported dates, or
Unknown for absent holiday evidence. Display distinct dates and counts. Per-person
reported holidays and own/co-driver-covered dates are excluded from period gaps;
no holiday is inherited from a partner. Regularity thresholds remain 4/7 and 8/15.

Training reporting eligibility now excludes known incomplete training and training
on/after report end from No DVIR lists, while keeping them in the full roster with
training status/date. Within-period gap evaluation starts the next calendar day.
Unknown training/dates are visibly unknown and not silently excluded. Actual
records and either-co-driver coverage remain intact; holiday gaps use only dates
after known training. This supersedes earlier training-independent follow-up.

Latest label rule: PTI training is Done only for DONE ignoring case/whitespace;
all other/missing values are Not done. Keep source provenance internally:
missing/unrecognized values do not prove explicitly incomplete training and are
not newly excluded from DVIR follow-up merely because their display label changed.
Training dates, actual inspection authorship, co-driver coverage, holidays and
Samsara account states retain their separate meanings. Conflicting values are
Not done with a data-review flag. This supersedes older Unknown training labels.

The stakeholder export now has five sheets: solo with/without dated DVIR in 15
days, co-driver groups with/without dated DVIR in 15 days, and all roster drivers
with no own/linked partner inspection evidence anywhere in the upload. The fifth
is a whole-file subset and deliberately overlaps the period tables; it does not
exclude holiday/training cases or claim lifetime history. Positive undated counts
are evidence and exclude the driver from the fifth sheet. Per-table CSV uses
search-filtered rows; the Excel button exports all five full tables. This replaces
the former four-sheet stakeholder report and period-only PTI-not-done sheet.

Safety status is now retained per explicit DVIR author as a full-upload summary,
using Unsafe, Resolved, other non-safe, Safe priority. Source status values are
also preserved for profile review. Grouped arrays are not considered aligned to
timestamps. Missing values remain Not supplied; CODRIVER_ safety is not borrowed
from primary fields. File-level safety does not change submission classification.

Detailed pages remain registered and are grouped under Backend in the sidebar.
Only presentation changes: Days off labels in the simple report use the existing
reported holiday dates/counts. No source fields or categorization are changed.

Solo reports and No PTI in entire file are now filtered to pti_training_status
Done. The no-file report also requires no own/linked-partner evidence anywhere
in the upload. Not done drivers remain available in the training section and
full roster. Co-driver coverage and source categories are not modified. This
supersedes earlier all-training-status membership for those report tables.

Days off categories use holiday_dates_in_period > 0, independent of full-file
DVIR history. Zero and missing counts group as No days off reported while the
original Not supplied remains visible. Solo without DVIR and No PTI in entire
file support this filter; the latter defaults to No days off reported. Solo without
DVIR additionally filters has_covered_DVIR as Has records in file versus No record
in entire file, retaining positive undated evidence as history. UI filters combine
with search and affect CSV. Excel retains all rows with category/history columns.
