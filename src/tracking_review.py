"""Explain source findings and suggested checks without changing driver records."""
from collections import defaultdict


def _source_action(check):
    text=check.lower()
    if 'training' in text:return 'Verify training completion and correct conflicting training values in the source.'
    if 'holiday' in text:return 'Compare the reported days-off count with the supplied dates and correct the source.'
    if any(word in text for word in ('identity','name differs','id missing','driver ids','partner slot')):
        return 'Verify TruckMate, Samsara and co-driver ID matching before assigning records to a driver.'
    if any(word in text for word in ('timestamp','start/end','without inspection dates')):
        return 'Check the original inspection start/end dates and export the corrected date information.'
    if any(word in text for word in ('counts','count differs','totalpti','overlapping')):
        return 'Compare source totals with inspection entries; confirm the export without adding overlapping histories.'
    return 'Review the original source row and confirm the information before follow-up.'


def attach_tracking_review(report,roster):
    """One explanation per roster driver, including explicitly linked partner issues."""
    result=roster.copy()
    peers=defaultdict(set)
    for team in report.teams.to_dict('records'):
        for member in team['members']:peers[member].update(team['members']-{member})
    names=report.people.set_index('driver_id').driver_name.to_dict()
    by_driver={key:frame for key,frame in report.issues.groupby('driver_id')}
    summaries=[];details=[];steps=[];groups=[];counts=[]
    for row in result.itertuples():
        reviews=[];information=[];actions=[];messages=[]
        source_review_count=0
        for member in sorted({row.driver_id}|peers[row.driver_id]):
            findings=by_driver.get(member)
            if findings is None:continue
            findings=findings.drop_duplicates(subset=['severity','check','detail'])
            for finding in findings.itertuples():
                owner='Driver' if member==row.driver_id else f'Co-driver {names.get(member,member)}'
                if finding.severity=='Review':
                    source_review_count+=1
                    reviews.append(f'{owner}: {finding.check}')
                    actions.append(_source_action(finding.check))
                else:information.append(f'{owner}: {finding.check}')
                messages.append(f'{owner} · {finding.severity} · {finding.detail}')
        category='Source data review' if reviews else None
        if row.training_date_conflict:
            reviews.append('Training dates disagree')
            actions.append('Verify the correct completion date before assessing post-training submissions.')
            category=category or 'Training record review'
        if row.pti_training_status!='Done':
            reviews.append('PTI training is Not done or not recorded')
            actions.append('Verify the training record; an inspection submission does not establish training completion.')
            category=category or 'Training record review'
        if not row.Submitted:
            reviews.append('No own or linked co-driver submission in these 15 days')
            if not row.training_followup_eligible:
                actions.append('Check training timing or incomplete training before evaluating missing DVIRs.')
            elif row.holiday_dates_in_period>0:
                actions.append('Check the dates off and days actually worked, then verify inspection records on working dates.')
            else:
                actions.append('Confirm whether the driver operated, verify missing days-off information and check other inspection records.')
            category=category or 'Submission follow-up'
        # Spaces in the column name are not valid namedtuple fields.
        own_on_day_off=bool(result.loc[row.Index,'Own DVIR on day off'])
        if own_on_day_off:
            reviews.append('Own DVIR date matches a reported day off')
            actions.append('Confirm whether the driver returned to work or whether the reported date off needs updating.')
            category=category or 'Days-off date review'
        if not reviews and information:
            actions.append('Informational source notes are available; no source review flag was supplied.')
        summaries.append('\n'.join(dict.fromkeys(reviews+information)) or 'No review flagged')
        details.append('\n'.join(dict.fromkeys(messages)) or 'No source finding supplied for this driver or linked co-drivers.')
        steps.append('\n'.join(dict.fromkeys(actions)) or 'Continue monitoring submission dates and update the upload when new data is available.')
        groups.append(category or ('Source information' if information else 'No review flagged'))
        counts.append(source_review_count)
    result['data_checks']=summaries
    result['check_details']=details
    result['suggested_next_step']=steps
    result['review_category']=groups
    result['source_review_items']=counts
    return result
