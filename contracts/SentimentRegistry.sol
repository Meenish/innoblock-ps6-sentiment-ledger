// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title SentimentRegistry
/// @notice Public, timestamped log of AI-generated crypto sentiment signals.
///         Each signal = one token's aggregated sentiment for one news window.
///         Full headlines and AI explanations live off-chain; `analysisHash`
///         (keccak256 of that off-chain analysis) lets anyone check it later.
/// @dev    The chain proves WHAT was published and WHEN. It does not prove the
///         AI was right.
contract SentimentRegistry {
    // ------------------------------------------------------------------ types

    struct Signal {
        int16 score;          // -100 (strongly bearish) .. +100 (strongly bullish)
        uint8 confidence;     // 0 .. 100 (%)
        uint16 sourceCount;   // number of distinct headlines/sources aggregated
        uint64 observedAt;    // end of the news window analysed (unix seconds)
        uint64 recordedAt;    // block time when written on-chain
        bytes32 analysisHash; // keccak256 of the off-chain analysis JSON
    }

    /// Input shape for publish/publishBatch
    struct SignalInput {
        string token;         // "BTC", "ETH" ... (A-Z, 0-9, 1-10 chars)
        int16 score;
        uint8 confidence;
        uint16 sourceCount;
        uint64 observedAt;
        bytes32 analysisHash;
    }

    // ---------------------------------------------------------------- storage

    /// Scores at or above this are "BULLISH", at or below -this are "BEARISH"
    int16 public constant CLASS_THRESHOLD = 20;

    address public owner;
    mapping(address => bool) public isPublisher;

    /// token symbol => full history (oldest first)
    mapping(string => Signal[]) private history;
    /// every token that has at least one signal
    string[] private tokens;

    uint256 public totalSignals;

    // ----------------------------------------------------------------- events

    event SignalPublished(
        string indexed tokenTopic, // indexed copy for filtering logs
        string token,
        uint256 index,             // position in that token's history
        int16 score,
        uint8 confidence,
        uint16 sourceCount,
        uint64 observedAt,
        bytes32 analysisHash,
        address publisher
    );
    event PublisherSet(address indexed account, bool allowed);
    event OwnershipTransferred(address indexed from, address indexed to);

    // -------------------------------------------------------------- modifiers

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    modifier onlyPublisher() {
        require(isPublisher[msg.sender], "not an authorized publisher");
        _;
    }

    /// The deployer is the owner and the first publisher
    constructor() {
        owner = msg.sender;
        isPublisher[msg.sender] = true;
        emit OwnershipTransferred(address(0), msg.sender);
        emit PublisherSet(msg.sender, true);
    }

    // ------------------------------------------------------------ admin (owner)

    /// Allow or revoke a wallet (e.g. the backend's) to publish signals
    function setPublisher(address account, bool allowed) external onlyOwner {
        require(account != address(0), "zero address");
        isPublisher[account] = allowed;
        emit PublisherSet(account, allowed);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "zero address");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    // ------------------------------------------------------------- publishing

    /// Publish one token's signal
    function publish(SignalInput calldata s) external onlyPublisher {
        _record(s);
    }

    /// Publish several tokens' signals in one transaction (cheaper per signal)
    function publishBatch(SignalInput[] calldata items) external onlyPublisher {
        require(items.length > 0 && items.length <= 20, "batch size 1-20");
        for (uint256 i = 0; i < items.length; i++) {
            _record(items[i]);
        }
    }

    function _record(SignalInput calldata s) private {
        _requireValidToken(s.token);
        require(s.score >= -100 && s.score <= 100, "score out of range");
        require(s.confidence <= 100, "confidence out of range");
        require(s.sourceCount > 0, "no sources");
        require(s.observedAt > 0 && s.observedAt <= block.timestamp, "bad observedAt");

        Signal[] storage h = history[s.token];
        // keep each token's history in time order
        if (h.length > 0) {
            require(s.observedAt > h[h.length - 1].observedAt, "observedAt not newer than last");
        } else {
            tokens.push(s.token);
        }

        h.push(Signal({
            score: s.score,
            confidence: s.confidence,
            sourceCount: s.sourceCount,
            observedAt: s.observedAt,
            recordedAt: uint64(block.timestamp),
            analysisHash: s.analysisHash
        }));
        totalSignals++;

        emit SignalPublished(
            s.token, s.token, h.length - 1, s.score, s.confidence,
            s.sourceCount, s.observedAt, s.analysisHash, msg.sender
        );
    }

    /// Token symbols: 1-10 chars, uppercase letters and digits only
    function _requireValidToken(string calldata token) private pure {
        bytes calldata b = bytes(token);
        require(b.length >= 1 && b.length <= 10, "token length 1-10");
        for (uint256 i = 0; i < b.length; i++) {
            bytes1 c = b[i];
            require((c >= "A" && c <= "Z") || (c >= "0" && c <= "9"), "token must be A-Z/0-9");
        }
    }

    // ------------------------------------------------------- reading (free)

    function getTokens() external view returns (string[] memory) {
        return tokens;
    }

    function historyLength(string calldata token) external view returns (uint256) {
        return history[token].length;
    }

    /// Most recent signal for a token (reverts if none)
    function latest(string calldata token) external view returns (Signal memory) {
        Signal[] storage h = history[token];
        require(h.length > 0, "no signals for token");
        return h[h.length - 1];
    }

    /// Page through a token's history: `count` items starting at `start`
    function getHistory(string calldata token, uint256 start, uint256 count)
        external view returns (Signal[] memory page)
    {
        Signal[] storage h = history[token];
        if (start >= h.length) return new Signal[](0);
        uint256 end = start + count;
        if (end > h.length) end = h.length;
        page = new Signal[](end - start);
        for (uint256 i = start; i < end; i++) {
            page[i - start] = h[i];
        }
    }

    /// "BULLISH" / "BEARISH" / "NEUTRAL" from a score, same rule for everyone
    function classify(int16 score) public pure returns (string memory) {
        if (score >= CLASS_THRESHOLD) return "BULLISH";
        if (score <= -CLASS_THRESHOLD) return "BEARISH";
        return "NEUTRAL";
    }
}
