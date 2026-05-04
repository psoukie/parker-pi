import * as fs from "node:fs";
import * as path from "node:path";
import { spawnSync } from "node:child_process";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

function todayString() {
	const now = new Date();
	const year = now.getFullYear();
	const month = String(now.getMonth() + 1).padStart(2, "0");
	const day = String(now.getDate()).padStart(2, "0");
	return `${year}-${month}-${day}`;
}

function ensureDailyBackup(cwd: string): { created: boolean; backupPath?: string; skipped?: string; error?: string } {
	const dataDir = path.join(cwd, "data");
	if (!fs.existsSync(dataDir)) {
		return { created: false, skipped: "No data/ directory found." };
	}

	const backupsDir = path.join(cwd, "backups");
	fs.mkdirSync(backupsDir, { recursive: true });

	const backupName = `${todayString()}-data.zip`;
	const backupPath = path.join(backupsDir, backupName);
	if (fs.existsSync(backupPath)) {
		return { created: false, backupPath };
	}

	const tempPath = `${backupPath}.tmp`;
	try {
		if (fs.existsSync(tempPath)) fs.rmSync(tempPath, { force: true });
		const result = spawnSync("zip", ["-r", "-q", tempPath, "data"], {
			cwd,
			encoding: "utf8",
		});
		if (result.status !== 0) {
			return { created: false, error: (result.stderr || result.stdout || "zip failed").trim() };
		}
		fs.renameSync(tempPath, backupPath);
		return { created: true, backupPath };
	} catch (error) {
		return {
			created: false,
			error: error instanceof Error ? error.message : String(error),
		};
	} finally {
		if (fs.existsSync(tempPath)) fs.rmSync(tempPath, { force: true });
	}
}

export default function dataBackupExtension(pi: ExtensionAPI) {
	pi.on("session_start", async (_event, ctx) => {
		if (process.env.PI_SUBAGENT === "1") return;

		const result = ensureDailyBackup(ctx.cwd);
		if (result.created && ctx.hasUI) {
			ctx.ui.notify(`Created backup: ${path.relative(ctx.cwd, result.backupPath ?? "")}`, "info");
		}
		if (result.error && ctx.hasUI) {
			ctx.ui.notify(`Backup failed: ${result.error}`, "warning");
		}
	});
}
