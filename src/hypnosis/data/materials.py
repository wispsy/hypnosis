"""Bounded snapshots and source-preserving chunks of approved Python material."""
from collections import deque
import fnmatch
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
import tarfile
from urllib.parse import urlsplit

APPROVAL='https://github.com/wispsy/hypnosis/issues/27'
SELECTIONS={
 'python-vault-tutorials':('tutorials/*.md','tutorials/**/*.md','python fundamentals.md',
                         'python functions.md','python decorators.md','python metaprogramming.md'),
 'python-vault-reference':('stdlib_module/*.md','stdlib_module/**/*.md','__builtins__/*.md','__builtins__/**/*.md'),
 'psf-wiki-python':('python/getting-started/*.md','python/getting-started/**/*.md',
                    'python/guides/*.md','python/guides/**/*.md'),
}
DOC_LIBRARY={'functions','stdtypes','exceptions','collections','itertools','functools',
             'contextlib','pathlib','json','math','random','unittest','typing','dataclasses',
             'io','os','sys','argparse','logging'}
MAX_FILE=1024*1024
MAX_TOTAL=64*1024*1024


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _entry(name,raw):
    return {'file':name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}


def _tree_files(source):
    root=Path(source.path)
    if not root.is_dir() or root.is_symlink(): raise ValueError('Select an ordinary approved source directory')
    values=[];total=0
    for path in root.rglob('*.md'):
        relative=path.relative_to(root).as_posix()
        if any(part in ('.git','.obsidian','_attachments') for part in path.relative_to(root).parts): continue
        if not any(fnmatch.fnmatchcase(relative,pattern) for pattern in SELECTIONS[source.source_id]): continue
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Source selection cannot follow links outside its root')
        size=path.stat().st_size;total+=size
        if size>MAX_FILE or total>MAX_TOTAL or len(values)>=10000: raise ValueError('Source snapshot exceeds its finite budget')
        with path.open('rb') as stream: raw=stream.read(MAX_FILE+1)
        if len(raw)!=size: raise ValueError('Source file changed while reading')
        raw.decode('utf-8')
        values.append(_entry(relative,raw))
    if not values: raise ValueError('Approved selection contains no text files')
    return sorted(values,key=lambda value:value['file'])


def _doc_selected(name):
    path=PurePosixPath(name)
    if path.name=='index.txt': return False
    return ((path.parts[0] in ('tutorial','reference') and path.suffix=='.txt') or
            (path.parts[0]=='library' and path.stem in DOC_LIBRARY and path.suffix=='.txt'))


def archive_pages(path):
    """Stream members without extracting paths, links or executable files."""
    total=count=0;seen=set()
    with tarfile.open(path,'r|bz2') as archive:
        for member in archive:
            count+=1;total+=member.size
            parts=PurePosixPath(member.name).parts
            if (not parts or parts[0]!='python-3.14-docs-text' or '..' in parts or
                PurePosixPath(member.name).is_absolute() or member.issym() or member.islnk()):
                raise ValueError('Archive member is outside the selected passive documentation profile')
            if count>4096 or total>MAX_TOTAL: raise ValueError('Documentation archive exceeds its expanded budget')
            name='/'.join(parts[1:])
            if not name or not member.isfile() or not _doc_selected(name): continue
            if name in seen: raise ValueError('Duplicate documentation member identity')
            seen.add(name)
            if member.size>MAX_FILE: raise ValueError('Selected documentation page is too large')
            with archive.extractfile(member) as stream: raw=stream.read(MAX_FILE+1)
            if len(raw)!=member.size: raise ValueError('Documentation member length differs')
            raw.decode('utf-8')
            yield name,raw


def material_snapshot(source):
    if source.kind=='python-docs':
        from .sources import file_snapshot
        ordinary=file_snapshot(source.path)
        sha=hashlib.sha256()
        with Path(source.path).open('rb') as stream:
            while block:=stream.read(65536): sha.update(block)
        files=sorted((_entry(name,raw) for name,raw in archive_pages(source.path)),key=lambda v:v['file'])
        if not files: raise ValueError('No selected Python documentation pages')
        value={'kind':'python-doc-archive/1','archive_sha256':sha.hexdigest(),
               'archive_bytes':ordinary['bytes'],'files':files,'version':'3.14'}
    else:
        value={'kind':'markdown-tree/1','files':_tree_files(source),'selection':list(SELECTIONS[source.source_id])}
    value.update(source_id=source.source_id,approval=APPROVAL,terms=source.terms,
                 file_count=len(value['files']),selected_bytes=sum(v['bytes'] for v in value['files']))
    value['fingerprint']=_digest(value)
    return value


def _reference_group(name,text,source_id):
    references=[]
    for line in text.splitlines():
        if line.startswith('Ref:'):
            references.extend(re.findall(r'https?://[^\s)>\]]+',line))
    if source_id=='python314-docs': return 'python-doc:'+name.removesuffix('.txt'),references
    for reference in references:
        url=urlsplit(reference)
        if url.hostname=='docs.python.org':
            parts=url.path.strip('/').split('/')
            if parts and re.fullmatch(r'3(?:\.14)?',parts[0]):
                return 'python-doc:'+'/'.join(parts[1:]).removesuffix('.html'),references
    return source_id+':'+name.removesuffix('.md'),references


def _chunks(name,text,source_id,maximum):
    if source_id=='python314-docs':
        # Exported text retains code indentation; no executable interpretation.
        blocks=[];start=0
        for match in re.finditer(r'\n\s*\n',text):
            blocks.append((start,match.start(),text[start:match.start()]));start=match.end()
        if start<len(text): blocks.append((start,len(text),text[start:]))
    else:
        from parse_md import CodeBlock,ThematicBreak,ParseOptions,EXTENDED,parse_blocks
        document=parse_blocks(text,dialect=EXTENDED,options=ParseOptions(max_characters=MAX_FILE,max_nodes=100000))
        blocks=[]
        for node in document.children:
            raw=node.to_markdown()
            if isinstance(node,ThematicBreak) or raw.lstrip().startswith(('Prev:','Rel:','Ref:','Tags:')): continue
            if isinstance(node,CodeBlock) and node.info.startswith(('{admonition}','{toctree}','{contents}')): continue
            if node.span is None: raise ValueError('Markdown source span is missing')
            blocks.append((node.span.start,node.span.end,raw))
    current=[];spans=[];size=0
    for start,end,raw in blocks:
        if not raw.strip(): continue
        for offset in range(0,len(raw),maximum):
            piece=raw[offset:offset+maximum]
            if current and size+len(piece)+2>maximum:
                yield '\n\n'.join(current),spans;current=[];spans=[];size=0
            current.append(piece);spans.append([start+offset,min(end,start+offset+len(piece))]);size+=len(piece)+2
    if current: yield '\n\n'.join(current),spans


def material_documents(source,snapshot,limits):
    from .corpus import group_split
    if source.fingerprint is None: raise ValueError('Select the approved material snapshot fingerprint before preparation')
    files={value['file']:value for value in snapshot['files']}
    if source.kind=='python-docs': pages=dict(archive_pages(source.path))
    else: pages=None
    queue=deque()
    def records(name):
        if pages is not None: raw=pages[name]
        else:
            with (Path(source.path)/name).open('rb') as stream: raw=stream.read(MAX_FILE+1)
        if _entry(name,raw)!=files[name]: raise ValueError('Selected material changed before parsing')
        text=raw.decode('utf-8');group,references=_reference_group(name,text,source.source_id)
        difficulty=1 if 'core_fundamentals' in name else (3 if 'advanced' in name else 2)
        for index,(chunk,spans) in enumerate(_chunks(name,text,source.source_id,limits.text_characters)):
            if not chunk.strip(): continue
            yield {'id':source.source_id+':'+hashlib.sha256(name.encode()).hexdigest()[:24]+':'+str(index),
                'source_id':source.source_id,'group':group,'split':group_split(group,limits.seed),'text':chunk,
                'content_sha256':hashlib.sha256(' '.join(chunk.split()).encode()).hexdigest(),
                'provenance':{'approval':APPROVAL,'terms':source.terms,'file':name,'file_sha256':files[name]['sha256'],
                    'snapshot_sha256':snapshot['fingerprint'],'references':references,'source_spans':spans,
                    'difficulty':difficulty,'material':'python','legacy_migrated':source.source_id=='psf-wiki-python',
                    'authorship':'owner-provided; retain cited derivation' if source.source_id.startswith('python-vault') else 'external approved source',
                    'text_truncated':False}}
    for name in sorted(files,key=lambda name:hashlib.sha256(name.encode()).digest()): queue.append(iter(records(name)))
    produced=0
    while queue and produced<limits.documents_per_source:
        iterator=queue.popleft()
        try: value=next(iterator)
        except StopIteration: continue
        yield value;produced+=1;queue.append(iterator)
