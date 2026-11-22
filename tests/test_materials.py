from dataclasses import replace
import importlib.util
import io
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest

from hypnosis.data import Source,DataLimits,prepare_corpus,load_corpus
from hypnosis.data.sources import bind_source,SourceApprovalError


@unittest.skipUnless(importlib.util.find_spec('parse_md'),'optional Markdown profile is not installed')
class MaterialTests(unittest.TestCase):
    def test_complete_snapshot_growth_detection_markdown_spans_and_reference_groups(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);vault=root/'python3_vault';(vault/'tutorials').mkdir(parents=True)
            path=vault/'tutorials/functions.md'
            raw=('# Functions\n\nRef: [Official](https://docs.python.org/3/tutorial/controlflow.html#functions)\n\n'
                 'A function returns a value.\n\n```python\ndef f(x):\n    return x + 1\n```\n')
            path.write_text(raw)
            source=Source('python-vault-tutorials',str(vault));snapshot=bind_source(source)
            with self.assertRaises(ValueError): prepare_corpus([source],root/'unbound')
            selected=replace(source,fingerprint=snapshot['fingerprint'])
            # Find a train seed without changing the page/reference grouping.
            from hypnosis.data.materials import material_documents
            limits=DataLimits(text_characters=80,seed=1)
            records=list(material_documents(selected,snapshot,limits))
            self.assertTrue(all(r['group']=='python-doc:tutorial/controlflow' for r in records))
            self.assertTrue(any('def f(x)' in r['text'] for r in records))
            self.assertTrue(all('Ref:' not in r['text'] for r in records))
            for r in records:
                self.assertEqual(r['provenance']['file_sha256'],snapshot['files'][0]['sha256'])
                self.assertTrue(all(0<=a<b<=len(raw) for a,b in r['provenance']['source_spans']))
            (vault/'tutorials/new.md').write_text('# New approved snapshot candidate\n\nMore text.\n')
            with self.assertRaises(SourceApprovalError): bind_source(selected)

    def test_archive_members_are_streamed_and_unsafe_paths_are_refused(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);path=root/'python-3.14-docs-text.tar.bz2'
            def write(name):
                with tarfile.open(path,'w:bz2') as archive:
                    raw=b'Functions\n=========\n\nA function returns a value.\n';info=tarfile.TarInfo(name);info.size=len(raw)
                    archive.addfile(info,io.BytesIO(raw))
            write('python-3.14-docs-text/tutorial/controlflow.txt')
            source=Source('python314-docs',str(path));snapshot=bind_source(source)
            self.assertEqual(snapshot['file_count'],1)
            self.assertEqual(snapshot['files'][0]['file'],'tutorial/controlflow.txt')
            write('python-3.14-docs-text/../tutorial/controlflow.txt')
            with self.assertRaises(ValueError): bind_source(source)

    def test_snapshot_approval_survives_corpus_reopen_and_chunks_share_one_split(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);vault=root/'python3_vault';(vault/'tutorials').mkdir(parents=True)
            for n in range(20):
                (vault/f'tutorials/topic-{n}.md').write_text(f'# Topic {n}\n\n'+('A distinct lesson '+str(n)+'.\n\n')*8)
            source=Source('python-vault-tutorials',str(vault));source=replace(source,fingerprint=bind_source(source)['fingerprint'])
            prepare_corpus([source],root/'corpus',limits=DataLimits(documents_per_source=60,text_characters=100))
            receipt,values=load_corpus(root/'corpus')
            self.assertEqual(receipt['sources'][source.source_id]['approval'],'https://github.com/wispsy/hypnosis/issues/27')
            groups={}
            for value in values: groups.setdefault(value['group'],set()).add(value['split'])
            self.assertTrue(all(len(splits)==1 for splits in groups.values()))
