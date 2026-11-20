"""Bounded indexed bz2 Wikipedia blocks and citation-preserving Wikitext excerpts."""
import bz2
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def index_blocks(path,*,max_lines=10000):
    prior=None;entries=[]
    with bz2.open(path,'rb') as stream:
        for _ in range(max_lines):
            raw=stream.readline(16385)
            if not raw: break
            if len(raw)>16384: raise ValueError('Index record exceeds its byte limit')
            offset,page,title=raw.decode('utf-8').rstrip('\r\n').split(':',2)
            if not offset.isascii() or not offset.isdigit() or not page.isascii() or not page.isdigit():
                raise ValueError('Invalid Wikipedia index identity')
            offset=int(offset);page=int(page)
            if prior is not None and offset<prior: raise ValueError('Wikipedia index offsets are not ordered')
            if prior is not None and offset!=prior:
                yield prior,offset,tuple(entries)
                entries=[]
            prior=offset;entries.append((page,title))
            if len(entries)>1000: raise ValueError('Too many pages in one indexed block')
        else:
            # A line ceiling must not fabricate the end of the current stream.
            return
    if prior is not None: yield prior,None,tuple(entries)


def _text(element,name):
    for child in element:
        if child.tag.rsplit('}',1)[-1]==name: return child.text or ''
    return ''


def pages(dump,index,*,max_pages=32,max_blocks=8,max_expanded_bytes=16*1024*1024):
    if type(max_pages) is not int or not 1<=max_pages<=10000 or type(max_blocks) is not int or not 1<=max_blocks<=1000:
        raise ValueError('Select finite Wikipedia page/block limits')
    dump=Path(dump);size=dump.stat().st_size;produced=0
    with dump.open('rb') as stream:
        for block_no,(start,end,entries) in enumerate(index_blocks(index)):
            if block_no>=max_blocks: return
            end=size if end is None else end
            if not 0<=start<end<=size or end-start>8*1024*1024: raise ValueError('Invalid or oversized compressed block')
            stream.seek(start);raw=stream.read(end-start)
            decoder=bz2.BZ2Decompressor();expanded=decoder.decompress(raw,max_length=max_expanded_bytes+1)
            if len(expanded)>max_expanded_bytes or not decoder.eof or decoder.unused_data:
                raise ValueError('Invalid or oversized expanded block')
            if b'<!DOCTYPE' in expanded.upper() or b'<!ENTITY' in expanded.upper(): raise ValueError('XML declarations are outside this fragment profile')
            fragment=expanded.strip()
            if fragment.endswith(b'</mediawiki>'): fragment=fragment[:-len(b'</mediawiki>')]
            tree=ET.fromstring(b'<mediawiki>'+fragment+b'</mediawiki>')
            expected=dict(entries)
            actual=[p for p in tree if p.tag.rsplit('}',1)[-1]=='page']
            for page in actual:
                page_id=int(_text(page,'id'));title=_text(page,'title')
                if expected.get(page_id)!=title: raise ValueError('Index and dump page identity differ')
            if {int(_text(p,'id')) for p in actual}!=set(expected): raise ValueError('Index/dump block membership differs')
            block_sha=hashlib.sha256(raw).hexdigest()
            for page in actual:
                if _text(page,'ns')!='0' or any(child.tag.rsplit('}',1)[-1]=='redirect' for child in page): continue
                revisions=[child for child in page if child.tag.rsplit('}',1)[-1]=='revision']
                if len(revisions)!=1: raise ValueError('Select current-revision page dumps')
                revision=revisions[0];markup=_text(revision,'text')
                yield {'page_id':int(_text(page,'id')),'title':_text(page,'title'),
                       'revision_id':_text(revision,'id'),'markup':markup,'compressed_block_sha256':block_sha,
                       'raw_sha256':hashlib.sha256(markup.encode()).hexdigest(),'block_offset':start}
                produced+=1
                if produced>=max_pages: return


def clean_wikitext(text,*,max_characters=4096):
    import mwparserfromhell
    if type(text) is not str or len(text)>4*1024*1024: raise ValueError('Wikitext exceeds the article limit')
    code=mwparserfromhell.parse(text)
    references=[];cursor=0;definitions={}
    tags=code.filter_tags(matches=lambda value:str(value.tag).strip().lower()=='ref')
    for number,tag in enumerate(tags,1):
        if number>128: break
        raw=str(tag);start=text.find(raw,cursor)
        if start<0: raise ValueError('Reference span is not traceable')
        cursor=start+len(raw)
        name=str(tag.get('name').value).strip('"\' ') if tag.has('name') else ''
        group=str(tag.get('group').value).strip('"\' ') if tag.has('group') else ''
        if len(name)>256 or len(group)>256: raise ValueError('Reference name/group exceeds its bound')
        body=str(tag.contents) if tag.contents is not None else ''
        key=(group,name) if name else (None,number)
        if body: definitions.setdefault(key,set()).add(body)
        references.append({'id':f'cite-{number}','name':name,'group':group,'raw_start':start,'raw_end':cursor,
                           'body':body[:4096],'body_truncated':len(body)>4096,'key':key})
        code.replace(tag,f' [cite-{number}] ')
    for reference in references:
        candidates=definitions.get(reference['key'],set())
        reference['ambiguous_name']=bool(reference['name'] and len(candidates)>1)
        body=reference['body']
        if not body and len(candidates)==1:
            full=next(iter(candidates));body=full[:4096]
            reference['body_truncated']=len(full)>4096
        reference['resolved']=bool(body);reference['body']=body
        reference['urls']=re.findall(r'https?://[^\s<>|}\]]+',body)[:16]
        reference.pop('key')
    plain=code.strip_code(normalize=True,collapse=True)
    plain='\n'.join(line.strip() for line in plain.splitlines() if line.strip())
    truncated=len(plain)>max_characters
    return plain[:max_characters],references,{'text_truncated':truncated,'references_truncated':len(tags)>128,'reference_count':len(tags)}
