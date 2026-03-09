const { Client, GatewayIntentBits, REST, Routes, SlashCommandBuilder } = require("discord.js");

const TOKEN = process.env.DISCORD_TOKEN;
const CLIENT_ID = process.env.CLIENT_ID;

if (!TOKEN || !CLIENT_ID) {
  console.error("Missing DISCORD_TOKEN or CLIENT_ID environment variables");
  process.exit(1);
}

// Define slash commands
const commands = [
  new SlashCommandBuilder()
    .setName("ping")
    .setDescription("Check bot latency"),
  new SlashCommandBuilder()
    .setName("hello")
    .setDescription("Get a friendly greeting"),
  new SlashCommandBuilder()
    .setName("info")
    .setDescription("Show bot information"),
].map((cmd) => cmd.toJSON());

// Register commands
async function registerCommands() {
  const rest = new REST().setToken(TOKEN);
  try {
    console.log("Registering slash commands...");
    await rest.put(Routes.applicationCommands(CLIENT_ID), { body: commands });
    console.log("Slash commands registered.");
  } catch (error) {
    console.error("Failed to register commands:", error);
  }
}

// Create client
const client = new Client({
  intents: [GatewayIntentBits.Guilds],
});

client.once("ready", () => {
  console.log(`Bot online as ${client.user.tag}`);
  console.log(`Serving ${client.guilds.cache.size} guild(s)`);
});

client.on("interactionCreate", async (interaction) => {
  if (!interaction.isChatInputCommand()) return;

  switch (interaction.commandName) {
    case "ping":
      const latency = Date.now() - interaction.createdTimestamp;
      await interaction.reply(`Pong! Latency: ${latency}ms`);
      break;
    case "hello":
      await interaction.reply(`Hello, ${interaction.user.username}! 👋`);
      break;
    case "info":
      await interaction.reply(
        `**Berth Discord Bot**\nGuilds: ${client.guilds.cache.size}\nUptime: ${Math.floor(client.uptime / 1000)}s`
      );
      break;
    default:
      await interaction.reply("Unknown command");
  }
});

registerCommands().then(() => client.login(TOKEN));
