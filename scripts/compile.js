const fs = require("fs");
const path = require("path");
const solc = require("solc");

const dir = path.join(__dirname, "..", "contracts");
const sources = {};
for (const f of ["EmissionTracker.sol", "CreditAuction.sol"]) {
  sources[f] = { content: fs.readFileSync(path.join(dir, f), "utf8") };
}
const input = {
  language: "Solidity",
  sources,
  settings: {
    optimizer: { enabled: true, runs: 200 },
    outputSelection: { "*": { "*": ["abi", "evm.bytecode.object", "evm.deployedBytecode.object"] } }
  }
};
const out = JSON.parse(solc.compile(JSON.stringify(input)));
if (out.errors) {
  const fatal = out.errors.filter(e => e.severity === "error");
  out.errors.forEach(e => console.error(e.formattedMessage));
  if (fatal.length) process.exit(1);
}
const artifacts = {};
for (const file of Object.keys(out.contracts)) {
  for (const name of Object.keys(out.contracts[file])) {
    const c = out.contracts[file][name];
    artifacts[name] = { abi: c.abi, bytecode: "0x" + c.evm.bytecode.object };
  }
}
fs.writeFileSync(path.join(__dirname, "..", "results", "artifacts.json"), JSON.stringify(artifacts));
console.log("compiled:", Object.keys(artifacts).join(", "));
