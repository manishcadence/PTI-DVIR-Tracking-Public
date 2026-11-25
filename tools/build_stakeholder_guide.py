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
header.text = 'FLEET DVIR   |   STAKEHOLDER QUICK GUIDE'
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

doc.add_heading('Track driver DVIR submissions',0)
p('A simple guide for supervisors and stakeholders','Subtitle')
p('Use two sections: Simple 15-day report to check who submitted inspection reports, and PTI training not done to find drivers whose training needs checking. DVIR means driver vehicle inspection report.')
h('Start here each time')
for text in [
    'Click Get DVIR and download the latest file. Then select Upload DVIR JSON and upload that file. If someone has already loaded it for you, check the Current file name.',
    'Open Simple 15-day report in the left menu.',
    'Check Report ending. The report covers that date and the previous 14 days. It starts with the latest inspection date in the file, which may be earlier than today.',
    'Choose a table below. Search for a name, ID or vehicle if needed. See page 2 for the dropdowns.',
    'Check days off and training dates before following up with a driver.'
]: p(text,'List Number')
h('Choose the list you need')
table(['Your question','Select this table'],[
    ('Which solo drivers submitted in these 15 days?','Solo with DVIR'),
    ('Which solo drivers have no submission in these 15 days?','Solo without DVIR'),
    ('Which co-driver groups have a submission?','Co-driver with DVIR'),
    ('Which co-driver groups have no submission?','Co-driver without DVIR'),
    ('Which drivers have no inspection evidence anywhere in the uploaded file?','No PTI in entire file')
],[3.9,3.2])
h('Three things to remember')
bullets([
    'For a co-driver group, either driver submitting counts as covered. Both drivers do not need to submit for the group to appear in Co-driver with DVIR.',
    'The solo lists and No PTI in entire file show only drivers with training Done. Find the other drivers in PTI training not done. Co-driver lists keep their group submission rules.',
    'No submission in 15 days is different from no record in the whole file. The file may include older inspections. No PTI in entire file does not mean the driver has never submitted.'
])
p('These are TruckMate roster reports. A missing record prompts a check; confirm whether the driver was working before treating it as a missed inspection.')

page('Use the filters to make a follow up list')
p('The dropdowns are above the tables. Filters work together with your search. To see a wider list, clear the search and select All in each dropdown.')
h('Days off follow up')
p('Available in Solo without DVIR and No PTI in entire file.')
table(['Choose','What you will see'],[
    ('All','Drivers with and without reported days off.'),
    ('No days off reported','Drivers with zero days off counted in the selected 15 days, or whose days-off information was not supplied.'),
    ('Has days off','Drivers with at least one reported day off in the selected 15 days.')
],[2.05,5.05])
p('No PTI in entire file starts with No days off reported selected. Choose All to include the other group. Not supplied means the information is missing; it does not confirm that the driver had no days off. One day off does not explain the whole 15-day period.')
h('DVIR history')
p('Available in Solo without DVIR. Everyone in this table already has no dated submission in the selected 15 days.')
table(['Choose','What you will see'],[
    ('All','All matching solo drivers without a submission in these 15 days.'),
    ('No record in entire file','Drivers with no inspection evidence anywhere in this upload.'),
    ('Has records in file','Drivers with inspection evidence in the upload, but none dated in these 15 days. Check Last DVIR and Status; some records may have missing dates.')
],[2.05,5.05])
h('Examples you can use')
bullets([
    'Find drivers to check first: open Solo without DVIR, choose No record in entire file, then No days off reported. Verify missing days-off information before contacting anyone.',
    'Find a recent gap: choose Has records in file. Check when the last submission was made.',
    'Review days off separately: choose Has days off, then check whether the time off covers some or all of the period.'
])
h('Download your list')
p('Download this table (CSV) saves the rows matching your current search and filters. It opens in Excel. Download Excel report (5 sheets), in the sidebar or report page, saves all five complete tables; your table filters do not narrow that workbook. Do not add the five table totals together because the no-record list overlaps the other lists.')

page('What each filter combination shows')
p('Open Simple 15-day report → Solo without DVIR. Every driver in this table has training Done and no dated own DVIR in the selected 15 days. The two dropdowns narrow that list further.')
table(['Days off follow up','DVIR history','You will see'],[
    ('No days off reported','No record in entire file','Drivers with no inspection evidence anywhere in the upload, and zero or missing days-off information for these 15 days.'),
    ('No days off reported','Has records in file','Drivers with inspection evidence elsewhere in the file, but no dated submission in these 15 days, and zero or missing days-off information.'),
    ('Has days off','No record in entire file','Drivers with at least one reported day off in these 15 days and no inspection evidence anywhere in the upload.'),
    ('Has days off','Has records in file','Drivers with at least one reported day off and some inspection evidence in the upload, but no dated submission in these 15 days.'),
],[1.65,1.65,3.8])
h('Example using a report ending November 23')
p('The 15-day period is November 9–23. Suppose a trained solo driver last submitted on November 5 and has two days off on November 12 and 13. Select Has days off + Has records in file to see that driver. Selecting No record in entire file would hide them because the November 5 submission exists in the upload.')
h('Check these before following up')
bullets([
    'Has records in file can also mean undated evidence. Check Last DVIR and Status to distinguish an older dated submission from a date problem.',
    'No days off reported includes missing information. Has days off means at least one date off, not necessarily the entire period.',
    'The No PTI in entire file table has only the Days off dropdown: its drivers already have no own or linked co-driver evidence anywhere in the upload.',
    'Your search also applies. Clear it if an expected driver is missing. Download this table (CSV) saves the matching result.'
])

page('Read the details and check training')
h('The most useful columns')
table(['Column','What it tells you'],[
    ('Driver name and IDs','Who the driver is. Use TMW ID or Driver ID to distinguish similar names.'),
    ('Vehicles','Vehicle names supplied for the driver or group. Not supplied means no name was available.'),
    ('DVIRs (15 days)','Dated submissions in the selected 15 days. A number above zero does not mean a submission on every day.'),
    ('DVIRs by driver','Each co-driver’s own count. One member can have zero while the group is covered.'),
    ('Last DVIR','The most recent dated record found up to Report ending. For a crew, this can be either member’s record.'),
    ('Days off','Reported dates off within the selected 15 days. Not supplied means missing information.'),
    ('Status and Training date','Context for the row. Day off or a training message needs checking before follow-up. Review inspection dates means the dates need checking.'),
    ('Safety status (file)','Uploaded Safe, Resolved, Unsafe or other safety information. Not supplied means no safety value was provided. This is separate from whether a report was submitted and does not confirm current vehicle condition.')
],[2.05,5.05])
h('Use PTI training not done')
p('Open PTI training not done in the left menu. This lists roster drivers whose uploaded training value is anything other than DONE. Blank, missing, Unknown and Not also appear as Not done. Check missing information before assuming the person has never received training.')
for text in [
    'Use Driver arrangement to choose All, Solo or Co-driver.',
    'Search by name, TMW ID, Driver ID or vehicle.',
    'Check the training date and available DVIR information. A driver can submit DVIRs while their training still shows Not done.',
    'Click Download CSV to save the matching training follow-up list.'
]:p(text,'List Bullet')
h('Before you contact a driver')
bullets([
    'Confirm the correct file and report dates. Check days off and whether a co-driver submitted.',
    'Check when training was completed. Recent training may explain the lack of earlier submissions.',
    'Check for older records or missing dates. Use the list to ask for clarification rather than assume the driver missed a required inspection.'
])
p('Get DVIR opens the download form; it does not update the report by itself. Upload the new file after downloading. Clear uploaded data empties the current report. Keep downloaded files if you need a record; the dashboard does not keep a history backup.')

target=ROOT/'docs'/'DVIR_Stakeholder_Guide_Revised.docx'
target.parent.mkdir(exist_ok=True)
doc.save(target)
print(target)

