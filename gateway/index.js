const express = require('express');
const axios = require('axios');
const cors = require('cors');

const app = express();
app.use(cors());
app.use(express.json());

// ✅ 5-node cluster
// Use host.docker.internal to reach localhost services from inside Docker container
// For local dev: host.docker.internal:3001-3005
// For Docker Compose: replica, replica1, replica2, replica3, replica4
const replicas = (process.env.REPLICAS || 'http://host.docker.internal:3001,http://host.docker.internal:3002,http://host.docker.internal:3003,http://host.docker.internal:3004,http://host.docker.internal:3005').split(',');

let currentLeader = replicas[0];

// ===============================
// 🔍 DISCOVER LEADER
// ===============================
async function discoverLeader() {
  console.log("🔍 Discovering leader...");

  for (let replica of replicas) {
    try {
      const res = await axios.get(`${replica}/state`, { timeout: 3000 });

      if (res.data.state === "leader") {
        currentLeader = replica;
        console.log("✅ Leader found:", currentLeader);
        return currentLeader;
      }

    } catch (err) {
      console.log(`❌ ${replica} not reachable:`, err.message);
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
      const r = await axios.get(`${replica}/status`, { timeout: 3000 });
      console.log(`✅ ${replica} responded:`, r.data);

      status.push({
        replica,
        status: "UP",
        ...r.data
      });

    } catch (err) {
      console.log(`⚠️ ${replica} /status failed:`, err.message);
      status.push({
        replica,
        status: "DOWN"
      });
    }
  }

  console.log("Final status:", status);
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