"""Hypnosis citation policy over the published Parse MW syntax tree."""

from html import unescape
from html.parser import HTMLParser
from array import array
import re


class _References(HTMLParser):
    """Retain exact source spans; protect literal regions before syntax parsing."""
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source=source;self.lines=array('I',(0,));self.lines.extend(m.end() for m in re.finditer('\n',source))
        self.literal=None;self.active=None;self.references=[];self.replacements=[];self.count=0

    def _source_offset(self):
        line,column=self.getpos()
        return self.lines[line-1]+column

    def attributes(self, attrs):
        result={}
        for key,value in attrs:
            if key not in ('name','group'):continue
            value=(value or '').strip()
            if len(value)>256:raise ValueError('Reference name/group exceeds its bound')
            if key in result and result[key]!=value:raise ValueError('Conflicting reference attributes')
            result[key]=value
        return result.get('name',''),result.get('group','')

    def record(self, start, end, body, name, group):
        self.count+=1
        if self.count>4096:raise ValueError('Reference scan exceeds its bound')
        marker=f' [cite-{self.count}] ' if self.count<=128 else ' '
        self.replacements.append((start,end,marker))
        if self.count<=128:
            self.references.append({'id':f'cite-{self.count}','name':name,'group':group,
                'raw_start':start,'raw_end':end,'body':body[:4096],
                'body_truncated':len(body)>4096,'key':(group,name) if name else (None,self.count),
                'definition':body})

    def handle_starttag(self, tag, attrs):
        if self.literal:return
        if self.active:
            if tag=='ref':raise ValueError('Nested references are outside the excerpt profile')
            return
        if tag in ('nowiki','pre','code','math'):
            self.literal=tag;return
        if tag=='ref':
            name,group=self.attributes(attrs);start=self._source_offset()
            self.active=(start,start+len(self.get_starttag_text()),name,group)

    def handle_startendtag(self, tag, attrs):
        if self.literal:return
        if self.active:
            if tag=='ref':raise ValueError('Nested references are outside the excerpt profile')
            return
        if tag=='ref':
            name,group=self.attributes(attrs);start=self._source_offset()
            self.record(start,start+len(self.get_starttag_text()),'',name,group)

    def handle_endtag(self, tag):
        if self.literal:
            if tag==self.literal:self.literal=None
            return
        if tag=='ref' and self.active:
            start,body_start,name,group=self.active;closing=self._source_offset()
            match=re.compile(r'</\s*ref\s*>',re.I).match(self.source,closing)
            if match is None:raise ValueError('Reference closing span is not traceable')
            self.record(start,match.end(),self.source[body_start:closing],name,group)
            self.active=None

    def stripped(self):
        self.feed(self.source);self.close()
        if self.active:raise ValueError('Unclosed reference is outside the excerpt profile')
        chunks=[];cursor=0
        for start,end,marker in self.replacements:
            chunks.extend((self.source[cursor:start],marker));cursor=end
        chunks.append(self.source[cursor:])
        return ''.join(chunks)


def _plain(node, mw):
    if isinstance(node,mw.Text):return node.value
    if isinstance(node,mw.Entity):return unescape('&'+node.value+';')
    if isinstance(node,(mw.Comment,mw.Template,mw.Category,mw.Reference)):return ''
    if isinstance(node,(mw.Nowiki,mw.Pre,mw.Code,mw.Math)):return node.value
    if isinstance(node,mw.SectionLink):return node.label or node.target
    if isinstance(node,mw.HorizontalRule):return '\n'
    if isinstance(node,mw.Section):
        return _plain(node.heading,mw)+'\n'+'\n'.join(_plain(c,mw) for c in node.children)
    if isinstance(node,mw.Container):
        separator='\n' if isinstance(node,(mw.Document,mw.Fragment,mw.Table,mw.BulletList,mw.OrderedList)) else ' ' if isinstance(node,mw.TableRow) else ''
        return separator.join(_plain(child,mw) for child in node.children)
    raise ValueError('Unsupported MediaWiki node in the excerpt profile')


def clean_wikitext(text, *, max_characters=4096):
    if type(text) is not str or len(text)>4*1024*1024:raise ValueError('Wikitext exceeds the article limit')
    if type(max_characters) is not int or not 1<=max_characters<=4*1024*1024:raise ValueError('Select a finite excerpt character limit')
    import parse_mw as mw
    scanner=_References(text);source=scanner.stripped();references=scanner.references;definitions={}
    for reference in references:
        body=reference.pop('definition')
        if body:definitions.setdefault(reference['key'],set()).add(body)
    for reference in references:
        candidates=definitions.get(reference['key'],set())
        reference['ambiguous_name']=bool(reference['name'] and len(candidates)>1)
        body=reference['body']
        if not body and len(candidates)==1:
            full=next(iter(candidates));body=full[:4096];reference['body_truncated']=len(full)>4096
        reference['resolved']=bool(body);reference['body']=body
        reference['urls']=re.findall(r'https?://[^\s<>|}\]]+',body)[:16]
        reference.pop('key')
    document=mw.parse_fragment(source,options=mw.ParseOptions(max_characters=4*1024*1024,max_nesting=64,max_nodes=100_000))
    plain='\n'.join(line.strip() for line in _plain(document,mw).splitlines() if line.strip())
    return plain[:max_characters],references,{'text_truncated':len(plain)>max_characters,
        'references_truncated':scanner.count>128,'reference_count':scanner.count}
