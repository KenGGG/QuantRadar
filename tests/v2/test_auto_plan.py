import pytest
from quantradar2.auto_plan import resolve_requirements

SOURCE = '''
def initialize(context):
    context.pool = ['512890.XSHG', '159949.XSHE', '513100.XSHG', '518880.XSHG']
    context.params = dict(bias_n=60, momentum_n=25, slope_n=25)
    context.params.update(extras)
def rebalance(context):
    p = context.params
    count = max(p['bias_n'] + p['momentum_n'] - 1, p['slope_n'])
    for security in context.pool:
        attribute_history(security, count, '1d', ['close'])
'''

def test_imported_strategy_and_parameter_override_without_source_changes():
    before = SOURCE
    plan, origin = resolve_requirements(SOURCE)
    assert origin == 'automatic' and plan['warmup_bars'] == 84
    assert plan['securities'] == ['159949.XSHE','512890.XSHG','513100.XSHG','518880.XSHG']
    assert resolve_requirements(SOURCE, extras={'bias_n':120,'momentum_n':35})[0]['warmup_bars']==154
    assert SOURCE == before

def test_opaque_count_is_conservative_and_never_executes_code(tmp_path):
    marker = tmp_path/'must-not-exist'
    source = f"get_price('510300.XSHG', count=__import__('pathlib').Path({str(marker)!r}).touch())"
    assert resolve_requirements(source)[0]['warmup_bars']==5000
    assert not marker.exists()

def test_literals_aliases_and_explicit_backward_compatibility():
    source="g.window = 120\nx = g.window + 5\nattribute_history('510300.SH', x, '1d')"
    assert resolve_requirements(source)[0]=={'securities':['510300.XSHG'],'warmup_bars':125}
    explicit={'securities':['600519.XSHG'],'warmup_bars':60}
    assert resolve_requirements(source,explicit)==(explicit,'declared')
    assert resolve_requirements('DATA_REQUIREMENTS: dict = '+repr(explicit))==(explicit,'declared')
    with pytest.raises(ValueError):resolve_requirements(source,{})

def test_ambiguous_counts_use_maximum_supported_window():
    source="n=20\nn=100\nhistory(n, security_list=['510300.XSHG'])"
    assert resolve_requirements(source)[0]['warmup_bars']==5000

def test_extras_security_pool_and_unsupported_range():
    assert resolve_requirements('pass',extras={'pool':['510300.XSHG']})[0]['securities']==['510300.XSHG']
    with pytest.raises(ValueError):resolve_requirements("get_price('510300.XSHG',count=5001)")
    with pytest.raises(ValueError, match='get_index_stocks'):
        resolve_requirements("pool=get_index_stocks('000300.XSHG')",benchmark='000300.XSHG')
