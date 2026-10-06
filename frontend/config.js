// =====================================================================
//  The only frontend file you need to edit.
//  Everything here is PUBLIC: never put keys or secrets in the frontend.
// =====================================================================
const CONFIG = {
  CONTRACT_ADDRESS: "0x119cC959d84C882893468134eC0F5b78f571EF5B",
  // Backend: localhost while building, your https Render URL once deployed
  BACKEND_URL: "http://localhost:5000",

  CHAIN_ID: 11155111,
  CHAIN_NAME: "Ethereum Sepolia",
  RPC_URL: "https://ethereum-sepolia-rpc.publicnode.com",
  EXPLORER: "https://sepolia.etherscan.io",
  CURRENCY: "ETH",

  // Tokens on-chain that the dashboard should not show (e.g. our Remix test entry)
  HIDDEN_TOKENS: ["TEST"],
  // Same rule as the contract's classify(): >= 20 bullish, <= -20 bearish
  THRESHOLD: 20,
};

const CONTRACT_ABI = [
  "function getTokens() view returns (string[])",
  "function historyLength(string token) view returns (uint256)",
  "function getHistory(string token, uint256 start, uint256 count) view returns (tuple(int16 score, uint8 confidence, uint16 sourceCount, uint64 observedAt, uint64 recordedAt, bytes32 analysisHash)[])",
  "function totalSignals() view returns (uint256)",
  "function isPublisher(address) view returns (bool)",
];
