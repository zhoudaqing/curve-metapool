import pytest
from eth_tester import EthereumTester, PyEVMBackend
from web3 import Web3
from os.path import realpath, dirname, join
from .deploy import deploy_contract

CONTRACT_PATH = join(dirname(dirname(realpath(__file__))), 'vyper')
N_COINS = 2
UP = [18, 6]
UU = [10 ** p for p in UP]
c_rates = [5 * UU[0], UU[1]]
use_lending = [True, True]
tethered = [False, False]
PRECISIONS = [10 ** 18 // u for u in UU]
MAX_UINT = 2 ** 256 - 1


@pytest.fixture
def tester():
    genesis_params = PyEVMBackend._generate_genesis_params(overrides={'gas_limit': 7 * 10 ** 6})
    pyevm_backend = PyEVMBackend(genesis_parameters=genesis_params)
    pyevm_backend.reset_to_genesis(genesis_params=genesis_params, num_accounts=10)
    return EthereumTester(backend=pyevm_backend, auto_mine_transactions=True)


@pytest.fixture
def w3(tester):
    w3 = Web3(Web3.EthereumTesterProvider(tester))
    w3.eth.setGasPriceStrategy(lambda web3, params: 0)
    w3.eth.defaultAccount = w3.eth.accounts[0]
    return w3


@pytest.fixture
def coins(w3):
    return [deploy_contract(
                w3, 'ERC20.vy', w3.eth.accounts[0],
                b'Coin ' + str(i).encode(), str(i).encode(), UP[i], 10 ** 12)
            for i in range(N_COINS)]


@pytest.fixture
def pool_token_internal(w3):
    return deploy_contract(w3, 'ERC20.vy', w3.eth.accounts[0],
                           b'Stableswap', b'STBL', 18, 0)


@pytest.fixture
def pool_token_meta(w3):
    return deploy_contract(w3, 'ERC20.vy', w3.eth.accounts[0],
                           b'Stableswap', b'STBL', 18, 0)


@pytest.fixture
def yerc20s(w3, coins):
    ccoins = [deploy_contract(
                w3, 'fake_yerc20.vy', w3.eth.accounts[0],
                b'C-Coin ' + str(i).encode(), b'c' + str(i).encode(),
                18, 0, coins[i].address, c_rates[i])
              for i in range(N_COINS)]
    for t, c, u in zip(coins, ccoins, UU):
        t.functions.transfer(c.address, 10 ** 11 * u)\
                .transact({'from': w3.eth.accounts[0]})
    for i, l in enumerate(use_lending):
        if not l:
            ccoins[i] = coins[i]
    return ccoins


@pytest.fixture(scope='function')
def internal_swap(w3, coins, yerc20s, pool_token_internal):
    swap_contract = deploy_contract(
            w3, ['stableswap.vy', 'ERC20m.vy', 'yERC20.vy'], w3.eth.accounts[1],
            [c.address for c in yerc20s], [c.address for c in coins],
            pool_token_internal.address, 1000, 10 ** 7,
            replacements={
                '___N_COINS___': str(N_COINS),
                '___N_ZEROS___': '[' + ', '.join(['ZERO256'] * N_COINS) + ']',
                '___PRECISION_MUL___': '[' + ', '.join(
                    'convert(%s, uint256)' % i for i in PRECISIONS) + ']',
                '___USE_LENDING___': '[' + ', '.join(
                        str(i) for i in use_lending) + ']',
                '___TETHERED___': '[' + ', '.join(
                        str(i) for i in tethered) + ']',
            })
    pool_token_internal.functions.set_minter(swap_contract.address).transact()
    return swap_contract


def approx(a, b, precision=1e-10):
    return 2 * abs(a - b) / (a + b) <= precision
