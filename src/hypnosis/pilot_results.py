"""Strict receipt collection after an uncertain child stdout delivery."""
from pathlib import Path
import json
import subprocess
import sys

from .training import _read


def collect_completed_job(directory,corpus,settings,*,parent_artifact=None,continue_artifact=None,timeout=15):
    """Recollect only a durably completed workflow, without retry authority.

    No optimizer stage may be repeated. The native checkpoint and persisted
    report must agree before invoking the identical CLI; func_seq independently
    validates the selected job and refuses uncertainty or changed definitions.
    """
    from thoughtform.artifacts import load_artifact
    from func_seq import CheckpointStore
    directory=Path(directory)
    report=_read(directory/'result.json')
    artifact=load_artifact(directory/'artifact.json')
    checkpoint=artifact.receipt['checkpoint']['sha256']
    if report.get('status') not in ('completed','limited') or report['training']['checkpoint_sha256']!=checkpoint:
        raise ValueError('No matching completed training receipt to recollect')
    # This is a read of func_seq's passive receipt, not a second workflow engine.
    # The CLI below remains authoritative for loading and validating progress.
    progress=CheckpointStore(directory/'workflow.json').read()
    if progress is None or progress['status']!='completed':
        raise ValueError('Only completed workflows can be recollected')
    command=[sys.executable,'-u','-m','hypnosis','train',str(corpus),str(directory),str(settings)]
    if parent_artifact is not None: command+=['--parent-artifact',str(parent_artifact)]
    if continue_artifact is not None: command+=['--continue-artifact',str(continue_artifact)]
    completed=subprocess.run(command,capture_output=True,text=True,timeout=timeout)
    if completed.returncode not in (0,1) or len(completed.stdout.encode())>1024*1024:
        raise ValueError('Completed job recollection failed')
    value=json.loads(completed.stdout)
    if value!=report: raise ValueError('Recollected result differs from the durable receipt')
    return value
