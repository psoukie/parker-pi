import * as fs from "node:fs";
import * as path from "node:path";
import { spawnSync } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

function todayString() {
	const now = new Date();
	const year = now.getFullYear();
	const month = String(now.getMonth() + 1).padStart(2, "0");
	const day = String(now.getDate()).padStart(2, "0");
	return `${year}-${month}-${day}`;
}

function ensureDailyBackup(cwd: string): { created: boolean; backupPath?: string; skipped?: string; error?: string } {
	if (!fs.existsSync(cwd)) {
		return { created: false, skipped: `Working directory not found: ${cwd}` };
	}

	const backupsDir = path.join(cwd, "backups");
	fs.mkdirSync(backupsDir, { recursive: true });

	const backupName = `${todayString()}-workspace.zip`;
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
				"./backups/",
				"./backups/*",
			],
			{
				cwd,
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

	pi.on("session_start", async (_event, ctx) => {
		if (process.env.PI_SUBAGENT === "1") return;

		shouldClearOnFirstPrompt = false;
		const result = ensureDailyBackup(ctx.cwd);
		if (!ctx.hasUI) return;

		const theme = ctx.ui.theme;
		if (result.created) {
			ctx.ui.setWidget("data-backup", [theme.fg("dim", `backup: ok (created ${path.relative(ctx.cwd, result.backupPath ?? "")})`)]);
			shouldClearOnFirstPrompt = true;
			return;
		}
		if (result.backupPath) {
			ctx.ui.setWidget(
				"data-backup",
				[theme.fg("dim", `backup: ok (${path.relative(ctx.cwd, result.backupPath)} already exists)`)],
			);
			shouldClearOnFirstPrompt = true;
			return;
		}
		if (result.error) {
			ctx.ui.setWidget("data-backup", [theme.fg("warning", `backup failed: ${result.error}`)]);
			shouldClearOnFirstPrompt = true;
			return;
		}
	});

	pi.on("before_agent_start", async (_event, ctx) => {
		if (process.env.PI_SUBAGENT === "1") return;
		if (!ctx.hasUI || !shouldClearOnFirstPrompt) return;
		ctx.ui.setWidget("data-backup", undefined);
		shouldClearOnFirstPrompt = false;
	});
}
