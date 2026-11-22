"""Versioned training-source mixtures and bounded, interleaved document windows."""
from collections import Counter,defaultdict,deque
import hashlib
import json
import random
import string

HERO_WEIGHTS={'internal-v1':20,'python-vault-tutorials':20,'tinystories-train':20,
 'simplewiki':10,'ud-train':5,'wiktionary':5,'python-vault-reference':5,
 'python314-docs':10,'psf-wiki-python':5}
CODING_WEIGHTS={'python-vault-tutorials':30,'python314-docs':35,'internal-v1':20,
                'python-vault-reference':10,'psf-wiki-python':5}
PYTHON_SOURCES=frozenset(CODING_WEIGHTS)-{'internal-v1'}


def identity(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def is_coding(document):
    return (document['source_id'] in PYTHON_SOURCES or
            (document['source_id']=='internal-v1' and document['provenance'].get('family','').startswith('python-')))


def _interleave(buckets,weights):
    served=Counter();active={name:iter(values) for name,values in buckets.items()}
    while active:
        source=min(active,key=lambda name:(served[name]/weights[name],name))
        try: value=next(active[source])
        except StopIteration: del active[source];continue
        served[source]+=1
        yield source,value


def prepare_selection(documents,config,*,tokenizer=None):
    from thoughtformula import BPETokenizer,token_sequences
    weights=CODING_WEIGHTS if config.model_id=='hero-coding' else HERO_WEIGHTS
    buckets=defaultdict(list)
    for value in documents:
        if value['split']!='train': raise ValueError('Tokenizer/window fitting accepts training records only')
        if value['source_id'] not in weights: raise ValueError('Source has no selected mixture weight')
        buckets[value['source_id']].append(value)
    if not buckets or len(buckets)>config.max_sequences: raise ValueError('Window budget cannot cover selected sources')
    for values in buckets.values():
        values.sort(key=lambda value:(value['provenance'].get('difficulty',4),
            hashlib.sha256(f"{config.seed}:{value['id']}".encode()).digest()))
    fitted=[];fit_characters=0
    if tokenizer is None:
        tokenizer=BPETokenizer();alphabet=set(string.printable)
        for values in buckets.values():
            for value in values: alphabet.update(value['text'])
        if len(alphabet)>8000: raise ValueError('Selected training alphabet exceeds the model vocabulary budget')
        tokenizer.BASE_ALPHABET+=''.join(sorted(alphabet))
        for source,value in _interleave(buckets,weights):
            remaining=512*1024-fit_characters
            if remaining<=0: break
            chunk=value['text'][:min(2048,remaining)]
            fitted.append(chunk);fit_characters+=len(chunk)
        if not fitted: raise ValueError('No training material fits tokenizer selection')
        tokenizer.train(tokenizer.EOS_TOKEN.join(fitted),max_merges=64)
    # At least one window per source, with largest-remainder allocation.
    total=sum(weights[name] for name in buckets);remaining=config.max_sequences-len(buckets)
    quotas={name:1+remaining*weights[name]//total for name in buckets}
    remainder=config.max_sequences-sum(quotas.values())
    order=sorted(buckets,key=lambda name:(-(remaining*weights[name]%total),name))
    for name in order[:remainder]: quotas[name]+=1
    pools={};selected_ids=set();unknown=Counter();eligible=Counter();unique_windows={}
    def windows(value):
        pairs=token_sequences(tokenizer,[value['text']],block_size=config.block_size,max_sequences=128)
        offset=int(hashlib.sha256(value['id'].encode()).hexdigest()[:8],16)%len(pairs)
        yield from pairs[offset:]+pairs[:offset]
    for source,values in buckets.items():
        queue=deque();pool=[]
        # Audit all eligibility; retain at most 1024 documents per source for this pool.
        for value in values:
            encoded=tokenizer.encode(value['text'])
            if tokenizer.decode(encoded)!=value['text']:
                unknown[source]+=1;continue
            eligible[source]+=1
            if len(queue)<min(quotas[source],1024): queue.append((value['id'],iter(windows(value))))
        while queue and len(pool)<quotas[source]:
            document_id,iterator=queue.popleft()
            try: pair=next(iterator)
            except StopIteration: continue
            selected_ids.add(document_id);pool.append(pair);queue.append((document_id,iterator))
        if not pool: raise ValueError('Selected source has no representable windows: '+source)
        unique_windows[source]=len(pool)
        # Small authored sets are deliberately oversampled to their selected weight.
        original=tuple(pool)
        while len(pool)<quotas[source]: pool.append(original[len(pool)%len(original)])
        pools[source]=pool
    combined=list(_interleave(pools,weights));sources=tuple(name for name,_pair in combined)
    pairs=tuple(pair for _name,pair in combined)
    selected=sorted(selected_ids)
    summary={'profile':'balanced-v2','sequences':len(pairs),'pairs_sha256':identity(pairs),
        'tokenizer_sha256':identity(tokenizer.to_dict()),'tokenizer_fit_characters':fit_characters,
        'documents_available':sum(map(len,buckets.values())),'documents_unknown':sum(unknown.values()),
        'documents_selected':len(selected),'selected_ids':selected[:256],'selected_ids_sha256':identity(selected),
        'sources':{name:{'weight':weights[name],'windows':quotas[name],'unique_windows':unique_windows[name],
                         'documents_available':len(buckets[name]),'documents_representable':eligible[name],
                         'documents_unknown':unknown[name]} for name in sorted(buckets)},
        'missing_recipe_sources':sorted(set(weights)-set(buckets))}
    return tokenizer,pairs,summary,sources


def consumed_windows(pairs,sources,steps,*,shuffle,seed):
    """Audit the native trainer's documented epoch/seed ordering, without math."""
    windows=Counter();tokens=Counter();epoch=-1;order=None
    for step in range(steps):
        selected_epoch,position=divmod(step,len(pairs))
        if epoch!=selected_epoch:
            order=list(range(len(pairs)))
            if shuffle: random.Random(seed+selected_epoch).shuffle(order)
            epoch=selected_epoch
        index=order[position];source=sources[index]
        windows[source]+=1;tokens[source]+=len(pairs[index][1])
    return {'windows':dict(windows),'tokens':dict(tokens)}
