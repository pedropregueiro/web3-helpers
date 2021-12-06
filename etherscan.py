import os

import requests

ETHERNET_API_KEY = os.environ.get("ETHERNET_API_KEY")
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")

ETHERSCAN_BASE_URL = 'https://api.etherscan.io/api'
POLYGON_BASE_URL = 'https://api.polygonscan.com/api'

CHAINS = {
    "eth": {"url": ETHERSCAN_BASE_URL, "api_key": ETHERNET_API_KEY},
    "polygon": {"url": POLYGON_BASE_URL, "api_key": POLYGON_API_KEY}
}


def get_token_supply(contract_address, chain="eth"):
    query_params = {
        "module": "token",
        "action": "tokeninfo",
        "contractaddress": contract_address,
        "apikey": CHAINS[chain].get("api_key")
    }

    response = requests.get(CHAINS[chain].get("url"), data=query_params)
    return response.json()


def get_contract_abi(contract_address, chain="eth"):
    query_params = {
        "module": "contract",
        "action": "getabi",
        "address": contract_address,
        "apikey": CHAINS[chain].get("api_key")
    }

    abi = requests.get(CHAINS[chain].get("url"), data=query_params).json().get('result')
    return abi
