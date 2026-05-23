import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { spawnSync } from "node:child_process";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

const USER_DATA_DIR = process.env.USER_DATA || path.join(os.homedir(), "user_data");

function todayString() {
	const now = new Date();
	const year = now.getFullYear();
	const month = String(now.getMonth() + 1).padStart(2, "0");
	const day = String(now.getDate()).padStart(2, "0");
	return `${year}-${month}-${day}`;
}

function ensureDailyBackup(dataDir: string): { created: boolean; backupPath?: string; skipped?: string; error?: string } {
	if (!fs.existsSync(dataDir)) {
		return { created: false, skipped: `Parker data directory not found: ${dataDir}` };
	}

	const backupsDir = path.join(dataDir, "backups");
	fs.mkdirSync(backupsDir, { recursive: true });

	const backupName = `${todayString()}-user_data.zip`;
	const backupPath = path.join(backupsDir, backupName);
	if (fs.existsSync(backupPath)) {
		return { created: false, backupPath };
	}

	const tempPath = `${backupPath}.tmp`;
	try {
		if (fs.existsSync(tempPath)) fs.rmSync(tempPath, { force: true });
		const result = spawnSync(
			"zip",
			[
				"-r",
				"-q",
				tempPath,
				".",
				"-x",
				"backups/",
				"backups/*",
			],
			{
				cwd: dataDir,
				encoding: "utf8",
			},
		);
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
	let shouldClearOnFirstPrompt = false;

	function clearStartupBackupWidget(ctx: ExtensionContext) {
		if (!ctx.hasUI || !shouldClearOnFirstPrompt) return;
		ctx.ui.setWidget("data-backup", undefined);
		shouldClearOnFirstPrompt = false;
	}

	pi.on("session_start", async (event, ctx) => {
		if (process.env.PI_SUBAGENT === "1") return;

		shouldClearOnFirstPrompt = false;
		if (event.reason !== "startup") return;

		const result = ensureDailyBackup(USER_DATA_DIR);
		if (!ctx.hasUI) return;

		const theme = ctx.ui.theme;
		if (result.created) {
			ctx.ui.setWidget("data-backup", [theme.fg("dim", `backup: ok (created ${result.backupPath ?? ""})`)]);
			shouldClearOnFirstPrompt = true;
			return;
		}
		if (result.backupPath) {
			ctx.ui.setWidget(
				"data-backup",
				[theme.fg("dim", `backup: ok (${result.backupPath} already exists)`)],
			);
			shouldClearOnFirstPrompt = true;
			return;
		}
		if (result.error) {
			ctx.ui.setWidget("data-backup", [theme.fg("warning", `backup failed: ${result.error}`)]);
			shouldClearOnFirstPrompt = true;
			return;
		}
		if (result.skipped) {
			ctx.ui.setWidget("data-backup", [theme.fg("warning", `backup skipped: ${result.skipped}`)]);
			shouldClearOnFirstPrompt = true;
			return;
		}
	});

	pi.on("before_agent_start", async (_event, ctx) => {
		if (process.env.PI_SUBAGENT === "1") return;
		clearStartupBackupWidget(ctx);
	});

	pi.on("user_bash", async (_event, ctx) => {
		if (process.env.PI_SUBAGENT === "1") return;
		clearStartupBackupWidget(ctx);
	});
}
