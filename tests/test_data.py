import bz2
import hashlib
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

    @unittest.skipUnless(importlib.util.find_spec('parse_mw'),'optional Wikipedia parser is not installed')
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

    @unittest.skipUnless(importlib.util.find_spec('parse_mw'),'optional Wikipedia parser is not installed')
    def test_conflicting_named_references_and_groups_remain_distinct(self):
        from hypnosis.data.wiki import clean_wikitext
        raw=("A<ref name='same'>https://example.org/a</ref>"
             "B<ref name='same'>https://example.org/b</ref>"
             "C<ref name='same'/>"
             "D<ref name='same' group='other'>https://example.org/c</ref>"
             "E<ref name='same' group='other'/>")
        _text,refs,_metadata=clean_wikitext(raw)
        self.assertEqual(refs[0]['urls'],['https://example.org/a'])
        self.assertEqual(refs[1]['urls'],['https://example.org/b'])
        self.assertTrue(refs[2]['ambiguous_name']);self.assertFalse(refs[2]['resolved'])
        self.assertEqual(refs[2]['urls'],[])
        self.assertEqual(refs[4]['urls'],['https://example.org/c'])
        self.assertFalse(refs[4]['ambiguous_name'])
        _text,refs,_metadata=clean_wikitext("A<ref name='long'>"+'x'*5000+"</ref>B<ref name='long'/>")
        self.assertTrue(refs[1]['body_truncated'])

    def test_loading_does_not_admit_new_source_ids_through_a_receipt(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);path=root/'TinyStories-train.txt'
            path.write_text('Authored story.\n<|endoftext|>\n')
            prepare_corpus([Source('tinystories-train',str(path))],root/'out')
            manifest=root/'out/manifest.json';data=root/'out/documents.jsonl'
            value=json.loads(data.read_text());value['source_id']='python3-vault'
            raw=(json.dumps(value)+'\n').encode();data.write_bytes(raw)
            receipt=json.loads(manifest.read_text());receipt['sha256']=hashlib.sha256(raw).hexdigest();receipt['bytes']=len(raw)
            receipt['sources']['python3-vault']=receipt['sources'].pop('tinystories-train')
            manifest.write_text(json.dumps(receipt))
            with self.assertRaises(ValueError): load_corpus(root/'out')


@unittest.skipUnless(importlib.util.find_spec('parse_mw'),'optional Parse MW profile is not installed')
class WikitextTests(unittest.TestCase):
    def test_published_parser_preserves_display_text_and_drops_templates(self):
        import parse_mw
        from unittest.mock import patch
        from hypnosis.data.wiki import clean_wikitext
        raw="'''Bold''' &amp; [[Target|label]] {{Unexpanded|secret}}<ref>https://example.org/a</ref>"
        with patch.object(parse_mw,'parse_fragment',wraps=parse_mw.parse_fragment) as parsed:
            text,refs,_=clean_wikitext(raw)
        self.assertEqual(parsed.call_count,1)
        self.assertIn('Bold & label',text);self.assertNotIn('secret',text)
        self.assertEqual(refs[0]['urls'],['https://example.org/a'])

    def test_literal_regions_comments_unicode_and_exact_spans(self):
        from hypnosis.data.wiki import clean_wikitext
        raw=("α\r\n<!-- <ref name='a'>ignored</ref> -->"
             "<nowiki><ref name='a'>literal</ref></nowiki>"
             "<REF NAME = a GROUP = note>https://example.org/a</REF>"
             "Again<REF NAME=a GROUP=note />")
        text,refs,metadata=clean_wikitext(raw)
        self.assertEqual(metadata['reference_count'],2)
        self.assertEqual(refs[0]['group'],'note');self.assertTrue(refs[1]['resolved'])
        self.assertEqual(refs[1]['urls'],['https://example.org/a'])
        self.assertEqual(raw[refs[0]['raw_start']:refs[0]['raw_end']],'<REF NAME = a GROUP = note>https://example.org/a</REF>')
        self.assertEqual(raw[refs[1]['raw_start']:refs[1]['raw_end']],'<REF NAME=a GROUP=note />')
        self.assertIn("<ref name='a'>literal</ref>",text);self.assertNotIn('ignored',text)

    def test_reference_and_excerpt_budgets_are_explicit(self):
        from hypnosis.data.wiki import clean_wikitext
        text,refs,metadata=clean_wikitext('word'+''.join('<ref>https://example.org/'+str(n)+'</ref>' for n in range(130)),max_characters=10)
        self.assertEqual(len(refs),128);self.assertEqual(metadata['reference_count'],130)
        self.assertTrue(metadata['references_truncated']);self.assertTrue(metadata['text_truncated'])
        self.assertLessEqual(len(text),10)
        for raw,kwargs in (('a',{'max_characters':0}),('a',{'max_characters':True}),('x'*(4*1024*1024+1),{}),('<ref/>'*4097,{})):
            with self.assertRaises(ValueError):clean_wikitext(raw,**kwargs)

    def test_unclosed_nested_and_conflicting_attributes_refuse(self):
        from hypnosis.data.wiki import clean_wikitext
        for raw in ('<ref>unclosed','<ref>outer<ref/>inner</ref>',"<ref name='a' name='b'/>",'<ref name="'+('x'*257)+'"/>'):
            with self.subTest(raw=raw[:60]),self.assertRaises(ValueError):clean_wikitext(raw)
