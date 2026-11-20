import ast
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hypnosis.curriculum import generated_documents
from hypnosis.data import DataLimits, Source, load_corpus, prepare_corpus


class CurriculumTests(unittest.TestCase):
    def test_reproducible_original_recipe_and_independently_checked_references(self):
        values=list(generated_documents(seed=11))
        self.assertEqual(values,list(generated_documents(seed=11)))
        self.assertEqual(len(values),320)
        for value in values:
            check=value['provenance']['verification']
            if value['provenance']['family'].startswith('python-'):
                code=value['text'].split('Python:\n',1)[1]
                ast.parse(code)
                namespace={'__builtins__':{'sum':sum}}
                # Only the local authored templates are executed in this test.
                exec(compile(code,'<authored-reference>','exec'),namespace)
                self.assertEqual(namespace['solve'](*check['arguments']),check['expected'])
            else:
                left,right=check['operands']
                actual=left+right if check['operator']=='add' else left*right
                self.assertEqual(actual,check['expected'])

    def test_grouped_variants_cannot_leak_and_selection_is_bounded(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)/'corpus'
            prepare_corpus([Source('internal-v1','recipe')],root,
                limits=DataLimits(documents_per_source=320,max_documents=320))
            receipt,values=load_corpus(root)
            groups={}
            for value in values: groups.setdefault(value['group'],set()).add(value['split'])
            self.assertTrue(all(len(splits)==1 for splits in groups.values()))
            self.assertTrue(all(receipt['splits'][split]>0 for split in ('train','validation','test')))
            limited=Path(directory)/'limited'
            result=prepare_corpus([Source('internal-v1','recipe')],limited,
                limits=DataLimits(documents_per_source=5))
            self.assertEqual(result['documents'],5)
