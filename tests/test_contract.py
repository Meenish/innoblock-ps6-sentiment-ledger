import json, time
from web3 import Web3, EthereumTesterProvider
from web3.exceptions import ContractLogicError
from eth_tester.exceptions import TransactionFailed
ERR=(ContractLogicError,TransactionFailed)
b=json.load(open(__import__('os').path.join(__import__('os').path.dirname(__file__),'build.json')))
w3=Web3(EthereumTesterProvider())
owner, backend, rando = w3.eth.accounts[:3]
tx=w3.eth.contract(abi=b['abi'],bytecode=b['bytecode']).constructor().transact({'from':owner})
addr=w3.eth.get_transaction_receipt(tx).contractAddress
c=w3.eth.contract(address=addr,abi=b['abi'])
now=w3.eth.get_block('latest').timestamp
H=Web3.keccak(text='analysis')
def S(tok,score,conf,n,t): return (tok,score,conf,n,t,H)
def expect_revert(fn,msg,frm=backend):
    try: fn.transact({'from':frm}); print('FAIL no revert:',msg)
    except ERR as e: assert msg in str(e),(msg,str(e)); print('ok revert:',msg)

expect_revert(c.functions.publish(S('BTC',50,80,3,now-100)),'not an authorized publisher')
c.functions.setPublisher(backend,True).transact({'from':owner})
expect_revert(c.functions.setPublisher(rando,True),'not owner',frm=rando)

r=w3.eth.get_transaction_receipt(c.functions.publishBatch([S('BTC',68,89,5,now-7200),S('ETH',-5,70,4,now-7200),S('SOL',-40,75,6,now-7200)]).transact({'from':backend}))
print('batch gas',r.gasUsed)
r1=w3.eth.get_transaction_receipt(c.functions.publish(S('BTC',75,91,14,now-3600)).transact({'from':backend}))
print('single gas',r1.gasUsed)
ev=c.events.SignalPublished().process_receipt(r1)[0].args
print('event',ev.token,ev.index,ev.score,ev.sourceCount)

print('tokens',c.functions.getTokens().call())
print('latest BTC',c.functions.latest('BTC').call())
print('history BTC',c.functions.getHistory('BTC',0,10).call())
print('page past end',c.functions.getHistory('BTC',5,10).call())
print('classify',[c.functions.classify(x).call() for x in (20,19,-19,-20,100,-100,0)])
print('total',c.functions.totalSignals().call())

for args,msg in [(S('BTC',101,50,1,now),'score out of range'),(S('BTC',-101,50,1,now),'score out of range'),
 (S('BTC',10,101,1,now),'confidence out of range'),(S('BTC',10,50,0,now),'no sources'),
 (S('btc',10,50,1,now),'token must be A-Z/0-9'),(S('',10,50,1,now),'token length 1-10'),
 (S('ABCDEFGHIJK',10,50,1,now),'token length 1-10'),(S('BTC',10,50,1,now+10**6),'bad observedAt'),
 (S('BTC',10,50,1,now-3600),'observedAt not newer than last')]:
    expect_revert(c.functions.publish(args),msg)
expect_revert(c.functions.publishBatch([]),'batch size 1-20')
try: c.functions.latest('DOGE').call(); print('FAIL')
except ERR as e: print('ok revert: no signals' if 'no signals' in str(e) else e)
# revoke
c.functions.setPublisher(backend,False).transact({'from':owner})
expect_revert(c.functions.publish(S('BTC',10,50,1,now)),'not an authorized publisher')
