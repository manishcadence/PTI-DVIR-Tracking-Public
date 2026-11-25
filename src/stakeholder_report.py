"""Small, fixed-15-day stakeholder tables and a template-based Excel download."""
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import re
import textwrap
import xml.etree.ElementTree as ET

import pandas as pd
from .upload_model import people_summary


DRIVER_COLUMNS = ['TMW ID', 'Driver ID', 'Driver name', 'Co-driver names', 'Vehicles',
                  'Status', 'DVIRs (15 days)', 'Last DVIR', 'Days off',
                  'PTI training', 'Training date', 'Safety status (file)']
SOLO_COLUMNS = [column for column in DRIVER_COLUMNS if column != 'Co-driver names']
SOLO_WITHOUT_COLUMNS = SOLO_COLUMNS + ['Days off category','DVIR history']
NO_FILE_COLUMNS = DRIVER_COLUMNS + ['Days off category']
TEAM_COLUMNS = ['Vehicles', 'Driver names', 'TMW IDs', 'Driver IDs', 'DVIRs by driver',
                'DVIRs (15 days)', 'Last DVIR', 'Days off by driver',
                'PTI training', 'Training dates', 'Status', 'Other crew', 'Safety by driver (file)']
SHEETS = [('Solo with DVIR', SOLO_COLUMNS), ('Solo without DVIR', SOLO_WITHOUT_COLUMNS),
          ('Co-driver with DVIR', TEAM_COLUMNS), ('Co-driver without DVIR', TEAM_COLUMNS),
          ('No PTI in entire file', NO_FILE_COLUMNS)]
TEMPLATE = Path(__file__).resolve().parent / 'resources' / 'stakeholder_report_template.xlsx'
REPORT_VERSION = 'trained-days-off-and-file-history-v1'
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
ET.register_namespace('', NS)


@dataclass
class StakeholderReport:
    start: date
    end: date
    source: str
    tables: dict
    roster_count: int
    co_roster_count: int


def build_stakeholder_report(report, end, source='Uploaded JSON'):
    """Use TruckMate membership, actual dates and explicit crew links, never names."""
    window = [end - timedelta(days=i) for i in reversed(range(15))]
    summary = people_summary(report, window, end)
    roster = summary[summary.in_roster]
    people = summary.set_index('driver_id')
    events = report.events
    selected = events[events.inspection_date.isin(window)]
    history = events[events.inspection_time.notna() & events.inspection_date.le(end)]
    last = history.groupby('driver_id').inspection_date.max().to_dict()
    peers = defaultdict(set)
    group_vehicles = defaultdict(set)
    for crew in report.teams.to_dict('records'):
        for member in crew['members']:
            peers[member].update(crew['members'] - {member})
            group_vehicles[member].update(crew['vehicles'])
    uncertain = set(events.loc[events.inspection_time.isna(), 'driver_id'])
    for block in report.blocks.to_dict('records'):
        if not block['timestamp_pairs'] and any((block.get(field) or 0) > 0 for field in
            ('reported_vehicle_count', 'reported_trailer_count', 'reported_totalPTI')
            if pd.notna(block.get(field))):
            uncertain.add(block['driver_id'])

    def names(ids):
        return sorted(ids, key=lambda key: (people.loc[key, 'driver_name'], key))

    def last_date(ids):
        found = [last[key] for key in ids if key in last]
        return max(found) if found else 'No dated DVIR'

    def status(ids, evaluated):
        if selected.driver_id.isin(ids).any():
            return 'Submitted'
        assessed = people.loc[list(evaluated)]
        if not assessed.training_followup_eligible.any():
            return 'Training: ' + '; '.join(sorted(set(assessed.training_period_status)))
        if all(not (people.loc[key, 'post_training_dates'] - people.loc[key, 'holidays'])
               for key in evaluated if people.loc[key, 'training_followup_eligible']):
            return 'Day off'
        if ids & uncertain:
            return 'Review inspection dates'
        return 'No DVIR'

    driver_rows = []
    for row in roster.sort_values(['driver_name', 'driver_id']).itertuples():
        linked = {row.driver_id} | peers[row.driver_id]
        vehicle_names = {row.vehicle_names} - {'Not supplied', ''}
        vehicle_names.update(group_vehicles[row.driver_id])
        driver_rows.append({'TMW ID': str(row.tms_id or ''), 'Driver ID': row.driver_id,
            'Driver name': row.driver_name,
            'Co-driver names': '\n'.join(people.loc[key, 'driver_name'] for key in names(peers[row.driver_id])) or 'None',
            'Vehicles': ', '.join(sorted(vehicle_names)) or 'Not supplied',
            'Status': status(linked, {row.driver_id}), 'DVIRs (15 days)': int(row.dated_PTIs),
            'Last DVIR': last_date(linked),
            'Days off': int(row.holiday_dates_in_period) if row.holiday_data_available else 'Not supplied',
            'Dates off': row.holiday_dates_display if row.holiday_data_available else 'Not supplied',
            'PTI training': row.pti_training_status,
            'Training date': row.training_completed_date if row.training_completed_date is not None else row.pti_training_date,
            'Safety status (file)': row.safety_status_file,
            'Days off category': 'Has days off' if row.holiday_dates_in_period>0 else 'No days off reported',
            'DVIR history': 'Has records in file' if row.has_covered_DVIR else 'No record in entire file',
            '_solo': not row.has_crew, '_no_file': not row.has_covered_DVIR})
    all_drivers = pd.DataFrame(driver_rows, columns=DRIVER_COLUMNS + ['Days off category','DVIR history','_solo','_no_file'])
    team_rows = []
    roster_ids = set(roster.driver_id)
    for crew in report.teams.to_dict('records'):
        ids = crew['members']
        evaluated = ids & roster_ids
        if not evaluated:
            continue
        ordered = names(ids)
        counts = selected[selected.driver_id.isin(ids)].groupby('driver_id').size()
        holidays = lambda key: sorted(set(window) & people.loc[key, 'holidays'])
        team_rows.append({'Vehicles': ', '.join(sorted(crew['vehicles'])) or 'Not supplied',
            'Driver names': '\n'.join(people.loc[key, 'driver_name'] for key in ordered),
            'TMW IDs': '\n'.join(str(people.loc[key, 'tms_id']) if pd.notna(people.loc[key, 'tms_id']) else 'Not in roster' for key in ordered),
            'Driver IDs': '\n'.join(ordered),
            'DVIRs by driver': '\n'.join(f'{people.loc[key, "driver_name"]}: {int(counts.get(key, 0))}' for key in ordered),
            'DVIRs (15 days)': int(counts.sum()), 'Last DVIR': last_date(ids),
            'Days off by driver': '\n'.join(f'{people.loc[key, "driver_name"]}: '
                + (str(len(holidays(key))) if people.loc[key, 'holiday_data_available'] else 'Not supplied') for key in ordered),
            'Dates off': '\n'.join(f'{people.loc[key, "driver_name"]}: '
                + (', '.join(day.isoformat() for day in holidays(key)) or 'None reported')
                if people.loc[key, 'holiday_data_available'] else f'{people.loc[key, "driver_name"]}: Not supplied' for key in ordered),
            'PTI training': '\n'.join(f'{people.loc[key, "driver_name"]}: {people.loc[key, "pti_training_status"]}' for key in ordered),
            'Training dates': '\n'.join(f'{people.loc[key, "driver_name"]}: {people.loc[key, "pti_training_date"]}' for key in ordered),
            'Status': status(ids, evaluated), 'Other crew': '\n'.join(sorted(crew['unmapped'])) or 'None',
            'Safety by driver (file)': '\n'.join(f'{people.loc[key,"driver_name"]}: {people.loc[key,"safety_status_file"]}' for key in ordered)})
    teams = pd.DataFrame(team_rows, columns=TEAM_COLUMNS)
    trained = all_drivers['PTI training'].eq('Done')
    tables = {
        'Solo with DVIR': all_drivers.loc[trained & all_drivers._solo & all_drivers['DVIRs (15 days)'].gt(0), SOLO_COLUMNS].copy(),
        'Solo without DVIR': all_drivers.loc[trained & all_drivers._solo & all_drivers['DVIRs (15 days)'].eq(0), SOLO_WITHOUT_COLUMNS].copy(),
        'Co-driver with DVIR': teams.loc[teams['DVIRs (15 days)'].gt(0)].copy(),
        'Co-driver without DVIR': teams.loc[teams['DVIRs (15 days)'].eq(0)].copy(),
        'No PTI in entire file': all_drivers.loc[trained & all_drivers._no_file.eq(True), NO_FILE_COLUMNS].copy(),
    }
    return StakeholderReport(window[0], end, Path(source).name, tables,
                             len(roster), int(roster.has_crew.sum()))


def column_name(index):
    text = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        text = chr(65 + remainder) + text
    return text


def _cell(ref, value, style=None):
    """Fill the artifact-authored template, preserving numeric IDs as text."""
    attributes = {'r': ref}
    if style is not None:
        attributes['s'] = style
    cell = ET.Element(f'{{{NS}}}c', attributes)
    if pd.isna(value):
        value='Not supplied'
    if isinstance(value, (datetime, date)):
        value = (value.date() if isinstance(value, datetime) else value) - date(1899, 12, 30)
        ET.SubElement(cell, f'{{{NS}}}v').text = str(value.days)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        ET.SubElement(cell, f'{{{NS}}}v').text = str(value)
    else:
        cell.set('t', 'inlineStr')
        text = ET.SubElement(ET.SubElement(cell, f'{{{NS}}}is'), f'{{{NS}}}t')
        text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        text.text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value if value is not None else ''))
    return cell


def excel_bytes(report):
    """Populate the styled template in memory; no Node/runtime service required."""
    output = BytesIO()
    with ZipFile(TEMPLATE) as original, ZipFile(output, 'w', ZIP_DEFLATED) as target:
        for item in original.infolist():
            data = original.read(item.filename)
            match = re.fullmatch(r'xl/worksheets/sheet(\d+)\.xml', item.filename)
            if match:
                sheet_name, headers = SHEETS[int(match[1]) - 1]
                frame = report.tables[sheet_name]
                root = ET.fromstring(data)
                body = root.find(f'{{{NS}}}sheetData')
                template_rows = {int(row.get('r')): deepcopy(row) for row in body}
                style_rows = [{re.sub(r'\d+', '', c.get('r')): c.get('s') for c in template_rows[n]} for n in (7, 8)]
                for row in list(body):
                    if int(row.get('r')) >= 7:
                        body.remove(row)
                for row_num, value in [(2, sheet_name),
                    (3, ('Whole uploaded history. ' if sheet_name=='No PTI in entire file' else '')
                        +f'{report.start:%b %d, %Y} to {report.end:%b %d, %Y} (15-day counts)   |   {len(frame):,} rows'),
                    (4, f'Source: {report.source}. TruckMate roster. Either co-driver submitting counts as submitted.')]:
                    row = body.find(f'{{{NS}}}row[@r="{row_num}"]')
                    if row is None:
                        row = ET.SubElement(body, f'{{{NS}}}row', {'r': str(row_num)})
                    old = row.find(f'{{{NS}}}c[@r="A{row_num}"]')
                    style = old.get('s') if old is not None else None
                    if old is not None:
                        row.remove(old)
                    row.insert(0, _cell(f'A{row_num}', value, style))
                rows = list(frame.itertuples(index=False, name=None)) or [('No matching drivers',) + ('',) * (len(headers)-1)]
                for row_num, values in enumerate(rows, 7):
                    line_count = max(sum(max(1,len(textwrap.wrap(line,width=25 if
                        re.search(r'name|driver|Vehicles|training|Training|Status|Other crew',headers[i]) else 14)))
                        for line in str(value).split('\n')) for i,value in enumerate(values))
                    row = ET.SubElement(body, f'{{{NS}}}row', {'r': str(row_num), 'ht': str(max(30, 14*line_count+8)), 'customHeight': '1'})
                    styles = style_rows[(row_num-7) % 2]
                    for index, value in enumerate(values, 1):
                        col = column_name(index)
                        row.append(_cell(f'{col}{row_num}', value, styles.get(col)))
                end_row = max(7, len(rows)+6)
                dimension = root.find(f'{{{NS}}}dimension')
                if dimension is not None:
                    dimension.set('ref', f'A1:{column_name(len(headers))}{end_row}')
                auto_filter = root.find(f'{{{NS}}}autoFilter')
                if auto_filter is None:
                    auto_filter = ET.Element(f'{{{NS}}}autoFilter')
                    # OOXML order: after sheetData, before conditional formatting.
                    root.insert(list(root).index(body)+1, auto_filter)
                auto_filter.set('ref', f'A6:{column_name(len(headers))}{end_row}')
                for formatting in root.findall(f'{{{NS}}}conditionalFormatting'):
                    col = re.match(r'\$?([A-Z]+)',formatting.get('sqref')).group(1)
                    formatting.set('sqref', f'{col}7:{col}{end_row}')
                data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            target.writestr(item, data)
    return output.getvalue()
