"""Talks to the SentimentRegistry contract: sign + send publishBatch with the backend's
burner wallet, and read what is already on-chain."""
import json
import os

from web3 import Web3

import config


class Chain:
    def __init__(self, w3, contract_address, private_key, abi=None):
        if abi is None:
            with open(os.path.join(config.HERE, "abi.json")) as f:
                abi = json.load(f)
        self.w3 = w3
        self.account = w3.eth.account.from_key(private_key)
        self.contract = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)

    @classmethod
    def from_env(cls):
        missing = [n for n in ("RPC_URL", "PRIVATE_KEY", "CONTRACT_ADDRESS") if not getattr(config, n)]
        if missing:
            raise SystemExit(f"Missing in backend/.env: {', '.join(missing)}")
        w3 = Web3(Web3.HTTPProvider(config.RPC_URL, request_kwargs={"timeout": 30}))
        return cls(w3, config.CONTRACT_ADDRESS, config.PRIVATE_KEY)

    def tx_url(self, tx_hash):
        return f"{config.EXPLORER_URL}/tx/{tx_hash}"

    def chain_time(self):
        return int(self.w3.eth.get_block("latest")["timestamp"])

    def last_observed(self, token):
        """observedAt of the token's newest on-chain signal, or 0 if none."""
        if self.contract.functions.historyLength(token).call() == 0:
            return 0
        return int(self.contract.functions.latest(token).call()[3])

    def is_publisher(self):
        return self.contract.functions.isPublisher(self.account.address).call()

    def publish_batch(self, signals):
        """Write signals in ONE transaction and wait until it is mined.
        Returns (tx_hash, block_number)."""
        items = [(s["token"], s["score"], s["confidence"], s["source_count"],
                  s["observed_at"], Web3.to_bytes(hexstr=s["analysis_hash"])) for s in signals]
        fn = self.contract.functions.publishBatch(items)
        fn.call({"from": self.account.address})  # dry run: surfaces the revert reason early
        tx = fn.build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status != 1:
            raise RuntimeError(f"Transaction failed on-chain: {self.tx_url(self.w3.to_hex(tx_hash))}")
        return self.w3.to_hex(tx_hash), receipt.blockNumber
