const solc=require('solc'),fs=require('fs');
const src=fs.readFileSync('contracts/SentimentRegistry.sol','utf8');
const out=JSON.parse(solc.compile(JSON.stringify({language:'Solidity',sources:{'S.sol':{content:src}},
 settings:{optimizer:{enabled:false},evmVersion:'cancun',outputSelection:{'*':{'*':['abi','evm.bytecode.object']}}}})));
(out.errors||[]).forEach(e=>console.log(e.severity, e.formattedMessage.split('\n')[0]));
const c=out.contracts?.['S.sol']?.SentimentRegistry; if(!c) process.exit(1);
fs.writeFileSync('build.json',JSON.stringify({abi:c.abi,bytecode:c.evm.bytecode.object}));
fs.writeFileSync('abi.json',JSON.stringify(c.abi,null,2));
console.log('ok, bytecode bytes', c.evm.bytecode.object.length/2);
