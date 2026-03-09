const express = require("express");
const cors = require("cors");

const PORT = process.env.PORT || 3000;
const app = express();

app.use(cors());
app.use(express.json());

// In-memory store
const items = new Map();
let nextId = 1;

// Health check
app.get("/health", (_req, res) => {
  res.json({ status: "ok", items_count: items.size });
});

// List items
app.get("/items", (_req, res) => {
  res.json({ items: Array.from(items.values()) });
});

// Get item
app.get("/items/:id", (req, res) => {
  const item = items.get(req.params.id);
  if (!item) return res.status(404).json({ error: "Item not found" });
  res.json(item);
});

// Create item
app.post("/items", (req, res) => {
  const { name, description = "", price = 0 } = req.body;
  if (!name) return res.status(400).json({ error: "Name is required" });

  const id = String(nextId++);
  const item = { id, name, description, price };
  items.set(id, item);
  console.log(`Created item ${id}: ${name}`);
  res.status(201).json(item);
});

// Delete item
app.delete("/items/:id", (req, res) => {
  if (!items.has(req.params.id))
    return res.status(404).json({ error: "Item not found" });

  items.delete(req.params.id);
  console.log(`Deleted item ${req.params.id}`);
  res.json({ deleted: req.params.id });
});

app.listen(PORT, () => {
  console.log(`Express API listening on port ${PORT}`);
});
