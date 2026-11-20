"""Provider-neutral held-out denominators, with a Thoughtformula loss adapter."""
import ast
import hashlib
import math


def measure_split(documents, split, *, encode_sequences, score, max_sequences=32):
    """Measure explicit split records, never filling a missing split from train."""
    if split not in ('train','validation','test') or type(max_sequences) is not int or not 1<=max_sequences<=256:
        raise ValueError('Select a finite evaluation split and sequence budget')
    available=representable=unknown=0;selected=[];pairs=[];buckets={};selected_sources={};windows=[]
    for document in documents:
        if document['split']!=split: continue
        available+=1
        try:
            encoded=encode_sequences(document['text'])
        except ValueError:
            unknown+=1;continue
        representable+=1
        if encoded:
            source=document.get('source_id','unspecified')
            family=document.get('provenance',{}).get('family','text')
            bucket=buckets.setdefault((source,family),[])
            if len(bucket)<max_sequences:
                index=int(hashlib.sha256(document['id'].encode()).hexdigest()[:8],16)%len(encoded)
                bucket.append((document['id'],index,encoded[index]))
    # Balance source/family strata, then choose one fixed window per document.
    # A long first story cannot consume the complete held-out budget.
    for position in range(max_sequences):
        for key,bucket in sorted(buckets.items()):
            if position<len(bucket) and len(pairs)<max_sequences:
                document_id,index,pair=bucket[position]
                selected.append(document_id);windows.append(index);pairs.append(pair)
                selected_sources[key[0]]=selected_sources.get(key[0],0)+1
    counts={'documents_available':available,'documents_representable':representable,
            'documents_unknown':unknown,'documents_selected':len(selected),
            'selected_ids':selected,'selected_window_indexes':windows,'selected_sources':selected_sources,
            'sequence_limit':max_sequences,
            'coverage':representable/available if available else None}
    if not pairs:
        return {**counts,'status':'unavailable','loss':None,'perplexity':None,'tokens':0,'sequences':0}
    measured=score(pairs)
    tokens=sum(len(right) for _left,right in pairs)
    if measured['tokens']!=tokens or measured['sequences']!=len(pairs) or not math.isfinite(measured['loss']):
        raise ValueError('Provider returned inconsistent evaluation denominators')
    return {**counts,**measured,'status':'measured'}


def thoughtformula_metrics(model, tokenizer, documents, *, block_size=32, max_sequences=32):
    from thoughtformula import evaluate, token_sequences
    def encode(text):
        return token_sequences(tokenizer,[text],block_size=block_size,max_sequences=256)
    def score(pairs):
        return evaluate(model,pairs,block_size=block_size,max_sequences=max_sequences)
    return {split:measure_split(documents,split,encode_sequences=encode,score=score,
                               max_sequences=max_sequences)
            for split in ('validation','test')}


def syntax_probe(adapter, prompts=('def solve(a, b):\n    ',)):
    """Parse bounded continuations only; never execute model-generated code."""
    prompts=tuple(prompts)
    if not 1<=len(prompts)<=4 or any(type(text) is not str or len(text)>256 for text in prompts):
        raise ValueError('Select at most four bounded syntax prompts')
    if adapter.definition.generation.max_new_tokens>64:
        raise ValueError('Syntax probes require at most 64 generated tokens')
    parsed=nonempty=failures=0
    for prompt in prompts:
        try:
            continuation=''.join(token.text for token in adapter.stream(prompt))
            if len(continuation)>4096: raise ValueError('Syntax continuation exceeds byte budget')
            if not continuation.strip(): continue
            nonempty+=1
            try: ast.parse(prompt+continuation)
            except (SyntaxError,ValueError): pass
            else: parsed+=1
        except ValueError: failures+=1
    return {'attempted':len(prompts),'nonempty':nonempty,'parsed':parsed,'failed':failures,
            'claim':'syntax-only; no execution, functional correctness or agent-capability claim'}
