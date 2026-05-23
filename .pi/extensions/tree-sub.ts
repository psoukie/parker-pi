import * as fs from "node:fs";
import * as path from "node:path";
import { DynamicBorder, getAgentDir, parseFrontmatter, type ExtensionAPI, type ExtensionCommandContext, type ExtensionContext, type SessionEntry } from "@earendil-works/pi-coding-agent";
import { Editor, Key, matchesKey, SelectList, type EditorTheme, type SelectItem } from "@earendil-works/pi-tui";
import { Type } from "typebox";

const CUSTOM_TYPE = "tree-sub";
const WIDGET_ID = "tree-sub";
const ORIGIN_LABEL = "branch-origin";
const RETURN_LABEL = "branch-return";
const NO_CONTEXT_SUMMARY = "This branch intentionally starts with no prior conversation history. The next user message defines the branch task.";

type AgentScope = "user" | "project" | "both";
type BranchContextMode = "full" | "compacted" | "none";

interface AgentConfig {
	name: string;
	description: string;
	tools?: string[];
	model?: string;
	systemPrompt: string;
	source: "user" | "project";
	filePath: string;
}

interface AgentDiscoveryResult {
	agents: AgentConfig[];
	projectAgentsDir: string | null;
}

interface TreeSubState {
	originId: string;
	startEntryId: string;
	agentName?: string;
	contextMode?: BranchContextMode;
}

interface TreeSubEntryData {
	version: 1;
	event: "start" | "return" | "cancel";
	originId: string;
	startEntryId?: string;
	agentName?: string;
	contextMode?: BranchContextMode;
	forget?: boolean;
	timestamp: string;
}

interface PendingContextReset {
	startEntryId: string;
	firstKeptEntryId: string;
}

let pendingContextReset: PendingContextReset | undefined;

function isSubagentProcess() {
	return process.env.PI_SUBAGENT === "1";
}

function loadAgentsFromDir(dir: string, source: "user" | "project"): AgentConfig[] {
	const agents: AgentConfig[] = [];
	if (!fs.existsSync(dir)) return agents;

	let entries: fs.Dirent[];
	try {
		entries = fs.readdirSync(dir, { withFileTypes: true });
	} catch {
		return agents;
	}

	for (const entry of entries) {
		if (!entry.name.endsWith(".md")) continue;
		if (!entry.isFile() && !entry.isSymbolicLink()) continue;

		const filePath = path.join(dir, entry.name);
		let content: string;
		try {
			content = fs.readFileSync(filePath, "utf-8");
		} catch {
			continue;
		}

		const { frontmatter, body } = parseFrontmatter<Record<string, string>>(content);
		if (!frontmatter.name || !frontmatter.description) continue;

		const tools = frontmatter.tools
			?.split(",")
			.map((tool: string) => tool.trim())
			.filter(Boolean);

		agents.push({
			name: frontmatter.name,
			description: frontmatter.description,
			tools: tools && tools.length > 0 ? tools : undefined,
			model: frontmatter.model,
			systemPrompt: body,
			source,
			filePath,
		});
	}

	return agents;
}

function isDirectory(p: string): boolean {
	try {
		return fs.statSync(p).isDirectory();
	} catch {
		return false;
	}
}

function findNearestProjectAgentsDir(cwd: string): string | null {
	let currentDir = cwd;
	while (true) {
		const candidate = path.join(currentDir, ".pi", "agents");
		if (isDirectory(candidate)) return candidate;

		const parentDir = path.dirname(currentDir);
		if (parentDir === currentDir) return null;
		currentDir = parentDir;
	}
}

function discoverAgents(cwd: string, scope: AgentScope): AgentDiscoveryResult {
	const userDir = path.join(getAgentDir(), "agents");
	const projectAgentsDir = findNearestProjectAgentsDir(cwd);

	const userAgents = scope === "project" ? [] : loadAgentsFromDir(userDir, "user");
	const projectAgents = scope === "user" || !projectAgentsDir ? [] : loadAgentsFromDir(projectAgentsDir, "project");
	const agentMap = new Map<string, AgentConfig>();

	if (scope === "both") {
		for (const agent of userAgents) agentMap.set(agent.name, agent);
		for (const agent of projectAgents) agentMap.set(agent.name, agent);
	} else if (scope === "user") {
		for (const agent of userAgents) agentMap.set(agent.name, agent);
	} else {
		for (const agent of projectAgents) agentMap.set(agent.name, agent);
	}

	return { agents: Array.from(agentMap.values()), projectAgentsDir };
}

function isBranchStateEntry(entry: SessionEntry): entry is SessionEntry & { type: "custom"; customType: typeof CUSTOM_TYPE; data?: TreeSubEntryData } {
	return entry.type === "custom" && entry.customType === CUSTOM_TYPE;
}

function parseBranchStateEntryData(data: unknown): TreeSubEntryData | undefined {
	if (!data || typeof data !== "object") return undefined;
	const value = data as Partial<TreeSubEntryData>;
	if (value.version !== 1) return undefined;
	if (value.event !== "start" && value.event !== "return" && value.event !== "cancel") return undefined;
	if (typeof value.originId !== "string" || !value.originId.trim()) return undefined;
	const contextMode = value.contextMode === "full" || value.contextMode === "compacted" || value.contextMode === "none" ? value.contextMode : undefined;
	return {
		version: 1,
		event: value.event,
		originId: value.originId.trim(),
		startEntryId: typeof value.startEntryId === "string" && value.startEntryId.trim() ? value.startEntryId.trim() : undefined,
		agentName: typeof value.agentName === "string" && value.agentName.trim() ? value.agentName.trim() : undefined,
		contextMode,
		forget: typeof value.forget === "boolean" ? value.forget : undefined,
		timestamp: typeof value.timestamp === "string" && value.timestamp.trim() ? value.timestamp.trim() : "",
	};
}

function readBranchState(ctx: ExtensionContext): TreeSubState | undefined {
	let active: TreeSubState | undefined;

	for (const entry of ctx.sessionManager.getBranch()) {
		if (!isBranchStateEntry(entry)) continue;
		const data = parseBranchStateEntryData(entry.data);
		if (!data) continue;

		if (data.event === "start") {
			active = {
				originId: data.originId,
				startEntryId: entry.id,
				agentName: data.agentName,
				contextMode: data.contextMode,
			};
			continue;
		}

		const matchesActiveStart = !data.startEntryId || data.startEntryId === active?.startEntryId;
		const matchesActiveOrigin = data.originId === active?.originId;
		if (active && matchesActiveOrigin && matchesActiveStart) active = undefined;
	}

	return active;
}

function appendBranchStartState(pi: ExtensionAPI, ctx: ExtensionContext, originId: string, agentName?: string, contextMode?: BranchContextMode): TreeSubState {
	pi.appendEntry<TreeSubEntryData>(CUSTOM_TYPE, {
		version: 1,
		event: "start",
		originId,
		agentName,
		contextMode,
		timestamp: new Date().toISOString(),
	});

	const startEntryId = ctx.sessionManager.getLeafId();
	if (!startEntryId) throw new Error("Failed to append tree-sub start state.");
	return { originId, startEntryId, agentName, contextMode };
}

function appendBranchReturnState(pi: ExtensionAPI, state: TreeSubState, forget: boolean) {
	pi.appendEntry<TreeSubEntryData>(CUSTOM_TYPE, {
		version: 1,
		event: "return",
		originId: state.originId,
		startEntryId: state.startEntryId,
		agentName: state.agentName,
		contextMode: state.contextMode,
		forget,
		timestamp: new Date().toISOString(),
	});
}

function setBranchWidget(ctx: ExtensionContext, state: TreeSubState | undefined) {
	if (!ctx.hasUI) return;
	if (!state) {
		ctx.ui.setWidget(WIDGET_ID, undefined);
		return;
	}
	const text = state.agentName ? `branch: ${state.agentName}` : "branch: active";
	ctx.ui.setWidget(WIDGET_ID, [ctx.ui.theme.fg("accent", text)]);
}

function notify(ctx: ExtensionContext, message: string, level: "info" | "warning" | "error" = "info") {
	if (ctx.hasUI) ctx.ui.notify(message, level);
}

function buildAgentSystemPrompt(agent: AgentConfig) {
	return [
		"",
		"## Visible Branch Agent Profile",
		"",
		`This temporary /branch is using agent profile: ${agent.name}`,
		"",
		`Agent description: ${agent.description}`,
		"",
		"Follow these agent-specific instructions for this branch:",
		"",
		agent.systemPrompt.trim(),
	].join("\n");
}

interface BranchStartSelection {
	agentName?: string;
	contextMode: BranchContextMode;
}

function getContextModeLabel(contextMode: BranchContextMode) {
	if (contextMode === "compacted") return "Compacted context";
	if (contextMode === "none") return "No prior context";
	return "Full context";
}

function getNextContextMode(contextMode: BranchContextMode, direction = 1): BranchContextMode {
	const modes: BranchContextMode[] = ["full", "compacted", "none"];
	const index = modes.indexOf(contextMode);
	return modes[(index + direction + modes.length) % modes.length];
}

async function selectBranchStartOptions(ctx: ExtensionCommandContext): Promise<BranchStartSelection | null> {
	const discovery = discoverAgents(ctx.cwd, "project");
	let contextMode: BranchContextMode = "full";
	const noneValue = "__none__";
	const items: SelectItem[] = [
		{ value: noneValue, label: "No agent profile", description: "Use Parker's normal instructions" },
		...discovery.agents.map((agent) => ({
			value: agent.name,
			label: agent.name,
			description: agent.description,
		})),
	];

	return await ctx.ui.custom<BranchStartSelection | null>((tui, theme, keybindings, done) => {
		const divider = new DynamicBorder((s: string) => theme.fg("border", s));
		const selectList = new SelectList(items, Math.min(items.length, 10), {
			selectedPrefix: (text: string) => theme.fg("accent", text),
			selectedText: (text: string) => theme.fg("accent", text),
			description: (text: string) => theme.fg("muted", text),
			scrollInfo: (text: string) => theme.fg("dim", text),
			noMatch: (text: string) => theme.fg("warning", text),
		});

		selectList.onSelect = (item: SelectItem) => {
			done({
				agentName: item.value === noneValue ? undefined : String(item.value),
				contextMode,
			});
		};
		selectList.onCancel = () => done(null);

		return {
			render: (width: number) => [
				...divider.render(width),
				theme.bold("Start branch"),
				theme.fg("muted", `Context: ${getContextModeLabel(contextMode)}`),
				...divider.render(width),
				...selectList.render(width),
				...divider.render(width),
				theme.fg("dim", "↑↓ agent · Enter start · Esc cancel"),
				theme.fg("dim", "Tab/←/→ context · 1 full · 2 compacted · 3 none"),
				...divider.render(width),
			],
			invalidate: () => selectList.invalidate(),
			handleInput: (data: string) => {
				if (matchesKey(data, Key.tab) || matchesKey(data, Key.right)) {
					contextMode = getNextContextMode(contextMode);
					tui.requestRender();
					return;
				}
				if (matchesKey(data, Key.left)) {
					contextMode = getNextContextMode(contextMode, -1);
					tui.requestRender();
					return;
				}
				if (data === "1") {
					contextMode = "full";
					tui.requestRender();
					return;
				}
				if (data === "2") {
					contextMode = "compacted";
					tui.requestRender();
					return;
				}
				if (data === "3") {
					contextMode = "none";
					tui.requestRender();
					return;
				}
				if (keybindings.matches(data, "tui.select.cancel")) {
					done(null);
					return;
				}
				selectList.handleInput(data);
				tui.requestRender();
			},
		};
	});
}

function resolveAgent(ctx: ExtensionContext, agentName: string | undefined, agentScope: AgentScope): { agent?: AgentConfig; error?: string } {
	if (!agentName) return {};
	const discovery = discoverAgents(ctx.cwd, agentScope);
	const agent = discovery.agents.find((candidate) => candidate.name === agentName);
	if (agent) return { agent };
	const available = discovery.agents.map((candidate) => candidate.name).join(", ") || "none";
	return { error: `Unknown agent: ${agentName}. Available agents: ${available}.` };
}

function getStateAgent(ctx: ExtensionContext, state: TreeSubState): AgentConfig | undefined {
	if (!state.agentName) return undefined;
	return discoverAgents(ctx.cwd, "project").agents.find((agent) => agent.name === state.agentName);
}

function startBranch(
	pi: ExtensionAPI,
	ctx: ExtensionContext,
	prompt: string,
	options?: { agentName?: string; agentScope?: AgentScope; deliverAs?: "followUp" | "steer"; contextMode?: BranchContextMode; deferPrompt?: boolean },
): { ok: true; originId: string; prompt: string; agentName?: string; state: TreeSubState; contextBaseEntryId: string } | { ok: false; error: string } {
	if (isSubagentProcess()) return { ok: false, error: "tree-sub is disabled inside subprocess subagents." };

	const existingState = readBranchState(ctx);
	if (existingState) {
		return { ok: false, error: "Already inside a branch. Use /branch to return first; nested branches are intentionally disabled." };
	}

	const originId = ctx.sessionManager.getLeafId();
	if (!originId) {
		return { ok: false, error: "Cannot start a branch before the session has a tree entry." };
	}

	const agentScope = options?.agentScope ?? "project";
	const resolved = resolveAgent(ctx, options?.agentName, agentScope);
	if (resolved.error) return { ok: false, error: resolved.error };

	const state = appendBranchStartState(pi, ctx, originId, resolved.agent?.name, options?.contextMode);
	pi.setLabel(originId, ORIGIN_LABEL);
	const contextBaseEntryId = ctx.sessionManager.getLeafId();
	if (!contextBaseEntryId) return { ok: false, error: "Failed to identify branch context base entry." };
	setBranchWidget(ctx, state);
	if (!options?.deferPrompt) {
		pi.sendUserMessage(prompt, options?.deliverAs ? { deliverAs: options.deliverAs } : undefined);
	}
	return { ok: true, originId, prompt, agentName: resolved.agent?.name, state, contextBaseEntryId };
}

function defaultBranchReturnInstructions(focus?: string) {
	const base = [
		"Summarize this temporary branch for returning to the main conversation.",
		"Include: objective, key findings, decisions made, files changed or commands run if relevant, unresolved issues, and recommended next step.",
		"Be concise and preserve only information useful for continuing from the original point.",
	];
	if (focus?.trim()) {
		base.push("", `Additional focus from user: ${focus.trim()}`);
	}
	return base.join("\n");
}

const TreeSubStartParams = Type.Object({
	prompt: Type.String({ description: "Task prompt to run on a visible temporary session-tree branch." }),
	agent: Type.Optional(
		Type.String({
			description:
				"Optional project-local agent profile name from .pi/agents, e.g. william or worker. The profile description and instructions are injected into the branch system prompt; no subprocess is spawned.",
		}),
	),
});

async function inputBranchPrompt(ctx: ExtensionCommandContext, title: string): Promise<string | undefined> {
	return await ctx.ui.custom<string | undefined>((tui, theme, keybindings, done) => {
		const divider = new DynamicBorder((s: string) => theme.fg("border", s));
		const editorTheme: EditorTheme = {
			borderColor: (s: string) => theme.fg("border", s),
			selectList: {
				selectedPrefix: (text: string) => theme.fg("accent", text),
				selectedText: (text: string) => theme.fg("accent", text),
				description: (text: string) => theme.fg("muted", text),
				scrollInfo: (text: string) => theme.fg("dim", text),
				noMatch: (text: string) => theme.fg("warning", text),
			},
		};
		const editor = new Editor(tui, editorTheme);

		editor.onSubmit = (value: string) => done(value.trim() || undefined);

		return {
			render: (width: number) => [
				...divider.render(width),
				theme.bold(title),
				theme.fg("muted", "Describe the task for this branch."),
				...editor.render(width),
				theme.fg("dim", "Enter submit · Shift+Enter newline · \\+Enter newline · Esc cancel"),
				...divider.render(width),
			],
			invalidate: () => editor.invalidate(),
			handleInput: (data: string) => {
				if (matchesKey(data, Key.escape) || keybindings.matches(data, "tui.select.cancel")) {
					done(undefined);
					return;
				}
				editor.handleInput(data);
				tui.requestRender();
			},
		};
	});
}

async function startBranchFromMenu(pi: ExtensionAPI, ctx: ExtensionCommandContext) {
	if (!ctx.isIdle()) {
		notify(ctx, "Agent is busy. Run /branch once the agent is idle.", "warning");
		return;
	}

	const selection = await selectBranchStartOptions(ctx);
	if (!selection) return;

	const promptTitle = selection.agentName ? `Branch task for ${selection.agentName}` : "Branch task";
	const prompt = await inputBranchPrompt(ctx, promptTitle);
	if (!prompt) {
		notify(ctx, "/branch cancelled: no prompt entered.", "info");
		return;
	}

	const contextMode = selection.contextMode;
	const result = startBranch(pi, ctx, prompt, { agentName: selection.agentName, agentScope: "project", contextMode, deferPrompt: contextMode !== "full" });
	if (!result.ok) {
		notify(ctx, result.error, "warning");
		return;
	}

	const agentText = result.agentName ? ` using agent profile ${result.agentName}` : "";
	if (contextMode === "none") {
		pendingContextReset = { startEntryId: result.state.startEntryId, firstKeptEntryId: result.contextBaseEntryId };
		notify(ctx, `Preparing no-context branch from ${result.originId}${agentText}...`, "info");
		ctx.compact({
			onComplete: () => {
				pi.sendUserMessage(prompt);
				notify(ctx, `Started no-context branch from ${result.originId}${agentText}`, "info");
			},
			onError: (error) => {
				pendingContextReset = undefined;
				notify(ctx, `Failed to prepare no-context branch: ${error.message}`, "error");
			},
		});
		return;
	}

	if (contextMode === "compacted") {
		notify(ctx, `Preparing compacted-context branch from ${result.originId}${agentText}...`, "info");
		ctx.compact({
			onComplete: () => {
				pi.sendUserMessage(prompt);
				notify(ctx, `Started compacted-context branch from ${result.originId}${agentText}`, "info");
			},
			onError: (error) => {
				notify(ctx, `Failed to prepare compacted-context branch: ${error.message}`, "error");
			},
		});
		return;
	}

	notify(ctx, `Started branch from ${result.originId}${agentText}`, "info");
}

async function returnFromBranch(pi: ExtensionAPI, ctx: ExtensionCommandContext, forget: boolean) {
	const state = readBranchState(ctx);
	if (!state) {
		notify(ctx, "No active branch found.", "warning");
		return;
	}

	if (!ctx.sessionManager.getEntry(state.originId)) {
		setBranchWidget(ctx, undefined);
		notify(ctx, `Stored branch origin ${state.originId} no longer exists.`, "error");
		return;
	}

	await ctx.waitForIdle();
	notify(ctx, forget ? `Returning to branch origin ${state.originId} without summary...` : `Returning to branch origin ${state.originId} with branch summary...`, "info");

	appendBranchReturnState(pi, state, forget);

	const result = await ctx.navigateTree(
		state.originId,
		forget
			? undefined
			: {
					summarize: true,
					customInstructions: defaultBranchReturnInstructions(),
					label: RETURN_LABEL,
				},
	);

	if (result.cancelled) {
		notify(ctx, "/branch return cancelled; return marker was recorded but tree navigation was cancelled.", "warning");
		return;
	}

	setBranchWidget(ctx, undefined);
	notify(ctx, "Returned from branch.", "info");
}

async function showBranchMenu(pi: ExtensionAPI, ctx: ExtensionCommandContext) {
	const state = readBranchState(ctx);
	setBranchWidget(ctx, state);

	if (!state) {
		await startBranchFromMenu(pi, ctx);
		return;
	}

	const choice = await ctx.ui.select("Branch", ["Return with summary", "Return without summary"]);
	if (!choice) return;

	if (choice === "Return with summary") {
		await returnFromBranch(pi, ctx, false);
		return;
	}
	if (choice === "Return without summary") {
		await returnFromBranch(pi, ctx, true);
	}
}

export default function treeSubExtension(pi: ExtensionAPI) {
	pi.on("session_start", async (_event, ctx) => {
		if (isSubagentProcess()) return;
		setBranchWidget(ctx, readBranchState(ctx));
	});

	pi.on("session_before_compact", async (event, ctx) => {
		if (isSubagentProcess()) return;
		if (!pendingContextReset) return;

		const reset = pendingContextReset;
		pendingContextReset = undefined;
		if (!ctx.sessionManager.getEntry(reset.firstKeptEntryId)) {
			notify(ctx, "No-context branch setup failed: context reset point no longer exists.", "error");
			return { cancel: true };
		}

		return {
			compaction: {
				summary: NO_CONTEXT_SUMMARY,
				firstKeptEntryId: reset.firstKeptEntryId,
				tokensBefore: event.preparation.tokensBefore,
				details: {
					customType: CUSTOM_TYPE,
					contextMode: "none",
					startEntryId: reset.startEntryId,
				},
			},
		};
	});

	pi.on("before_agent_start", async (event, ctx) => {
		if (isSubagentProcess()) return;
		const state = readBranchState(ctx);
		if (!state?.agentName) return;

		const agent = getStateAgent(ctx, state);
		if (!agent) return;

		return {
			systemPrompt: event.systemPrompt + buildAgentSystemPrompt(agent),
		};
	});

	pi.registerTool({
		name: "tree_sub_start",
		label: "Tree Sub Start",
		description: [
			"Start a visible temporary branch task in the current Pi session tree.",
			"Use when a subagent-style investigation is helpful but true parallel subprocess isolation is not required.",
			"This queues the branch task; the user must later run /branch to summarize the branch and return to the origin.",
			"Optionally provide a project-local agent profile name from .pi/agents to inject that agent's description and instructions into the branch system prompt without spawning a subprocess.",
		].join(" "),
		promptSnippet: "tree_sub_start: start a branch task; user later runs /branch to summarize and return.",
		promptGuidelines: [
			"Prefer tree_sub_start over subprocess subagent delegation when the work should remain visible and inspectable in /tree and true parallelism is not needed.",
			"Do not use tree_sub_start if already inside an active branch; nested tree-sub work is intentionally disabled.",
			"After starting a tree-sub branch, tell the user they can inspect it with /tree and should run /branch when they want to summarize and come back.",
		],
		parameters: TreeSubStartParams,
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const prompt = params.prompt.trim();
			if (!prompt) {
				return { content: [{ type: "text", text: "Missing prompt." }], isError: true };
			}

			const result = startBranch(pi, ctx, prompt, {
				agentName: params.agent,
				agentScope: "project",
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
						text: `Started branch from ${result.originId}${agentText}. The branch task has been queued; run /branch when ready to summarize and return.`,
					},
				],
			};
		},
	});

	pi.registerCommand("branch", {
		description: "Open the branch menu",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			if (isSubagentProcess()) return;
			if (args.trim()) {
				notify(ctx, "Run /branch with no arguments and choose an action from the menu.", "warning");
				return;
			}
			await showBranchMenu(pi, ctx);
		},
	});
}
