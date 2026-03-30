const express = require('express');
const axios = require('axios');

const app = express();
app.use(express.json());

// ✅ 5-node cluster
const replicas = [
  'http://replica:3001',   // leader node (initial)
  'http://replica1:3002',
  'http://replica2:3003',
  'http://replica3:3004',
  'http://replica4:3005'
];

let currentLeader = replicas[0];

// ===============================
// 🔍 DISCOVER LEADER
// ===============================
async function discoverLeader() {
  console.log("🔍 Discovering leader...");

  for (let replica of replicas) {
    try {
      const res = await axios.get(`${replica}/state`, { timeout: 1000 });

      if (res.data.state === "leader") {
        currentLeader = replica;
        console.log("✅ Leader found:", currentLeader);
        return currentLeader;
      }

    } catch (err) {
      console.log(`❌ ${replica} not reachable`);
    }
  }

  console.log("⚠️ No leader found");
  return null;
}

// ===============================
// 📊 CLUSTER STATUS
// ===============================
app.get('/cluster-status', async (req, res) => {
  await discoverLeader();

  const status = [];

  for (let replica of replicas) {
    try {
      const r = await axios.get(`${replica}/status`, { timeout: 1000 });

      status.push({
        replica,
        ...r.data
      });

    } catch {
      status.push({
        replica,
        status: "DOWN"
      });
    }
  }

  res.json({
    timestamp: new Date(),
    leader: currentLeader,
    totalNodes: replicas.length,
    replicas: status
  });
});

// ===============================
// 📡 CLIENT REQUEST → LEADER
// ===============================
app.post('/send', async (req, res) => {
  let attempts = 3;

  while (attempts > 0) {
    try {
      console.log(`➡️ Sending to leader: ${currentLeader}`);

      await axios.post(`${currentLeader}/client_request`, req.body, { timeout: 1000 });

      return res.send("✅ Sent to leader");

    } catch (err) {
      console.log("⚠️ Leader failed, rediscovering...");
      await discoverLeader();
      attempts--;
    }
  }

  res.status(500).send("❌ No leader available");
});

// ===============================
// ❤️ HEALTH CHECK
// ===============================
app.get('/health', (req, res) => {
  res.send("Gateway OK");
});

// ===============================
app.listen(3000, () => {
  console.log("🚀 Gateway running on 3000");
});