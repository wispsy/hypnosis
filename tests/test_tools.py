import asyncio
import importlib.util
import json
import time
import unittest
from hypnosis.tools import ToolExecutor,ToolPolicy,ToolRequest
from hypnosis.runtime import RunControl

AVAILABLE=importlib.util.find_spec('hidden_moves') is not None

@unittest.skipUnless(AVAILABLE,'optional tools profile is not installed')
class ToolTests(unittest.IsolatedAsyncioTestCase):
    def catalog(self,funcs):
        from hidden_moves import Moves
        from hidden_moves.adapters import CapabilityCatalog
        moves=Moves()
        for name,func in funcs.items():moves.learn(func,name=name)
        return CapabilityCatalog(moves,funcs)

    async def test_selection_schemas_immutable_requests_and_structural_privacy(self):
        effects=[]
        def add(x:int,y:int)->int:effects.append((x,y));return x+y
        catalog=self.catalog({'add':add});runner=ToolExecutor(catalog,ToolPolicy(('add',)))
        args={'x':2,'y':3};request=ToolRequest('first','add',args);args['x']=99
        result=await runner.invoke(request);self.assertEqual(result.value,5)
        self.assertEqual((await runner.invoke(ToolRequest('bad','add',{'x':'PRIVATE','y':1}))).status,'denied')
        self.assertEqual((await runner.invoke(ToolRequest('unknown','other',{}))).code,'unselected')
        self.assertEqual(effects,[(2,3)])
        self.assertNotIn('PRIVATE',json.dumps(result.receipt()));self.assertNotIn('value',result.receipt())
        with self.assertRaises(ValueError):ToolExecutor(catalog,ToolPolicy(('other',)))

    async def test_async_cancel_and_budgets(self):
        async def wait()->str:await asyncio.sleep(1);return 'private result'
        catalog=self.catalog({'wait':wait})
        result=await ToolExecutor(catalog,ToolPolicy(('wait',),max_seconds=.005)).invoke(ToolRequest('timeout','wait',{}))
        self.assertEqual((result.status,result.effect),('limited','uncertain'))
        control=RunControl();control.cancel()
        runner=ToolExecutor(catalog,ToolPolicy(('wait',)))
        result=await runner.invoke(ToolRequest('cancel','wait',{}),control=control)
        self.assertEqual((result.status,runner.calls,result.effect),('canceled',0,'not_started'))
        runner=ToolExecutor(catalog,ToolPolicy(('wait',),max_calls=0))
        self.assertEqual((await runner.invoke(ToolRequest('empty','wait',{}))).code,'call_budget')

    async def test_sync_timeout_settles_once_and_output_is_bounded(self):
        effects=[]
        def slow()->str:time.sleep(.025);effects.append(1);return 'PRIVATE'
        catalog=self.catalog({'slow':slow})
        result=await ToolExecutor(catalog,ToolPolicy(('slow',),max_seconds=.001)).invoke(ToolRequest('slow','slow',{}))
        self.assertEqual((result.status,result.effect,effects),('limited','uncertain',[1]))
        def large()->str:return 'private'*10
        result=await ToolExecutor(self.catalog({'large':large}),ToolPolicy(('large',),max_output_bytes=4)).invoke(ToolRequest('large','large',{}))
        self.assertEqual(result.code,'output_budget');self.assertIsNone(result.value)
        runner=ToolExecutor(self.catalog({'large':large}),ToolPolicy(('large',),max_output_bytes=100))
        self.assertEqual((await runner.invoke(ToolRequest('one','large',{}))).status,'completed')
        self.assertEqual((await runner.invoke(ToolRequest('two','large',{}))).code,'output_budget')
        self.assertLessEqual(runner.output_bytes,100)
