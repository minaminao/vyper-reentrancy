import csv
import os
from itertools import cycle
from pathlib import Path
import re

import requests

VULNERABLE_VERSIONS = {"0.2.15", "0.2.16", "0.3.0"}
ETHERSCAN_API_URLS = {
    "arb": "https://api.arbiscan.io/api",
    "avax": "https://api.snowtrace.io/api",
    "celo": "https://api.celoscan.io/api",
    "ethereum": "https://api.etherscan.io/api",
    "ftm": "https://api.ftmscan.com/api",
    "gnosis": "https://api.gnosisscan.io/api",
    "moonbeam": "https://api-moonbeam.moonscan.io/api",
    "op": "https://api-optimistic.etherscan.io/api",
    "poly": "https://api.polygonscan.com/api",
}
ETHERSCAN_API_VARS = {
    "arb": "ARBISCAN_API_KEY",
    "avax": "SNOWTRACE_API_KEY",
    "celo": "CELOSCAN_API_KEY",
    "ethereum": "ETHERSCAN_API_KEY",
    "ftm": "FTMSCAN_API_KEY",
    "gnosis": "GNOSISSCAN_API_KEY",
    "moonbeam": "MOONSCAN_API_KEY",
    "op": "OPTIMISTIC_ETHERSCAN_API_KEY",
    "poly": "POLYGONSCAN_API_KEY",
}
api_keys = {
    network: cycle(os.environ[key].split(","))
    for network, key in ETHERSCAN_API_VARS.items()
}


def get_source(network, address):
    params = {
        "module": "contract",
        "action": "getsourcecode",
        "address": address,
        "apikey": next(api_keys[network]),
    }
    resp = requests.get(ETHERSCAN_API_URLS[network], params=params)
    resp.raise_for_status()
    return resp.json()


def find_closing_paren(text):
    stack = []
    slices = []
    for i, char in enumerate(text):
        if char == "(":
            stack.append(i)
        if char == ")":
            slices.append(slice(stack.pop(), i + 1))
            if not stack:
                return text[slices[-1]]


def could_be_vulnerable(source):
    if "@payable" in source:
        print('has payable')
        return True

    if "raw_call" in source:
        vulnerable_calls = []

        for match in re.finditer("raw_call", source):
            inner = find_closing_paren(source[match.start() :])
            print(inner)
            safe_calls = [
                "transfer(address,uint256)",
                "transferFrom(address,address,uint256)",
                "approve(address,uint256)",
            ]
            if not any(call in inner for call in safe_calls):
                print('no safe call', inner)
                vulnerable_calls.append(inner)

        return bool(vulnerable_calls)
    else:
        return False


def main():
    contracts_dir = Path("contracts")
    contracts_dir.mkdir(exist_ok=True)

    for network in ETHERSCAN_API_URLS:
        network_dir = contracts_dir / network
        network_dir.mkdir(exist_ok=True)
        reader = csv.reader(open(f"etherscan-export/{network}.csv"))

        for address, version in reader:
            if version not in VULNERABLE_VERSIONS:
                continue

            contract_path = network_dir / f"{address}.vy"
            if contract_path.exists():
                source = contract_path.read_text()
                if not could_be_vulnerable(source):
                    print('narrowed down to non vulnerable')
                    contract_path.unlink()
                continue

            print(network, address, version)
            resp = get_source(network, address)
            source = resp["result"][0]["SourceCode"]
            version = resp["result"][0]["CompilerVersion"].split(":")[-1]

            if could_be_vulnerable(source):
                contract_path.write_text(source)
                print("could be vulnerable, saved")
            else:
                print("contract looks safe")


if __name__ == "__main__":
    main()
