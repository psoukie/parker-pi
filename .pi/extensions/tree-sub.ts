import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { StringEnum } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { type AgentConfig, type AgentScope, discoverAgents } from "./subagent/agents.js";

const USER_DATA_DIR = process.env.USER_DATA || path.join(os.homedir(), "user_data");
const STATE_DIR = path.join(USER_DATA_DIR, "state", "pi-tree-sub");
const WIDGET_ID = "tree-sub";
const ORIGIN_LABEL = "sub-origin";
const RETURN_LABEL = "sub-return";

function isSubagentProcess() {
	return process.env.PI_SUBAGENT === "1";
}

function ensureStateDir() {
	fs.mkdirSync(STATE_DIR, { recursive: true });
}

function statePath(ctx: ExtensionContext) {
	const sessionId = ctx.sessionManager.getSessionId();
	return path.join(STATE_DIR, `${sessionId}.txt`);
}

function readOriginId(ctx: ExtensionContext): string | undefined {
	const file = statePath(ctx);
	if (!fs.existsSync(file)) return undefined;
	const value = fs.readFileSync(file, "utf8").trim();
	return value || undefined;
}

function writeOriginId(ctx: ExtensionContext, originId: string) {
	ensureStateDir();
	fs.writeFileSync(statePath(ctx), `${originId}\n`, "utf8");
}

function clearOriginId(ctx: ExtensionContext) {
	const file = statePath(ctx);
	if (fs.existsSync(file)) fs.rmSync(file, { force: true });
}

function setSubWidget(ctx: ExtensionContext, active: boolean) {
	if (!ctx.hasUI) return;
	if (!active) {
		ctx.ui.setWidget(WIDGET_ID, undefined);
		return;
	}
	ctx.ui.setWidget(WIDGET_ID, [ctx.ui.theme.fg("accent", "sub: active")]);
}

function notify(ctx: ExtensionContext, message: string, level: "info" | "warning" | "error" = "info") {
	if (ctx.hasUI) ctx.ui.notify(message, level);
}

function parseSubArgs(args: string): { agentName?: string; prompt: string; selectAgent: boolean } {
	const trimmed = args.trim();
	if (!trimmed) return { prompt: "", selectAgent: false };

	const selectMatch = trimmed.match(/^--select\s+([\s\S]*)$/);
	if (selectMatch) {
		return { prompt: selectMatch[1].trim(), selectAgent: true };
	}

	const agentMatch = trimmed.match(/^(?:--agent\s+|@)([A-Za-z0-9_-]+)\s+([\s\S]*)$/);
	if (agentMatch) {
		return { agentName: agentMatch[1], prompt: agentMatch[2].trim(), selectAgent: false };
	}

	return { prompt: trimmed, selectAgent: false };
}

function buildAgentPrompt(agent: AgentConfig, prompt: string) {
	return [
		`Visible branch task using agent profile: ${agent.name}`,
		"",
		`Agent description: ${agent.description}`,
		"",
		"Follow these agent-specific instructions for this branch:",
		"",
		agent.systemPrompt.trim(),
		"",
		"Task:",
		prompt,
	].join("\n");
}

function resolveAgent(ctx: ExtensionContext, agentName: string | undefined, agentScope: AgentScope): { agent?: AgentConfig; error?: string } {
	if (!agentName) return {};
	const discovery = discoverAgents(ctx.cwd, agentScope);
	const agent = discovery.agents.find((candidate) => candidate.name === agentName);
	if (agent) return { agent };
	const available = discovery.agents.map((candidate) => candidate.name).join(", ") || "none";
	return { error: `Unknown agent: ${agentName}. Available agents: ${available}.` };
}

function startSubBranch(
	pi: ExtensionAPI,
	ctx: ExtensionContext,
	prompt: string,
	options?: { agentName?: string; agentScope?: AgentScope; deliverAs?: "followUp" | "steer" },
): { ok: true; originId: string; prompt: string; agentName?: string } | { ok: false; error: string } {
	if (isSubagentProcess()) return { ok: false, error: "tree-sub is disabled inside subprocess subagents." };

	const existingOriginId = readOriginId(ctx);
	if (existingOriginId) {
		return { ok: false, error: "Already inside a /sub branch. Use /return first; nested /sub is intentionally disabled." };
	}

	const originId = ctx.sessionManager.getLeafId();
	if (!originId) {
		return { ok: false, error: "Cannot start /sub before the session has a tree entry." };
	}

	const agentScope = options?.agentScope ?? "both";
	const resolved = resolveAgent(ctx, options?.agentName, agentScope);
	if (resolved.error) return { ok: false, error: resolved.error };

	const branchPrompt = resolved.agent ? buildAgentPrompt(resolved.agent, prompt) : prompt;
	writeOriginId(ctx, originId);
	pi.setLabel(originId, ORIGIN_LABEL);
	setSubWidget(ctx, true);
	pi.sendUserMessage(branchPrompt, options?.deliverAs ? { deliverAs: options.deliverAs } : undefined);
	return { ok: true, originId, prompt: branchPrompt, agentName: resolved.agent?.name };
}

function defaultReturnInstructions(focus?: string) {
	const base = [
		"Summarize this temporary /sub branch for returning to the main conversation.",
		"Include: objective, key findings, decisions made, files changed or commands run if relevant, unresolved issues, and recommended next step.",
		"Be concise and preserve only information useful for continuing from the original point.",
	];
	if (focus?.trim()) {
		base.push("", `Additional focus from user: ${focus.trim()}`);
	}
	return base.join("\n");
}

const AgentScopeSchema = StringEnum(["user", "project", "both"] as const, {
	description: 'Which agent directories to use when --agent/agent is provided. Default: "both".',
	default: "both",
});

const TreeSubStartParams = Type.Object({
	prompt: Type.String({ description: "Task prompt to run on a visible temporary session-tree branch." }),
	agent: Type.Optional(
		Type.String({
			description:
				"Optional agent profile name, e.g. william or worker. The profile description and instructions are injected into the branch prompt; no subprocess is spawned.",
		}),
	),
	agentScope: Type.Optional(AgentScopeSchema),
});

export default function treeSubExtension(pi: ExtensionAPI) {
	pi.on("session_start", async (_event, ctx) => {
		if (isSubagentProcess()) return;
		ensureStateDir();
		clearOriginId(ctx);
		setSubWidget(ctx, false);
	});

	pi.registerTool({
		name: "tree_sub_start",
		label: "Tree Sub Start",
		description: [
			"Start a visible temporary branch task in the current Pi session tree.",
			"Use when a subagent-style investigation is helpful but true parallel subprocess isolation is not required.",
			"This queues the branch task; the user must later run /return to summarize the branch and return to the origin.",
			"Optionally provide an agent profile name to inject that agent's description and instructions into the branch prompt without spawning a subprocess.",
		].join(" "),
		promptSnippet: "tree_sub_start: start a visible branch-subagent task; user later runs /return to summarize and return.",
		promptGuidelines: [
			"Prefer tree_sub_start over subprocess subagent delegation when the work should remain visible and inspectable in /tree and true parallelism is not needed.",
			"Do not use tree_sub_start if already inside an active /sub branch; nested tree-sub work is intentionally disabled.",
			"After starting a tree-sub branch, tell the user they can inspect it with /tree and should run /return when they want to summarize and come back.",
		],
		parameters: TreeSubStartParams,
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const prompt = params.prompt.trim();
			if (!prompt) {
				return { content: [{ type: "text", text: "Missing prompt." }], isError: true };
			}

			const result = startSubBranch(pi, ctx, prompt, {
				agentName: params.agent,
				agentScope: params.agentScope ?? "both",
				deliverAs: ctx.isIdle() ? undefined : "followUp",
			});
			if (!result.ok) {
				return { content: [{ type: "text", text: result.error }], isError: true };
			}

			const agentText = result.agentName ? ` using agent profile \`${result.agentName}\`` : "";
			return {
				content: [
					{
						type: "text",
						text: `Started visible /sub branch from ${result.originId}${agentText}. The branch task has been queued; run /return when ready to summarize and return.`,
					},
				],
			};
		},
	});

	pi.registerCommand("sub", {
		description: "Start a visible temporary branch task from the current tree position",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			if (isSubagentProcess()) return;

			let { agentName, prompt, selectAgent } = parseSubArgs(args);
			if (!prompt) {
				notify(ctx, "Usage: /sub [--agent NAME|@name|--select] <prompt>", "warning");
				return;
			}

			if (!ctx.isIdle()) {
				notify(ctx, "Agent is busy. Run /sub once the agent is idle.", "warning");
				return;
			}

			if (selectAgent) {
				const discovery = discoverAgents(ctx.cwd, "both");
				if (discovery.agents.length === 0) {
					notify(ctx, "No agents available to select.", "warning");
					return;
				}
				const choices = ["(none)", ...discovery.agents.map((agent) => `${agent.name} (${agent.source}) — ${agent.description}`)];
				const choice = await ctx.ui.select("Use which agent profile for this /sub branch?", choices);
				if (!choice) return;
				if (choice !== "(none)") agentName = choice.split(" ", 1)[0];
			}

			const result = startSubBranch(pi, ctx, prompt, { agentName, agentScope: "both" });
			if (!result.ok) {
				notify(ctx, result.error, "warning");
				return;
			}

			const agentText = result.agentName ? ` using agent profile ${result.agentName}` : "";
			notify(ctx, `Started /sub branch from ${result.originId}${agentText}`, "info");
		},
	});

	pi.registerCommand("return", {
		description: "Summarize the current /sub branch and return to its origin",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			if (isSubagentProcess()) return;

			const originId = readOriginId(ctx);
			if (!originId) {
				notify(ctx, "No active /sub branch found.", "warning");
				return;
			}

			if (!ctx.sessionManager.getEntry(originId)) {
				clearOriginId(ctx);
				setSubWidget(ctx, false);
				notify(ctx, `Stored /sub origin ${originId} no longer exists; cleared state.`, "error");
				return;
			}

			await ctx.waitForIdle();
			notify(ctx, `Returning to /sub origin ${originId} with branch summary...`, "info");

			const result = await ctx.navigateTree(originId, {
				summarize: true,
				customInstructions: defaultReturnInstructions(args),
				label: RETURN_LABEL,
			});

			if (result.cancelled) {
				notify(ctx, "/return cancelled; /sub state preserved.", "warning");
				return;
			}

			clearOriginId(ctx);
			setSubWidget(ctx, false);
			notify(ctx, "Returned from /sub branch.", "info");
		},
	});
}
