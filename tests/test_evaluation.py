from types import SimpleNamespace
import unittest

from hypnosis.evaluation import measure_split,syntax_probe


class EvaluationTests(unittest.TestCase):
    def test_exact_denominators_unknowns_missing_splits_and_finite_selection(self):
        records=[{'id':'a','text':'abc','split':'validation'},
                 {'id':'b','text':'unknown','split':'validation'},
                 {'id':'c','text':'train only','split':'train'}]
        def encode(text):
            if text=='unknown': raise ValueError('not representable')
            return [((1,2),(2,3)),((3,),(4,))]
        def score(pairs):
            return {'loss':1.0,'perplexity':2.718,'tokens':sum(len(b) for a,b in pairs),'sequences':len(pairs)}
        result=measure_split(records,'validation',encode_sequences=encode,score=score,max_sequences=1)
        self.assertEqual((result['tokens'],result['sequences']), (2,1))
        self.assertEqual((result['documents_available'],result['documents_unknown']), (2,1))
        self.assertEqual(result['selected_ids'],['a'])
        empty=measure_split(records,'test',encode_sequences=encode,score=score)
        self.assertEqual(empty['status'],'unavailable');self.assertEqual(empty['tokens'],0)

    def test_inconsistent_provider_counts_are_rejected(self):
        with self.assertRaises(ValueError):
            measure_split([{'id':'a','text':'a','split':'test'}],'test',
                encode_sequences=lambda _text:[((1,),(2,))],
                score=lambda _pairs:{'loss':1.0,'tokens':99,'sequences':1})

    def test_syntax_probe_counts_nonempty_and_never_executes_output(self):
        class Adapter:
            definition=SimpleNamespace(generation=SimpleNamespace(max_new_tokens=8))
            def stream(self,prompt):
                yield SimpleNamespace(text="raise RuntimeError('never execute')\n")
        result=syntax_probe(Adapter(),prompts=('\n',))
        self.assertEqual((result['attempted'],result['parsed'],result['failed']), (1,1,0))
