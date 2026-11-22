"""Explicit local source admission and bounded snapshot fingerprints."""
from dataclasses import dataclass,asdict
import hashlib
from pathlib import Path

APPROVAL='https://github.com/wispsy/hypnosis/issues/13'
# Explicit selected sources, not automatic source discovery. Approvals are per source.
CATALOG={
 'tinystories-train':('stories','TinyStories-train.txt','train','CDLA-Sharing-1.0'),
 'tinystories-valid':('stories','TinyStories-valid.txt','validation','CDLA-Sharing-1.0'),
 'simplewiki':('wikipedia','simplewiki-latest-pages-articles-multistream.xml.bz2',None,'Wikimedia source terms'),
 'enwiki':('wikipedia','enwiki-latest-pages-articles-multistream.xml.bz2',None,'Wikimedia source terms'),
 'wiktionary':('wiktextract','raw-wiktextract-data.jsonl.gz',None,'Wiktionary source terms'),
 'ud-train':('conllu','en_ewt-ud-train.conllu','train','UD EWT source and annotation terms'),
 'ud-dev':('conllu','en_ewt-ud-dev.conllu','validation','UD EWT source and annotation terms'),
 'ud-test':('conllu','en_ewt-ud-test.conllu','test','UD EWT source and annotation terms'),
 'internal-v1':('generated',None,None,'Internally authored curriculum v1'),
 'python-vault-tutorials':('markdown','python3_vault',None,'Owner-provided notes; retain cited source terms'),
 'python-vault-reference':('markdown','python3_vault',None,'Owner-provided reference notes; retain cited source terms'),
 'psf-wiki-python':('markdown','psf_wiki',None,'Python community wiki source terms; preserve clone attribution'),
 'python314-docs':('python-docs','python-3.14-docs-text.tar.bz2',None,'Python 3.14 documentation terms in archive license.txt'),
}


def source_approval(source_id):
    if source_id in ('python-vault-tutorials','python-vault-reference','psf-wiki-python','python314-docs'):
        return 'https://github.com/wispsy/hypnosis/issues/27'
    return APPROVAL


class SourceApprovalError(ValueError):
    pass


@dataclass(frozen=True)
class Source:
    source_id: str
    path: str
    index: str | None = None
    fingerprint: str | None = None

    def __post_init__(self):
        if self.source_id not in CATALOG:
            raise SourceApprovalError('Source is not in the explicitly approved pilot catalog')
        kind,filename,_split,_terms=CATALOG[self.source_id]
        if type(self.path) is not str or not self.path or (filename is not None and Path(self.path).name!=filename):
            raise SourceApprovalError('Select the approved source filename and snapshot explicitly')
        if kind=='wikipedia' and (type(self.index) is not str or not self.index):
            raise ValueError('Wikipedia requires its selected multistream index')

    @property
    def kind(self): return CATALOG[self.source_id][0]

    @property
    def split(self): return CATALOG[self.source_id][2]

    @property
    def terms(self): return CATALOG[self.source_id][3]


def file_snapshot(path):
    """Stat plus bounded head/tail samples, explicitly not a full-file checksum."""
    path=Path(path)
    if not path.is_file() or path.is_symlink(): raise ValueError('Select an ordinary source file')
    before=path.stat()
    if before.st_size==0: raise ValueError('Source download is an empty placeholder')
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        digest.update(stream.read(65536))
        stream.seek(max(0,before.st_size-65536));digest.update(stream.read(65536))
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns): raise ValueError('Source changed during fingerprinting')
    data={'kind':'stat-plus-head-tail/1','bytes':before.st_size,'mtime_ns':before.st_mtime_ns,'sample_sha256':digest.hexdigest()}
    data['fingerprint']=hashlib.sha256(repr(sorted(data.items())).encode()).hexdigest()
    return data


def bind_source(source):
    if source.kind in ('markdown','python-docs'):
        from .materials import material_snapshot
        snapshot=material_snapshot(source)
        if source.fingerprint is not None and source.fingerprint!=snapshot['fingerprint']:
            raise SourceApprovalError('Material differs from the selected approved snapshot')
        return snapshot
    if source.kind=='generated':
        from ..curriculum import RECIPE,RECIPE_SHA256
        return {'kind':'generator/1','recipe':RECIPE,'recipe_sha256':RECIPE_SHA256,'approval':APPROVAL}
    snapshot=file_snapshot(source.path)
    if source.fingerprint is not None and source.fingerprint!=snapshot['fingerprint']:
        raise SourceApprovalError('Source differs from the selected snapshot')
    if source.kind=='wikipedia': snapshot['index']=file_snapshot(source.index)
    snapshot.update(source_id=source.source_id,terms=source.terms,approval=APPROVAL)
    return snapshot
