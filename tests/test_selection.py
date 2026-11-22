from dataclasses import replace
import hashlib
import importlib.util
from types import SimpleNamespace
import unittest

from hypnosis.training import JobConfig,job_settings


@unittest.skipUnless(importlib.util.find_spec('thoughtformula'),'optional model profile is not installed')
class SelectionTests(unittest.TestCase):
    def records(self):
        values=[]
        for source in ['internal-v1','python-vault-tutorials','tinystories-train','simplewiki','python314-docs']:
            for number in range(3):
                values.append({'id':source+':'+str(number),'source_id':source,'split':'train',
                    'text':f'Lesson {number} in {source}. α = {number}\n'*3,
                    'provenance':{'difficulty':number+1,'family':'python-addition' if source=='internal-v1' else 'text'}})
        return values

    def test_interleaving_covers_sources_and_every_training_character(self):
        from hypnosis.selection import prepare_selection,consumed_windows
        config=JobConfig('selection',profile='balanced-v2',max_sequences=60,block_size=8)
        tokenizer,pairs,summary,sources=prepare_selection(self.records(),config)
        self.assertEqual(len(pairs),60)
        self.assertEqual(set(sources),{r['source_id'] for r in self.records()})
        self.assertEqual(set(sources[:10]),set(sources))
        self.assertEqual(summary['documents_unknown'],0)
        self.assertEqual(tokenizer.decode(tokenizer.encode('α = 1')),'α = 1')
        _,other,repeat,other_sources=prepare_selection(self.records(),config)
        self.assertEqual((pairs,summary,sources),(other,repeat,other_sources))
        consumed=consumed_windows(pairs,sources,70,shuffle=False,seed=7)
        self.assertEqual(sum(consumed['windows'].values()),70)
        self.assertEqual(sum(consumed['tokens'].values()),sum(len(pairs[n%60][1]) for n in range(70)))

    def test_heldout_records_are_refused_and_parent_vocabulary_is_not_refitted(self):
        from hypnosis.selection import prepare_selection
        records=self.records();config=JobConfig('selection',profile='balanced-v2',max_sequences=20,block_size=8)
        tokenizer,pairs,summary,sources=prepare_selection(records,config)
        frozen=tokenizer.to_dict()
        coding=[r for r in records if r['source_id'] in ('internal-v1','python-vault-tutorials','python314-docs')]
        _,_,selected,_=prepare_selection(coding,replace(config,model_id='hero-coding'),tokenizer=tokenizer)
        self.assertEqual(tokenizer.to_dict(),frozen)
        self.assertEqual(selected['tokenizer_fit_characters'],0)
        records[0]={**records[0],'split':'test'}
        with self.assertRaises(ValueError): prepare_selection(records,config)

    def test_legacy_settings_keep_their_original_identity_shape(self):
        old=JobConfig('legacy')
        self.assertNotIn('profile',job_settings(old))
        self.assertEqual(set(job_settings(old)),{'run_id','model_id','max_steps','max_seconds','block_size',
            'learning_rate','seed','shuffle','max_sequences','evaluation_sequences','checkpoint_interval'})
        self.assertEqual(JobConfig('long',profile='balanced-v2',max_seconds=1800).max_seconds,1800)
        with self.assertRaises(ValueError): JobConfig('legacy',max_seconds=1800)
