import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function memoryExtension(pi: ExtensionAPI) {
	let memoryPath = "";
	let memoryContent: string | undefined;

	function isSubagentProcess() {
		return process.env.PI_SUBAGENT === "1";
	}

	function loadMemory(cwd: string) {
		memoryPath = path.join(cwd, "data", "MEMORY.md");
		memoryContent = fs.existsSync(memoryPath)
			? fs.readFileSync(memoryPath, "utf8").trim()
			: undefined;
	}

	pi.on("session_start", async (_event, ctx) => {
		if (isSubagentProcess()) return;
		loadMemory(ctx.cwd);
	});

	pi.on("resources_discover", async (event) => {
		if (isSubagentProcess()) return;
		loadMemory(event.cwd);
	});

	pi.on("before_agent_start", async (event) => {
		if (isSubagentProcess()) return;
		if (!memoryContent) return;

		return {
			systemPrompt: `${event.systemPrompt}

## Parker's Memory

The following persistent project memory was loaded from \`data/MEMORY.md\`:

${memoryContent}
`,
		};
	});
}
