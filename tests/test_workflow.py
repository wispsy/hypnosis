import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hypnosis.workflow import WorkflowIdentity, training_workflow


@unittest.skipUnless(importlib.util.find_spec('func_seq'),'optional workflow profile is not installed')
class WorkflowTests(unittest.TestCase):
    def test_completed_stages_are_not_replayed_and_identity_changes_are_refused(self):
        from dataclasses import replace
        from func_seq import DefinitionMismatchError
        identity=WorkflowIdentity(*[str(n)*64 for n in (1,2,3,4)])
        calls=[]
        def prepare(): calls.append('prepare');return {'corpus':'selected'}
        def train(prepared): calls.append('train');return {**prepared,'trained':True}
        def evaluate(trained): calls.append('evaluate');return {**trained,'loss':1.5}
        def register(evaluated): calls.append('register');return evaluated
        def build(selected=identity):
            return training_workflow('fixture',selected,prepare=prepare,train=train,evaluate=evaluate,register=register)
        with TemporaryDirectory() as directory:
            path=Path(directory)/'workflow.json'
            partial=build().run(checkpoint=path,pace='function')
            self.assertEqual(partial.completed,('prepare',))
            with self.assertRaises(DefinitionMismatchError):
                build(replace(identity,corpus_sha256='5'*64)).run(checkpoint=path)
            completed=build().run(checkpoint=path)
            self.assertEqual(completed.status,'completed')
            self.assertEqual(calls,['prepare','train','evaluate','register'])
            build().run(checkpoint=path)
            self.assertEqual(len(calls),4)

    def test_uncertain_effect_requires_explicit_retry(self):
        from func_seq import RecoveryRequiredError,StepFailedError
        attempts=[]
        def prepare(): return {'ready':True}
        def train(value):
            attempts.append('attempt')
            if len(attempts)==1: raise RuntimeError('fixture interruption')
            return value
        def finish(value): return value
        def build():
            return training_workflow('retry-fixture',WorkflowIdentity(*['1'*64]*4),
                prepare=prepare,train=train,evaluate=finish,register=finish)
        with TemporaryDirectory() as directory:
            path=Path(directory)/'workflow.json'
            with self.assertRaises(StepFailedError): build().run(checkpoint=path)
            with self.assertRaises(RecoveryRequiredError): build().run(checkpoint=path)
            self.assertEqual(attempts,['attempt'])
            result=build().run(checkpoint=path,retry=True)
            self.assertEqual(result.status,'completed')
            self.assertEqual(len(attempts),2)
