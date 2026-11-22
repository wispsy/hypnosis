"""Approved corpus selection, grouped splits and finite materialization."""
from dataclasses import asdict,dataclass
import hashlib
import json
from itertools import islice
from pathlib import Path

from .sources import APPROVAL,CATALOG,Source,bind_source,source_approval
from .wiki import pages,clean_wikitext


@dataclass(frozen=True)
class DataLimits:
    documents_per_source: int = 32
    max_documents: int = 512
    max_output_bytes: int = 4*1024*1024
    text_characters: int = 4096
    seed: int = 1

    def __post_init__(self):
        for name,maximum in (('documents_per_source',10000),('max_documents',100000),('max_output_bytes',64*1024*1024),('text_characters',32768)):
            value=getattr(self,name)
            if type(value) is not int or not 1<=value<=maximum: raise ValueError('Invalid corpus budget')
        if type(self.seed) is not int or not 0<=self.seed<2**32: raise ValueError('Invalid split seed')


def group_split(group,seed):
    value=int(hashlib.sha256(f'{seed}:{group}'.encode()).hexdigest()[:8],16)%100
    return 'train' if value<80 else ('validation' if value<90 else 'test')


def _stories(path,limit):
    record=[];size=0;number=0;scanned=0
    with Path(path).open('rb') as stream:
        while True:
            raw=stream.readline(65537)
            if not raw: break
            scanned+=len(raw);size+=len(raw)
            if len(raw)>65536 or size>65536 or scanned>8*1024*1024: raise ValueError('Story scan exceeds its finite budget')
            line=raw.decode('utf-8')
            if line.strip()=='<|endoftext|>':
                text=''.join(record).strip();record=[];size=0
                if text:
                    yield str(number),text;number+=1
                    if number>=limit: return
            else: record.append(line)
        if record and ''.join(record).strip(): raise ValueError('Story source ends with an incomplete record')


def documents(source,limits):
    metadata={'approval':APPROVAL,'terms':source.terms}
    def make(identity,text,group,extra=None):
        truncated=len(text)>limits.text_characters
        text=text[:limits.text_characters]
        content=hashlib.sha256(' '.join(text.split()).encode()).hexdigest()
        return {'id':source.source_id+':'+identity,'source_id':source.source_id,'group':group,
                'split':source.split or group_split(group,limits.seed),'text':text,'content_sha256':content,
                'provenance':{**metadata,**(extra or {}),'text_truncated':truncated}}
    if source.kind=='stories':
        for identity,text in _stories(source.path,limits.documents_per_source):
            group='story:'+hashlib.sha256(' '.join(text.split()).encode()).hexdigest()
            yield make(identity,text,group)
    elif source.kind=='wikipedia':
        for value in pages(source.path,source.index,max_pages=limits.documents_per_source):
            text,references,excerpt=clean_wikitext(value['markup'],max_characters=limits.text_characters)
            if not text: continue
            extra={key:item for key,item in value.items() if key!='markup'}
            extra.update(references=references,excerpt=excerpt)
            yield make(str(value['page_id']),text,'wiki:'+value['title'].replace('_',' ').casefold(),extra)
    elif source.kind=='wiktextract':
        from engl import iter_wiktextract
        for number,value in enumerate(iter_wiktextract(source.path,source=source.source_id,max_records=limits.documents_per_source)):
            text=value.lemma+' ('+value.pos+'): '+' '.join(gloss for sense in value.senses for gloss in sense.glosses)
            yield make(value.record_id,text,'lexeme:'+value.lemma.casefold()+':'+value.pos,{'lexical_record':value.as_dict()})
    elif source.kind=='conllu':
        from engl import iter_conllu
        for value in iter_conllu(source.path,source=source.source_id,max_sentences=limits.documents_per_source):
            if value.text:
                yield make(value.sentence_id,value.text,'ud:'+(getattr(value,'document_id',None) or value.sentence_id),{'sentence_id':value.sentence_id})
    elif source.kind=='generated':
        from ..curriculum import generated_documents
        for value in islice(generated_documents(seed=limits.seed),limits.documents_per_source):
            if len(value['text'])>limits.text_characters:
                raise ValueError('An exercise exceeds the selected text budget')
            yield value
    elif source.kind in ('markdown','python-docs'):
        from .materials import material_documents
        yield from material_documents(source,bind_source(source),limits)


def prepare_corpus(sources,destination,*,limits=None):
    limits=limits or DataLimits();sources=tuple(sources)
    if not sources or len(sources)>16 or any(type(source) is not Source for source in sources): raise ValueError('Select 1–16 approved typed sources')
    if len({source.source_id for source in sources})!=len(sources): raise ValueError('Duplicate source selection')
    snapshots={source.source_id:bind_source(source) for source in sources}
    values=[];seen={};dropped=0;encoded_total=0;encoded_sizes={}
    rank={'train':0,'validation':1,'test':2}
    for source in sources:
        for value in documents(source,limits):
            identity=value['content_sha256']
            if identity in seen:
                prior=seen[identity]
                dropped+=1
                if rank[value['split']]<=rank[prior['split']]: continue
                values.remove(prior);encoded_total-=encoded_sizes[identity]
            encoded_size=len(json.dumps(value,ensure_ascii=True,allow_nan=False).encode())+1
            encoded_total+=encoded_size;encoded_sizes[identity]=encoded_size
            if encoded_total>limits.max_output_bytes: raise ValueError('Corpus exceeds retained byte ceiling')
            seen[identity]=value;values.append(value)
            if len(values)>limits.max_documents: raise ValueError('Corpus exceeds the document ceiling')
        if bind_source(source)!=snapshots[source.source_id]: raise ValueError('Source changed during corpus preparation')
    if not any(value['split']=='train' for value in values): raise ValueError('No approved training records selected')
    # All records with a shared group inherit the strictest held-out assignment.
    assignment={}
    for value in values:
        prior=assignment.get(value['group'],'train')
        if rank[value['split']]>rank[prior]: assignment[value['group']]=value['split']
        else: assignment.setdefault(value['group'],prior)
    for value in values: value['split']=assignment[value['group']]
    raw=b''.join(json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()+b'\n' for value in values)
    if len(raw)>limits.max_output_bytes: raise ValueError('Corpus exceeds output byte ceiling')
    receipt={'schema':'hero-corpus/1','sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
             'limits':asdict(limits),'sources':snapshots,'duplicates_removed':dropped,
             'splits':{split:sum(value['split']==split for value in values) for split in rank},'documents':len(values)}
    destination=Path(destination)
    destination.mkdir(parents=False,exist_ok=False)
    try:
        (destination/'documents.jsonl').write_bytes(raw)
        (destination/'manifest.json').write_text(json.dumps(receipt,indent=2,sort_keys=True,allow_nan=False)+'\n')
    except BaseException:
        # An incomplete destination has no successful receipt and is never reused.
        raise
    return receipt


def load_corpus(directory):
    directory=Path(directory)
    with (directory/'manifest.json').open('rb') as stream:
        manifest=stream.read(1024*1024+1)
    if len(manifest)>1024*1024: raise ValueError('Corpus manifest too large')
    receipt=json.loads(manifest)
    path=directory/'documents.jsonl'
    if path.stat().st_size>64*1024*1024: raise ValueError('Corpus exceeds load ceiling')
    raw=path.read_bytes()
    if receipt.get('schema')!='hero-corpus/1' or len(raw)!=receipt['bytes'] or hashlib.sha256(raw).hexdigest()!=receipt['sha256']:
        raise ValueError('Corpus identity differs from its successful receipt')
    values=[json.loads(line) for line in raw.splitlines()]
    if len(values)!=receipt['documents'] or not 1<=len(values)<=100000: raise ValueError('Corpus record count differs')
    for value in values:
        if value['source_id'] not in CATALOG or value['source_id'] not in receipt['sources'] or receipt['sources'][value['source_id']].get('approval')!=source_approval(value['source_id']):
            raise ValueError('Corpus record lacks selected source approval')
        if value['split'] not in ('train','validation','test') or type(value['text']) is not str or len(value['text'])>32768:
            raise ValueError('Invalid corpus record')
        if hashlib.sha256(' '.join(value['text'].split()).encode()).hexdigest()!=value['content_sha256']:
            raise ValueError('Corpus content identity differs')
    return receipt,values
