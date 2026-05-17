import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const USER_DATA_DIR = process.env.USER_DATA || path.join(os.homedir(), "user_data");

export default function memoryExtension(pi: ExtensionAPI) {
	let memoryPath = "";
	let memoryContent: string | undefined;

	function isSubagentProcess() {
		return process.env.PI_SUBAGENT === "1";
	}

	function loadMemory() {
		memoryPath = path.join(USER_DATA_DIR, "MEMORY.md");
		memoryContent = fs.existsSync(memoryPath)
			? fs.readFileSync(memoryPath, "utf8").trim()
			: undefined;
	}

	pi.on("session_start", async () => {
		if (isSubagentProcess()) return;
		loadMemory();
	});

	pi.on("resources_discover", async () => {
		if (isSubagentProcess()) return;
		loadMemory();
	});

	pi.on("before_agent_start", async (event) => {
		if (isSubagentProcess()) return;
		if (!memoryContent) return;

		return {
			systemPrompt: `${event.systemPrompt}

## Parker's Memory

The following persistent Parker memory was loaded from \`${memoryPath}\`:

${memoryContent}
`,
		};
	});
}
