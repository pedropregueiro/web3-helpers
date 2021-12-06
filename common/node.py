import json
import os
from functools import lru_cache

from dotenv import load_dotenv
from ens import ENS
from hexbytes import HexBytes
from web3 import Web3
from web3._utils.contracts import find_matching_event_abi
from web3._utils.events import get_event_data
from web3._utils.filters import construct_event_filter_params

from .etherscan import get_contract_abi

load_dotenv()

CONTRACTS_STORAGE_PATH = os.path.join(os.getcwd(), "data", "contracts")

MAINNET_HTTP_PROVIDER_URL = os.getenv("MAINNET_HTTP_PROVIDER_URL")
MAINNET_WS_PROVIDER_URL = os.getenv("MAINNET_WS_PROVIDER_URL")

POLYGON_HTTP_PROVIDER_URL = os.getenv("POLYGON_HTTP_PROVIDER_URL")
POLYGON_WS_PROVIDER_URL = os.getenv("POLYGON_WS_PROVIDER_URL")

CHAIN_ENDPOINTS = {
    "eth": MAINNET_HTTP_PROVIDER_URL,
    "polygon": POLYGON_HTTP_PROVIDER_URL,
}

CHAIN_WEBSOCKET_ENDPOINTS = {
    "eth": MAINNET_WS_PROVIDER_URL,
    "polygon": POLYGON_WS_PROVIDER_URL
}


@lru_cache
def fetch_curated_contracts():
    with open("curated.json") as f:
        curated_contracts = json.loads(f.read())
    return curated_contracts


def web3_client(chain="eth", provider="http"):
    if provider and provider == "websocket":
        return Web3(Web3.WebsocketProvider(CHAIN_WEBSOCKET_ENDPOINTS[chain]))
    return Web3(Web3.HTTPProvider(CHAIN_ENDPOINTS[chain]))


def ns_client(chain="eth"):
    return ENS.fromWeb3(web3_client(chain))


def checksum_address(address, chain="eth"):
    return web3_client(chain).toChecksumAddress(address)


def get_balance(address, chain="eth"):
    return web3_client(chain=chain).eth.get_balance(address)


def get_ens_domain_for_address(address, chain="eth"):
    ens_name = None
    try:
        ens_name = ns_client(chain).name(address)
    except Exception as e:
        pass
    return ens_name


def get_current_gas_price(chain="eth"):
    return web3_client(chain).eth.gas_price


def fetch_contract_abi(contract_address):
    path = os.path.join(CONTRACTS_STORAGE_PATH, f"{contract_address}.abi")
    if os.path.isfile(path):
        with open(path, "r") as f:
            return f.read()

    return None


def store_contract_abi(contract_address, contract_abi):
    path = os.path.join(CONTRACTS_STORAGE_PATH, f"{contract_address}.abi")
    if not os.path.isfile(path):
        with open(path, "x") as f:
            f.write(contract_abi)


def get_contract(contract_address, chain="eth", provider="http"):
    contract_address = checksum_address(contract_address, chain=chain)
    contract_abi = fetch_contract_abi(contract_address)
    if not contract_abi:
        print(f"fetching contract {contract_address} for the first time")
        contract_abi = get_contract_abi(contract_address, chain=chain)
        store_contract_abi(contract_address, contract_abi)

    contract = web3_client(chain=chain, provider=provider).eth.contract(address=contract_address,
                                                                        abi=json.loads(contract_abi))
    return contract


def get_transaction(address, chain="eth"):
    return web3_client(chain).eth.get_transaction(HexBytes(address))


def get_block(block_number, chain="eth"):
    return web3_client(chain).eth.get_block(block_number)


def get_latest_block_number(chain="eth"):
    return web3_client(chain).eth.block_number


def get_transaction_receipt(address, chain="eth"):
    return web3_client(chain).eth.get_transaction_receipt(HexBytes(address))


def decode_contract_transaction(transaction_address, chain="eth"):
    transaction = web3_client(chain).eth.get_transaction(HexBytes(transaction_address))

    contract_address = transaction.get('to')
    print(f"decoding transaction. hash: {transaction_address} | contract: {contract_address}")

    contract = get_contract(contract_address)

    try:
        func_obj, func_params = contract.decode_function_input(transaction.input)
        return func_obj, func_params
    except Exception as e:
        print(f"exception decoding function: {e}")
        raise e


def get_events(contract_address, event_name='Transfer', token_id=None, start_block=0, end_block="latest",
               chain="eth", topics=None):
    codec = web3_client(chain).codec
    contract_address = checksum_address(contract_address)
    contract = get_contract(contract_address)
    event_abi = find_matching_event_abi(contract.abi, event_name)

    argument_filters = {"address": contract_address}
    if token_id:
        argument_filters["tokenId"] = token_id

    if topics:
        for index, topic in enumerate(topics):
            if topic:
                argument_filters[f"topic{index}"] = topic

    if start_block < 0:
        latest_block = get_latest_block_number(chain=chain)
        start_block = latest_block + start_block

    data_filter_set, event_filter_params = construct_event_filter_params(
        event_abi,
        codec,
        address=argument_filters.get("address"),
        argument_filters=argument_filters,
        fromBlock=start_block,
        toBlock=end_block
    )

    print("Querying eth_getLogs with the following parameters:", event_filter_params)
    logs = web3_client(chain).eth.get_logs(event_filter_params)

    all_events = []
    for log in logs:
        evt = get_event_data(codec, event_abi, log)
        all_events.append(evt)

    return all_events


def get_nft_holdings(wallet_address, contract_address, contract_metadata=None):
    wallet_address = checksum_address(wallet_address)

    contract_address = checksum_address(contract_address)
    contract = get_contract(contract_address)

    if not contract_metadata:
        raise Exception("kinda need some metadata here")

    symbol = contract_metadata.get('symbol')
    name = contract_metadata.get('name')
    balance = contract.functions.balanceOf(wallet_address).call()

    if balance <= 0:
        return None

    return {**contract_metadata, **{"balance": balance, "symbol": symbol, "name": name,
                                    "address": contract_address}}


def get_curated_nfts_holdings(wallet_address, include_batch=False):
    wallet_address = checksum_address(wallet_address)
    holdings = []

    curated_contracts = fetch_curated_contracts()
    for contract_address, contract_metadata in curated_contracts.items():
        contract_address = checksum_address(contract_address)
        contract = get_contract(contract_address)
        symbol = contract_metadata.get('symbol')
        name = contract_metadata.get('name')

        if 'fetch_batch' in contract_metadata and contract_metadata['fetch_batch'] is True:
            if not include_batch:
                continue

            try:
                # Some NFT projects need some extra love
                total_supply = contract_metadata.get('total_supply')
                total = [wallet_address] * total_supply
                token_ids = list(range(total_supply))
                balance = contract.functions.balanceOfBatch(total, token_ids).call().count(1)
            except Exception as e:
                balance = 0
                print(f"problems fetching contract balance: {contract_address}. moving along...")
        else:
            balance = contract.functions.balanceOf(wallet_address).call()

        if balance > 0:
            holdings.append({**contract_metadata, **{"balance": balance, "symbol": symbol, "name": name,
                                                     "address": contract_address}})

    return holdings
