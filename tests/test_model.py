import asyncio
import importlib.util
import io
import unittest


@unittest.skipUnless(importlib.util.find_spec('thoughtform') and importlib.util.find_spec('thoughtformula'),
                     'optional models profile is not installed')
class ModelCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_transformer_through_harness_and_carets(self):
        from carets import Program
        from carets.testing import SnapshotRenderer
        from thoughtform import GenerationConfig, ModelDefinition
        from thoughtform.thoughtformula import ThoughtformulaModel
        from thoughtformula import BPETokenizer, ModernMicroGPT
        from hypnosis.execution import model_text
        from hypnosis.terminal import HarnessTerminal
        tokenizer = BPETokenizer()
        tokenizer.train('hello world', max_merges=0)
        transformer = ModernMicroGPT(len(tokenizer.vocab), n_embd=8, n_heads=2, n_kv_heads=1,
            n_layers=1, n_experts=1, moe_top_k=1, expert_hidden=8, lora_rank=2)
        adapter = ThoughtformulaModel(ModelDefinition('tiny', 'thoughtformula', 'synthetic-untrained',
            GenerationConfig(max_new_tokens=3, temperature=0)), transformer, tokenizer)
        model = HarnessTerminal(lambda: model_text(adapter, 'hello'), exit_on_completion=True)
        renderer = SnapshotRenderer()
        program = model.program = Program(model, renderer=renderer, output_stream=io.StringIO(), stream_buffer=2)
        await asyncio.wait_for(program.run([], stop_on_eof=False, commands=[model.start()]), 5)
        self.assertEqual(model.status, 'completed')
        self.assertIn('completed', renderer.latest)
        self.assertGreaterEqual(len(renderer.frames), 2)
