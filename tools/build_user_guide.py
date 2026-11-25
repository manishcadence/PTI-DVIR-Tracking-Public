"""Build the stakeholder guide without any uploaded driver information."""
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[1]
doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.5), Inches(11)
sec.top_margin = sec.bottom_margin = Inches(.65)
sec.left_margin = sec.right_margin = Inches(.7)
normal = doc.styles['Normal']
normal.font.name = 'Calibri'
normal.font.size = Pt(11)
normal.paragraph_format.space_after = Pt(6)
normal.paragraph_format.line_spacing = 1.06
for name in ('Title', 'Subtitle', 'Heading 1', 'Heading 2'):
    doc.styles[name].font.color.rgb = RGBColor(0, 0, 0)
doc.styles['Title'].font.size = Pt(25)
doc.styles['Heading 1'].font.size = Pt(19)
doc.styles['Heading 2'].font.size = Pt(13)
for border in list(doc.styles.element.iter(qn('w:pBdr'))):
    border.getparent().remove(border)
header = sec.header.paragraphs[0]
header.text = 'FLEET DVIR   |   SUPERVISOR USER GUIDE'
header.runs[0].font.size = Pt(9)
footer = sec.footer.paragraphs[0]
footer.text = 'Updated November 25 2026   •   '
field = OxmlElement('w:fldSimple'); field.set(qn('w:instr'), 'PAGE'); footer._p.append(field)
footer.runs[0].font.size = Pt(9)

def p(text, style=None): return doc.add_paragraph(text, style)
def h(text): doc.add_heading(text, 2)
def page(title): doc.add_page_break(); doc.add_heading(title, 1)
def bullets(items):
    for text in items: p(text, 'List Bullet')
def table(headers, rows, widths):
    t=doc.add_table(rows=1, cols=len(headers)); t.autofit=False
    for i,(cell,text) in enumerate(zip(t.rows[0].cells,headers)):
        cell.text=text; cell.width=Inches(widths[i])
    repeat=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row in rows:
        cells=t.add_row().cells
        for i,(cell,text) in enumerate(zip(cells,row)):
            cell.text=text;cell.width=Inches(widths[i])
    for ri,row in enumerate(t.rows):
        cant=OxmlElement('w:cantSplit');row._tr.get_or_add_trPr().append(cant)
        for cell in row.cells:
            pr=cell._tc.get_or_add_tcPr()
            borders=OxmlElement('w:tcBorders')
            for edge in ('top','left','bottom','right'):
                e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');borders.append(e)
            pr.append(borders)
            shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'DCE6F1' if ri==0 else ('F5F7FA' if ri%2==0 else 'FFFFFF'));pr.append(shade)
            margins=OxmlElement('w:tcMar')
            for edge in ('top','left','bottom','right'):
                e=OxmlElement('w:'+edge);e.set(qn('w:w'),'85');e.set(qn('w:type'),'dxa');margins.append(e)
            pr.append(margins)
            for para in cell.paragraphs:
                para.paragraph_format.space_after=Pt(2)
                para.paragraph_format.line_spacing=1
                for run in para.runs:
                    run.font.size=Pt(10.5);run.bold=ri==0
    p('')
    return t

doc.add_heading('Fleet DVIR dashboard user guide',0)
p('How to review submissions and prepare driver follow up', 'Subtitle')
p('Use this dashboard to see which TruckMate roster drivers have DVIR records, identify recent recording gaps, and prepare training follow-up lists. A DVIR is a driver vehicle inspection report. PTI means pre-trip inspection; this dashboard also counts supplied post-trip records.')
p('Start with Simple 15-day report for routine review. Check days off, training dates and co-driver submissions before contacting a driver. A missing record is a reason to check, not proof that a required inspection was missed.')
h('Start a report')
for text in ['Click Get DVIR in the sidebar. Complete the download through the n8n form.',
             'Save the JSON file, then use Upload DVIR JSON in the dashboard. Opening Get DVIR alone does not update the dashboard.',
             'Check Current file and Report ending. The default end date comes from the latest usable inspection in the upload, rather than today or the file download time.',
             'Open Simple 15-day report, choose a table, then use the search and dropdown filters.',
             'Download the displayed table as CSV or download the full five-sheet Excel report.']:
    p(text,'List Number')
h('Main sidebar controls')
table(['Control','What it does'],[
 ('Get DVIR','Opens the production download form. Download first, then upload the new JSON.'),
 ('Upload DVIR JSON','Loads the selected file. A replacement file replaces the current report data.'),
 ('Clear uploaded data','Removes the active upload from this session and returns to the empty screen.'),
 ('Report ending','Sets the final date included. The simple report includes this date and the previous 14 dates.'),
 ('Download Excel report (5 sheets)','Downloads all five full tables for the chosen ending date. Table search and dropdown selections do not narrow this workbook.')],[2.1,5])
h('Use Overview to see the pattern')
p('Overview shows source categories, coverage consistency, daily participation and own DVIR counts. Regular means at least 4 of 7 or 8 of 15 dates with records. Crew coverage can count either member; individual counts and the daily participation graph keep authors separate.')

page('Choose the right report')
p('The main navigation contains Simple 15-day report, PTI training not done and Overview. Detailed screens remain under Backend. Use the simple report when sharing a concise list with a supervisor.')
table(['Table','Who appears'],[
 ('Solo with DVIR','TruckMate roster drivers with training Done, no linked co-driver information, and at least one dated own DVIR in the selected 15 days.'),
 ('Solo without DVIR','Solo roster drivers with training Done and zero dated own DVIRs in the selected 15 days. Some may have older or undated records in the file.'),
 ('Co-driver with DVIR','Supplied crew groups where at least one member has a dated DVIR in the selected 15 days.'),
 ('Co-driver without DVIR','Supplied crew groups where no member has a dated DVIR in the selected 15 days. Check Status for exceptions.'),
 ('No PTI in entire file','Roster drivers with training Done and no own or explicitly linked co-driver inspection evidence anywhere in the uploaded file. Includes solo and crew-associated drivers.')],[2.05,5.05])
h('Rules that explain the lists')
bullets([
 'Roster scope means TruckMate drivers, identified by their roster information. It does not mean only Samsara accounts marked Active.',
 'Solo means no linked crew information was supplied. Crew links use supplied identities and assignments; sharing a name alone does not establish a team.',
 'Either co-driver submitting provides team coverage. The other driver keeps an own DVIR count of zero, but the team is not put in the co-driver without-DVIR table.',
 'The solo tables and No PTI in entire file require training Done. Other training values remain in PTI training not done. Co-driver tables do not apply this same trained-only membership restriction.',
 'No PTI in entire file checks the full upload, which may contain 20–30 days or more. It does not mean the driver has never submitted in their lifetime.',
 'Positive undated inspection evidence excludes a driver from No PTI in entire file, even though it cannot prove a submission within the selected 15 days.'
])
p('The fifth table overlaps the period tables. Do not add all five row counts together. Supplied crew groups can also overlap, so their totals are not necessarily unique driver totals.')
p('The Backend solo lists use whole-file source categories. A solo driver with an older DVIR remains in Backend Solo with DVIR, even when they appear in Simple 15-day report → Solo without DVIR. Use the simple report for the complete list of recent gaps.')

page('Filter the without DVIR lists')
p('Use the dropdowns above the table. Search and dropdown selections work together: a displayed row must match every selected condition. Choose All and clear the search to widen the list.')
h('Days off follow up')
table(['Dropdown choice','Meaning'],[
 ('All','Shows both days-off groups in the current table.'),
 ('No days off reported','The selected 15-day days-off count is zero or the information was not supplied.'),
 ('Has days off','At least one reported date off falls within the selected 15 days.')],[2.05,5.05])
p('This dropdown appears in Solo without DVIR and No PTI in entire file. The entire-file table initially selects No days off reported; Solo without DVIR initially selects All. Select All to see drivers initially hidden by that default.')
p('Not supplied remains visible in the Days off column. Grouping it with zero helps build a follow-up list; it does not confirm that the driver worked every day. One day off also does not excuse the whole 15-day period.')
h('DVIR history')
table(['Dropdown choice','Meaning in Solo without DVIR'],[
 ('All','Shows every trained solo driver with no dated submission in the selected period.'),
 ('No record in entire file','No inspection evidence exists anywhere in this upload.'),
 ('Has records in file','Evidence exists elsewhere in the upload, but there is no dated DVIR in the selected 15 days. It may be older or have missing dates.')],[2.05,5.05])
h('Examples of useful selections')
bullets([
 'Find trained solo drivers with no uploaded history and no reported days off: select No record in entire file and No days off reported.',
 'Find trained solo drivers who previously submitted but have a recent gap: select Has records in file. Check Last DVIR and Status before following up.',
 'Review drivers with days off separately: select Has days off. Verify whether they were off for some or all of the selected period.'
])
p('Download this table (CSV) exports the displayed filtered rows. The Excel report keeps all five complete tables and includes the category columns so a recipient can filter them in Excel.')

page('Understand the table data')
table(['Column','How to read it'],[
 ('TMW ID and Driver ID','TruckMate roster ID and the linked driver identifier. Use IDs to distinguish people with similar names.'),
 ('Driver name and Co-driver names','The supplied driver and linked crew members. Co-driver tables put all supplied group names in Driver names.'),
 ('Vehicles','Vehicle names supplied with the driver or group. Not supplied means no name was available; these names do not prove a current assignment.'),
 ('DVIRs (15 days)','Number of dated inspection entries in the selected period. Solo rows show own submissions; crew rows show submissions by the group.'),
 ('DVIRs by driver','Each crew member’s own submission count. A partner’s record is not added to the other person’s own count.'),
 ('Last DVIR','Latest usable dated own or linked crew record on or before Report ending. No dated DVIR means no usable dated entry was found for that scope.'),
 ('Days off and Days off by driver','Reported dates off within the selected 15 days. Zero means none counted there; Not supplied means the source did not provide this information. Days off displays as text.'),
 ('Days off category and DVIR history','The groups used by the dropdowns. File history and selected-period days off measure different things.'),
 ('PTI training and Training date','Uploaded training completion status and supplied completion date. Crew tables show these for each member.'),
 ('Other crew','Additional supplied crew names that could not be mapped to a verified driver identity. Check these before assuming coverage.'),
 ('Safety status (file) and Safety by driver (file)','Safety values supplied anywhere in the upload, summarized per driver. This is separate from whether a DVIR was submitted.')],[2.05,5.05])
h('Status explains a row')
bullets([
 'Submitted: a dated own or linked crew record exists in the period.',
 'No DVIR: no dated record was found for that row’s scope in the period.',
 'Day off: all applicable dates after training were reported as days off.',
 'Training followed by a description: the training timing or status needs consideration before no-DVIR follow-up.',
 'Review inspection dates: inspection evidence exists, but dates are missing or unusable. Resolve the date issue before treating it as a period submission or a confirmed gap.'
])

page('Training safety and follow up')
h('PTI training not done')
p('Open this section to plan training follow-up. Only the uploaded value DONE, allowing different letter case and surrounding spaces, displays as Done. Empty, missing, Unknown, Not and all other values display as Not done. A driver may have submitted DVIRs while training still shows Not done.')
bullets([
 'Driver arrangement selects All, Solo or Co-driver.',
 'Find a driver or vehicle searches the name, TMW ID, Driver ID or vehicle.',
 'Download CSV exports all matching rows, not just the current table page.',
 'Click Driver, Driver ID or Open profile in supported detailed tables to open the individual report. The simple report tables do not provide these profile links.'
])
p('Missing training information should be verified before assuming someone never received training. A completion date alone does not replace a missing Done status.')
h('Training dates and missing records')
p('Detailed follow-up checks start on the day after a known training completion date. A driver trained after the report period or on its final date is not treated as a normal no-DVIR follow-up case. The simple tables still retain factual zero-submission rows with training Done; read Status and Training date before contacting the driver.')
h('Safety values')
p('When several safety values are supplied, the displayed priority is Unsafe, then Resolved, then another non-safe value, then Safe. Missing safety information displays as Not supplied. Crew reports keep each driver’s safety information separate.')
p('These are summaries of the full uploaded file. Resolved does not establish that every defect was repaired, and an old Unsafe value does not establish the current vehicle condition. Grouped values cannot reliably be assigned to a particular date or asset. Check the original inspection when a safety decision is needed.')
h('What if these situations occur')
table(['Situation','What to do'],[
 ('One co-driver submits and the other does not','Treat the group as covered for that submission date. Use individual counts if you need to know who authored it.'),
 ('Training Done but no period DVIR','Check days off, training timing, Last DVIR and missing-date warnings. Then confirm whether the driver was operating.'),
 ('No PTI in entire file with Not supplied days off','Verify days off before following up. This row has no supplied evidence of either inspections or days off.'),
 ('Training Not done but DVIRs exist','Keep the driver in training follow-up. Existing inspection records do not change the uploaded training status.')],[2.35,4.75])

page('Detailed screens and common questions')
h('When to use Backend')
p('Expand Backend for investigations. It contains the detailed solo lists, Main TruckMate roster, Co-driver teams, Individual driver and Data checks & unmatched. These screens keep the graphs, heatmaps and inspection details available without crowding routine stakeholder reports.')
table(['Control or view','Purpose'],[
 ('Reporting period','Selects 7 or 15 days on detailed screens. The simple report and Excel workbook always use 15.'),
 ('Search drivers and Samsara status','Narrows detailed lists by supplied name, driver ID or vehicle, and by account status. Samsara status does not define TruckMate roster membership.'),
 ('Days off status (period)','Selects full-period days off, some days off, no dates reported, or Unknown. Unknown remains distinct on detailed screens.'),
 ('PTI activity and Arrangement','Selects date activity or consistency, and solo or crew arrangement where offered.'),
 ('Training relative to report and Training / DVIR follow-up','Separates training before, during or after the period and trained drivers with no file or period records. Date-based follow-up also checks training eligibility.'),
 ('Sort all matching rows by and Descending','Orders the full matching list before paging. Rows per page and Page change the visible portion; Download CSV keeps all matching rows.'),
 ('Inspect a team and Driver','Selects the team or individual whose detailed report is shown. Team file coverage distinguishes either member having evidence from neither having it.'),
 ('Heatmap rows and Calendar status','Changes the visible heatmap rows or individual calendar marks. Hover over cells to read dates, status and available vehicle information.')],[2.55,4.55])
p('Heatmap marks: green = recorded; yellow = recorded with data review; purple = day off without DVIR; blue = before training or not trained; gray = no own DVIR. An asterisk marks a record on a day off. Read the legend on the screen.')
h('If something looks wrong')
bullets([
 'Old date or missing driver: check Current file, Report ending, search and every dropdown. Download and upload the latest JSON; Get DVIR does not refresh automatically.',
 'Different totals: distinguish people, crew groups, inspection entries and dates. Multiple entries on one day count as one participation date. No-file rows overlap period rows.',
 'Empty screen: upload a file. No matching drivers: widen the filters. Data checks & unmatched helps investigate identity and source issues.'
])
p('Data is held in the current session only. There is no database or historical backup in this version. Keep the original JSON and downloaded reports if you need a record. Replacing or clearing the upload replaces the active data; a new session starts empty.')

target=ROOT/'docs'/'Fleet_DVIR_User_Guide.docx'
target.parent.mkdir(exist_ok=True)
doc.save(target)
print(target)
