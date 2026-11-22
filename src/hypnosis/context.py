"""Bounded context selection over explicitly configured Workspace sources."""
from dataclasses import dataclass
import hashlib
import math
from .tools import digest


@dataclass(frozen=True)
class ContextSource:
    path: str
    kind: str = 'knowledge'
    trusted: bool = False
    expected_sha256: str | None = None

    def __post_init__(self):
        if type(self.path) is not str or not self.path or len(self.path)>1024:raise ValueError('Use a selected relative path')
        if self.kind not in ('instructions','skill','knowledge') or type(self.trusted) is not bool:raise ValueError('Invalid context classification')
        if self.trusted and self.kind!='instructions':raise ValueError('Explicit trusted sources must be instructions')
        if self.expected_sha256 is not None:
            from .records import _sha
            _sha(self.expected_sha256)


@dataclass(frozen=True)
class ContextBudget:
    max_bytes: int = 16384
    max_tokens: int | None = None
    max_sources: int = 16
    max_reads: int = 32

    def __post_init__(self):
        if type(self.max_bytes) is not int or not 64<=self.max_bytes<=1024*1024:raise ValueError('Invalid context byte budget')
        if type(self.max_sources) is not int or not 1<=self.max_sources<=32:raise ValueError('Invalid source limit')
        if type(self.max_reads) is not int or not 1<=self.max_reads<=256:raise ValueError('Invalid read budget')
        if self.max_tokens is not None and (type(self.max_tokens) is not int or not 1<=self.max_tokens<=1024*1024):raise ValueError('Invalid token budget')


@dataclass(frozen=True)
class ContextChunk:
    path: str
    kind: str
    trusted: bool
    source_sha256: str
    text: str
    start_line: int
    start_column: int
    end_line: int
    truncated: bool
    heading_count: int = 0

    def reference(self):
        return {'source_sha256':self.source_sha256,'kind':self.kind,'trusted':self.trusted,
                'start_line':self.start_line,'start_column':self.start_column,'end_line':self.end_line,
                'truncated':self.truncated,'heading_count':self.heading_count,
                'excerpt_sha256':hashlib.sha256(self.text.encode()).hexdigest()}


def _prompt(instructions,chunks):
    result='[Caller instructions]\n'+instructions+'\n'
    for chunk in chunks:
        authority='trusted instruction' if chunk.trusted else 'untrusted data'
        result+=f'\n[{chunk.kind}: {chunk.path}; {authority}]\n'+chunk.text+'\n'
    return result


@dataclass(frozen=True)
class ContextBundle:
    instructions: str
    chunks: tuple[ContextChunk,...]
    selected_sources: int
    truncated: bool
    tokens: int | None
    reads: int = 0

    @property
    def prompt(self):return _prompt(self.instructions,self.chunks)

    @property
    def bytes(self):return len(self.prompt.encode('utf-8'))

    def receipt(self):
        # Paths, prompts, instruction text and excerpts remain private.
        return {'context_sha256':hashlib.sha256(self.prompt.encode()).hexdigest(),
                'selected_sources':self.selected_sources,'included_sources':len(self.chunks),
                'bytes':self.bytes,'tokens':self.tokens,'truncated':self.truncated,'reads':self.reads,
                'sources':[chunk.reference() for chunk in self.chunks]}


class ContextSelector:
    """No directory discovery, provider activation, URL following or code import.

    Workspace enforces file selection, UTF-8, read limits and expected identities.
    Optional token counting is the caller's actual tokenizer, not an estimate.
    """
    def __init__(self,workspace,budget=None,*,count_tokens=None):
        self.workspace=workspace;self.budget=budget if budget is not None else ContextBudget()
        if type(self.budget) is not ContextBudget:raise TypeError('Use ContextBudget')
        if self.budget.max_tokens is not None and count_tokens is None:raise ValueError('Token limits require an explicit tokenizer counter')
        if count_tokens is not None and not callable(count_tokens):raise TypeError('Token counter must be callable')
        self.count_tokens=count_tokens

    def _tokens(self,text):
        if self.count_tokens is None:return None
        value=self.count_tokens(text)
        if type(value) is not int or value<0:raise ValueError('Token counters must return a nonnegative integer')
        return value

    def _fits(self,text):
        if len(text.encode('utf-8'))>self.budget.max_bytes:return False
        return self.budget.max_tokens is None or self._tokens(text)<=self.budget.max_tokens

    def select(self,sources,*,instructions='',query=''):
        if type(instructions) is not str or type(query) is not str:raise TypeError('Context text requires strings')
        sources=tuple(sources)
        if len(sources)>32 or any(type(s) is not ContextSource for s in sources) or len({s.path for s in sources})!=len(sources):raise ValueError('Use distinct explicitly selected sources')
        if not self._fits(_prompt(instructions,())):raise ValueError('Trusted instructions exceed the context budget')
        chunks=[];reads=0;truncated=len(sources)>self.budget.max_sources
        for source in sources[:self.budget.max_sources]:
            if reads>=self.budget.max_reads:truncated=True;break
            line,column=1,1;expected=source.expected_sha256
            if query and not source.trusted and source.kind!='instructions':
                reads+=1
                matches=self.workspace.search(source.path,query,max_matches=1,expected_sha256=expected)
                if not matches.matches:continue
                line=max(1,matches.matches[0].line-2);expected=matches.sha256
            start=line;start_column=column;accumulated='';last_line=line;more=False
            read_limited=False
            for _ in range(self.budget.max_reads):
                if reads>=self.budget.max_reads:read_limited=True;more=True;break
                reads+=1
                page=self.workspace.read(source.path,start_line=line,start_column=column,line_count=200,expected_sha256=expected)
                expected=page.sha256
                part='\n'.join(value.text for value in page.lines)
                separator='' if not accumulated or column>1 else '\n'
                proposed=accumulated+separator+part;last_line=page.lines[-1].number if page.lines else line
                draft=ContextChunk(source.path,source.kind,source.trusted,page.sha256,proposed,start,start_column,last_line,False)
                if not self._fits(_prompt(instructions,(*chunks,draft))):
                    low,high=0,len(proposed)
                    while low<high:
                        middle=(low+high+1)//2
                        candidate=ContextChunk(source.path,source.kind,source.trusted,page.sha256,proposed[:middle],start,start_column,last_line,True)
                        if self._fits(_prompt(instructions,(*chunks,candidate))):low=middle
                        else:high=middle-1
                    proposed=proposed[:low];more=True
                    # Binary packing need not maximize non-monotonic tokenization;
                    # the final accepted prompt still has to satisfy the exact cap.
                    draft=ContextChunk(source.path,source.kind,source.trusted,page.sha256,proposed,start,start_column,
                                       start+proposed.count('\n'),True)
                    if proposed and self._fits(_prompt(instructions,(*chunks,draft))):chunks.append(draft)
                    truncated=True;break
                accumulated=proposed
                more=page.next_line is not None
                if not more:
                    draft=ContextChunk(source.path,source.kind,source.trusted,page.sha256,proposed,start,start_column,last_line,start>1)
                    chunks.append(draft);break
                line,column=page.next_line,page.next_column
            else:read_limited=True;more=True
            if read_limited:
                truncated=True
                if accumulated:chunks.append(ContextChunk(source.path,source.kind,source.trusted,expected,accumulated,start,start_column,last_line,True))
            if more and truncated:break
        # Structure comes from the existing Markdown parser, not document directives.
        from dataclasses import replace
        from parse_md import Heading,parse_blocks
        annotated=[]
        for chunk in chunks:
            headings=sum(isinstance(node,Heading) for node in parse_blocks(chunk.text).children) if chunk.path.lower().endswith('.md') else 0
            annotated.append(replace(chunk,heading_count=headings))
        result=ContextBundle(instructions,tuple(annotated),len(sources),truncated or any(c.truncated for c in annotated),None,reads)
        result=replace(result,tokens=self._tokens(result.prompt))
        if not self._fits(result.prompt):raise ValueError('Context packing exceeded its selected budget')
        return result
