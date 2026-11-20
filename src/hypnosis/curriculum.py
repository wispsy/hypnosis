"""The explicitly reviewed internally authored pilot recipe, version one."""
import hashlib
import json
import random

from .data.corpus import group_split
from .data.sources import APPROVAL

RECIPE = 'wispsy-internal-curriculum/v1'
SPECIFICATION = {'recipe': RECIPE, 'problems': 64, 'operand_range': [0, 39],
                 'families': ['addition', 'multiplication', 'python-addition',
                              'python-parity', 'python-aggregation']}
RECIPE_SHA256 = hashlib.sha256(json.dumps(SPECIFICATION, sort_keys=True).encode()).hexdigest()


def generated_documents(*, seed=1):
    """Yield finite, original exercises with exact answers and grouped variants.

    No model, downloaded material, vault notes or external teacher is involved.
    Code is an authored template with a reference assertion. Model-generated
    code is never executed by this generator or its verification tests.
    """
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('Select a finite curriculum seed')
    rng = random.Random(seed)

    def document(family, problem, text, level, verification):
        group = 'internal-v1:' + problem
        return {'id': 'internal-v1:' + family + ':' + problem,
                'source_id': 'internal-v1', 'group': group,
                'split': group_split(group, seed), 'text': text,
                'content_sha256': hashlib.sha256(' '.join(text.split()).encode()).hexdigest(),
                'provenance': {'approval': APPROVAL, 'recipe': RECIPE,
                    'recipe_sha256': RECIPE_SHA256, 'origin': 'internally-authored-template',
                    'family': family, 'difficulty': level, 'verification': verification,
                    'text_truncated': False}}

    for number in range(SPECIFICATION['problems']):
        a, b = sorted((rng.randrange(40), rng.randrange(40)))
        add = f'add:{a}:{b}';multiply = f'multiply:{a}:{b}'
        yield document('addition', add,
            f'Question: What is {a} plus {b}?\nAnswer: {a} + {b} = {a+b}.\n', 1,
            {'operator': 'add', 'operands': [a,b], 'expected': a+b})
        yield document('multiplication', multiply,
            f'Question: What is {a} times {b}?\nAnswer: {a} * {b} = {a*b}.\n', 2,
            {'operator': 'multiply', 'operands': [a,b], 'expected': a*b})
        yield document('python-addition', add,
            f'Task: Write a Python function that adds two numbers.\nPython:\n'
            f'def solve(a, b):\n    return a + b\n\nassert solve({a}, {b}) == {a+b}\n', 2,
            {'function': 'solve', 'arguments': [a,b], 'expected': a+b})
        values = [rng.randrange(30) for _ in range(4 + number % 4)]
        result = [value for value in values if value % 2 == 0]
        key = ':'.join(map(str,values))
        yield document('python-parity', 'even:'+key,
            'Task: Keep the even integers from a Python list.\nPython:\n'
            'def solve(values):\n    return [value for value in values if value % 2 == 0]\n\n'
            f'assert solve({values!r}) == {result!r}\n', 3,
            {'function': 'solve', 'arguments': [values], 'expected': result})
        yield document('python-aggregation', 'sum:'+key,
            'Task: Add the integers in a Python list.\nPython:\n'
            'def solve(values):\n    return sum(values)\n\n'
            f'assert solve({values!r}) == {sum(values)}\n', 3,
            {'function': 'solve', 'arguments': [values], 'expected': sum(values)})
