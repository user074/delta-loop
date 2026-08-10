export const stageNames: Record<string, string> = {
  "minimal-probe": "Quick test",
  "signal-confirmation": "Check the result",
  "full-investigation": "Full study",
  replicate: "Repeat the original",
  "controlled-variation": "Change one thing",
};

export const planStatusNames: Record<string, string> = {
  draft: "Still editing",
  ready: "Ready to run",
  running: "Running",
  finished: "Finished",
  failed: "Stopped with an error",
  cancelled: "Stopped",
};

export const runStatusNames: Record<string, string> = {
  starting: "Starting",
  running: "Running",
  finished: "Finished",
  failed: "Stopped with an error",
  cancelled: "Stopped",
};
