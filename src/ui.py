"""Compatibility helpers. The active app uses the upload-only local_ui shell."""
from dataclasses import dataclass
from pathlib import Path
import streamlit as st
from .filters import Filters,Scope,source_assets_match
from .normalization import FleetData
from .local_ui import prepare,page_context

@dataclass
class Context:
    data: FleetData
    scope: Scope
    timezone: str
    team_scope: Scope | None = None
    team_officer: str = ''
    filters: Filters = Filters()
    history_path: str = ''

    @property
    def filtered_source_rows(self):
        ids=set(self.scope.drivers.driver_id)
        return [{**row,'_source_row_number':number} for number,row in enumerate(self.data.source_rows,1)
                if (str(row.get('driverID')) in ids or row.get('_roster_driver_id') in ids) and source_assets_match(row,self.filters)]

def local_report_signature(path:Path):
    stat=path.stat()
    return stat.st_mtime_ns,stat.st_size

@st.fragment(run_every='15s')
def watch_local_report(path,loaded_signature):
    try: changed=local_report_signature(Path(path))!=loaded_signature
    except OSError:return
    if changed:st.rerun(scope='app')
