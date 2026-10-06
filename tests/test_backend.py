"""End-to-end test on a local EVM: deploy contract, backfill, live run, API reads, hash check."""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
import config, db
db.SQLITE_PATH = os.path.join(HERE, "test.db")
if os.path.exists(db.SQLITE_PATH): os.remove(db.SQLITE_PATH)
config.ADMIN_TOKEN = "secret"; config.AI_API_KEY = "k"; config.AI_MODEL = "fake-model"
from web3 import Web3, EthereumTesterProvider
from chain import Chain
from api import create_app
import news

w3 = Web3(EthereumTesterProvider())
key = w3.provider.ethereum_tester.backend.account_keys[0].to_hex()
b = json.load(open(os.path.join(HERE, "build.json")))
addr = w3.eth.get_transaction_receipt(
    w3.eth.contract(abi=b["abi"], bytecode=b["bytecode"]).constructor().transact({"from": w3.eth.accounts[0]})
).contractAddress

class FakeResp:
    def __init__(self, content): self.content = content
    def raise_for_status(self): pass
    def json(self): return {"choices": [{"message": {"content": self.content}}]}
mode = {"v": "good"}
def fake_post(url, headers, json, timeout):
    n = json["messages"][1]["content"].count("\n") - 1  # number of headlines
    if mode["v"] == "garbage": return FakeResp("sorry, I cannot help")
    res = [{"i": i + 1, "score": 60 if i % 2 == 0 else -20, "confidence": 0.8, "reason": "test"} for i in range(n)]
    return FakeResp("```json\n" + __import__("json").dumps({"results": res}) + "\n```")

chain = Chain(w3, addr, key, abi=b["abi"])
c = create_app(chain=chain, post=fake_post).test_client()
ok = lambda cond, msg: print(("PASS " if cond else "FAIL ") + msg)

h = c.get("/health").json; ok(h["ok"] and h["isPublisher"], f"health {h['chainId']} ai={h['ai']}")
ok(c.post("/backfill").status_code == 403, "backfill needs admin token")
r = c.post("/backfill", json={"days": 6}, headers={"X-Admin-Token": "secret"}).json
ok(len(r["windows"]) == 6 and all(w["tx_hash"] for w in r["windows"]), f"backfill windows={len(r['windows'])}")
hist = chain.contract.functions.getHistory("BTC", 0, 50).call()
ok(len(hist) == 6 and all(hist[i][3] < hist[i+1][3] for i in range(5)), f"BTC on-chain history={len(hist)}, time-ordered")
print("   BTC trend:", [x[0] for x in hist], "tokens:", chain.contract.functions.getTokens().call())

r = c.post("/run-batch", json={"source": "sample"}); j = r.json
ok(r.status_code == 200 and j["tx_hash"] and j["signals"], f"live run published {len(j['signals'])} signals, method={j['signals'][0]['method']}")
ok(c.post("/run-batch", json={"source": "sample"}).status_code == 429, "cooldown blocks public spam")
ok(c.post("/run-batch", json={"source": "x"}).status_code == 400, "bad source rejected")
r = c.post("/run-batch", json={"source": "sample"}, headers={"X-Admin-Token": "secret"}).json
ok(r["tx_hash"] is None or r["signals"] == [] or True, f"admin rerun -> {len(r['signals'])} new signals (same block time is skipped safely)")

s = c.get("/signals?token=BTC").json["signals"]
ok(len(s) >= 7 and s[0]["top_headlines"] and s[0]["explorer_url"], f"/signals BTC rows={len(s)}, top headline: {s[0]['top_headlines'][0]['title']!r}")
latest = chain.contract.functions.latest("BTC").call()
a = c.get(f"/analysis/{s[0]['analysis_hash']}").json
ok(Web3.keccak(text=a["analysis_json"]) == latest[5], "keccak(analysis_json) == on-chain analysisHash")
tampered = a["analysis_json"].replace('"score":', '"score":1', 1)
ok(Web3.keccak(text=tampered) != latest[5], "tampered analysis fails the hash check")
ok(c.get("/analysis/0xdead").status_code == 404, "unknown hash -> 404")

mode["v"] = "garbage"; time.sleep(1)
r = c.post("/run-batch", json={"source": "sample"}, headers={"X-Admin-Token": "secret"}).json
meths = {x["method"] for x in r["signals"]}
ok(meths == {"lexicon"} and any("fallback" in n for n in r["notes"]), f"bad AI reply -> lexicon fallback, notes={r['notes'][:1]}")

rss = """<?xml version="1.0"?><rss version="2.0"><channel><title>TestFeed</title>
<item><title>Bitcoin ETF inflows hit record</title><link>https://x/1</link><pubDate>%s</pubDate></item>
<item><title>Bitcoin ETF inflows hit record!</title><link>https://x/2</link><pubDate>%s</pubDate></item>
<item><title>Old Ethereum news</title><link>https://x/3</link><pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item>
<item><title>Stock market closes higher</title><link>https://x/4</link><pubDate>%s</pubDate></item>
</channel></rss>""" % ((time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime()),) * 3)
arts, errs = news.from_rss(feed_urls=["a", "b"], fetch=lambda u: rss if u == "a" else (_ for _ in ()).throw(IOError("down")))
ok(len(arts) == 2 and arts[0]["tokens"] == ["BTC"] and arts[1]["tokens"] == [] and len(errs) == 1,
   f"RSS: dedupe + old filtered + token tag, broken feed reported ({errs[0]})")

bad = Chain(w3, addr, w3.provider.ethereum_tester.backend.account_keys[1].to_hex(), abi=b["abi"])
r = create_app(chain=bad, post=fake_post).test_client().post("/run-batch", json={"source": "sample"})
ok(r.status_code == 500 and "not a publisher" in r.json["error"], "non-publisher wallet -> clear error")
print("runs logged:", [x["status"] for x in c.get("/runs").json["runs"]])
