const LEVELS = { DEBUG: 10, INFO: 20, ERROR: 40 };
const configuredLevel = String(
  import.meta.env.VITE_VOICE_LOG_LEVEL ?? import.meta.env.VITE_LOG_LEVEL ?? "INFO"
).toUpperCase();
const threshold = LEVELS[configuredLevel] ?? LEVELS.INFO;

export function voiceLog(level, event, details = {}) {
  const normalizedLevel = String(level).toUpperCase();
  if ((LEVELS[normalizedLevel] ?? LEVELS.INFO) < threshold) return;
  const payload = {
    logger: "mjolniros.voice",
    level: normalizedLevel,
    event,
    timestamp: new Date().toISOString(),
    ...details
  };
  if (normalizedLevel === "ERROR") console.error(payload);
  else if (normalizedLevel === "DEBUG") console.debug(payload);
  else console.info(payload);
}

export function voiceState(state, details = {}) {
  voiceLog("INFO", `VOICE_STATE: ${state}`, { voice_state: state, ...details });
}
