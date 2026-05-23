import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const USER_DATA_DIR = process.env.USER_DATA || path.join(os.homedir(), "user_data");
const MEMORY_MESSAGE_TYPE = "memory";

type MemoryInjectTrigger = "session_start" | "session_compact";

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

	function buildMemoryMessage(trigger: MemoryInjectTrigger) {
		if (!memoryContent) return undefined;
		return {
			customType: MEMORY_MESSAGE_TYPE,
			content: `The following persistent agent memory was loaded from \`${memoryPath}\`:

${memoryContent}`,
			display: false,
			details: {
				trigger,
				path: memoryPath,
			},
		};
	}

	function injectMemoryLeaf(trigger: MemoryInjectTrigger) {
		const message = buildMemoryMessage(trigger);
		if (!message) return;
		pi.sendMessage(message, { triggerTurn: false });
	}

	pi.on("session_start", async () => {
		if (isSubagentProcess()) return;
		loadMemory();
		injectMemoryLeaf("session_start");
	});

	pi.on("resources_discover", async () => {
		if (isSubagentProcess()) return;
		loadMemory();
	});

	pi.on("session_compact", async () => {
		if (isSubagentProcess()) return;
		loadMemory();
		injectMemoryLeaf("session_compact");
	});
}
