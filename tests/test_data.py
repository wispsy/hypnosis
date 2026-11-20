import bz2
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hypnosis.data import Source,SourceApprovalError,DataLimits,prepare_corpus,load_corpus,file_snapshot
from hypnosis.data.wiki import pages


class DataTests(unittest.TestCase):
    def test_unapproved_sources_and_changed_snapshots_are_rejected(self):
        with self.assertRaises(SourceApprovalError): Source('python3-vault','notes.md')
        with TemporaryDirectory() as directory:
            path=Path(directory)/'TinyStories-train.txt'
            path.write_text('A small authored story.\n<|endoftext|>\n')
            snapshot=file_snapshot(path)
            source=Source('tinystories-train',str(path),fingerprint=snapshot['fingerprint'])
            path.write_text('Changed source.\n<|endoftext|>\n')
            with self.assertRaises(SourceApprovalError): prepare_corpus([source],Path(directory)/'corpus')
            path.write_bytes(b'')
            with self.assertRaises(ValueError): file_snapshot(path)

    def test_official_evaluation_precedence_dedup_and_immutable_output(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            train=root/'TinyStories-train.txt';valid=root/'TinyStories-valid.txt'
            train.write_text('A shared story.\n<|endoftext|>\nA train story.\n<|endoftext|>\n')
            valid.write_text('A shared story.\n<|endoftext|>\n')
            sources=[Source('tinystories-train',str(train)),Source('tinystories-valid',str(valid))]
            result=prepare_corpus(sources,root/'corpus')
            self.assertEqual(result['splits'],{'train':1,'validation':1,'test':0})
            receipt,values=load_corpus(root/'corpus')
            self.assertEqual(receipt,result)
            self.assertEqual(len({v['content_sha256'] for v in values}),2)
            with self.assertRaises(FileExistsError): prepare_corpus(sources,root/'corpus')
            (root/'corpus/documents.jsonl').write_bytes(b'changed')
            with self.assertRaises(ValueError): load_corpus(root/'corpus')

    def test_indexed_member_read_and_mismatched_index_refusal(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            header=b'<mediawiki>'
            first=b'<page><title>A: title</title><ns>0</ns><id>1</id><revision><id>2</id><text>A page.</text></revision></page>'
            second=b'<page><title>Second</title><ns>0</ns><id>3</id><revision><id>4</id><text>Next page.</text></revision></page></mediawiki>'
            blocks=[bz2.compress(value) for value in (header,first,second)]
            dump=root/'dump.bz2';index=root/'index.txt.bz2'
            dump.write_bytes(b''.join(blocks))
            start=len(blocks[0]);next_start=start+len(blocks[1])
            index.write_bytes(bz2.compress(f'{start}:1:A: title\n{next_start}:3:Second\n'.encode()))
            self.assertEqual([v['title'] for v in pages(dump,index,max_pages=1)],['A: title'])
            self.assertEqual(len(list(pages(dump,index))),2)
            index.write_bytes(bz2.compress(f'{start}:1:Wrong\n{next_start}:3:Second\n'.encode()))
            with self.assertRaises(ValueError): list(pages(dump,index))

    @unittest.skipUnless(importlib.util.find_spec('mwparserfromhell'),'optional Wikipedia parser is not installed')
    def test_citation_markers_named_reuse_and_provenance_spans_survive(self):
        from hypnosis.data.wiki import clean_wikitext
        raw="'''A star''' is bright.<ref name='a'>https://example.org/evidence</ref> Again.<ref name='a'/>"
        text,references,excerpt=clean_wikitext(raw)
        self.assertIn('[cite-1]',text);self.assertIn('[cite-2]',text)
        self.assertEqual(len(references),2)
        self.assertEqual(references[1]['urls'],['https://example.org/evidence'])
        self.assertTrue(references[1]['resolved'])
        self.assertTrue(raw[references[0]['raw_start']:references[0]['raw_end']].startswith('<ref'))
        self.assertFalse(excerpt['references_truncated'])

    def test_corpus_byte_budget_is_enforced_before_publication(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);path=root/'TinyStories-train.txt'
            path.write_text('Authored story.\n<|endoftext|>\n')
            with self.assertRaises(ValueError): prepare_corpus([Source('tinystories-train',str(path))],root/'out',limits=DataLimits(max_output_bytes=10))
            self.assertFalse((root/'out').exists())
