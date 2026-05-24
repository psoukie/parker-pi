import * as fs from "node:fs";
import * as path from "node:path";
import { BorderedLoader, DynamicBorder, getAgentDir, parseFrontmatter, type ExtensionAPI, type ExtensionCommandContext, type ExtensionContext, type SessionEntry } from "@earendil-works/pi-coding-agent";
import { Editor, Key, matchesKey, SelectList, type EditorTheme, type SelectItem } from "@earendil-works/pi-tui";
import { Type } from "typebox";

const CUSTOM_TYPE = "branch";
const ANCHOR_TYPE = "branch-anchor";
const WIDGET_ID = "branch";
const ORIGIN_LABEL = "branch-origin";
const RETURN_LABEL = "branch-return";
const RETURN_TOOL_NAME = "excursion_return";
const NO_CONTEXT_SUMMARY = "This branch intentionally starts with no prior conversation history. The next user message defines the branch task.";
const BRANCH_PROMPT_PREFIX = "[START OF BRANCH EXCURSION]";

type AgentScope = "user" | "project" | "both";
type BranchContextMode = "full" | "compacted" | "none";
type BranchReturnContext = ExtensionContext & Partial<Pick<ExtensionCommandContext, "navigateTree" | "waitForIdle">>;

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

interface BranchState {
	originId: string;
	startEntryId: string;
	agentName?: string;
	contextMode?: BranchContextMode;
}

interface BranchEntryData {
	version: 1;
	event: "start";
	originId: string;
	agentName?: string;
	contextMode?: BranchContextMode;
	timestamp: string;
}

interface PendingContextReset {
	startEntryId: string;
	firstKeptEntryId: string;
}

interface PendingManualReturnSummary {
	startEntryId: string;
	targetId: string;
	oldLeafId: string | null;
	summary: string;
}

let pendingContextReset: PendingContextReset | undefined;
let pendingManualReturnSummary: PendingManualReturnSummary | undefined;

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

function isBranchStateEntry(entry: SessionEntry): entry is SessionEntry & { type: "custom"; customType: typeof CUSTOM_TYPE; data?: unknown } {
	return entry.type === "custom" && entry.customType === CUSTOM_TYPE;
}

function parseBranchStateEntryData(data: unknown): BranchEntryData | undefined {
	if (!data || typeof data !== "object") return undefined;
	const value = data as Partial<BranchEntryData>;
	if (value.version !== 1) return undefined;
	if (value.event !== "start") return undefined;
	if (typeof value.originId !== "string" || !value.originId.trim()) return undefined;
	const contextMode = value.contextMode === "full" || value.contextMode === "compacted" || value.contextMode === "none" ? value.contextMode : undefined;
	return {
		version: 1,
		event: "start",
		originId: value.originId.trim(),
		agentName: typeof value.agentName === "string" && value.agentName.trim() ? value.agentName.trim() : undefined,
		contextMode,
		timestamp: typeof value.timestamp === "string" && value.timestamp.trim() ? value.timestamp.trim() : "",
	};
}

function readBranchState(ctx: ExtensionContext): BranchState | undefined {
	const branch = ctx.sessionManager.getBranch();

	for (let i = branch.length - 1; i >= 0; i--) {
		const entry = branch[i];
		if (!entry || !isBranchStateEntry(entry)) continue;
		const data = parseBranchStateEntryData(entry.data);
		if (!data) continue;

		return {
			originId: data.originId,
			startEntryId: entry.id,
			agentName: data.agentName,
			contextMode: data.contextMode,
		};
	}

	return undefined;
}

function appendBranchAnchorIfNeeded(pi: ExtensionAPI, ctx: ExtensionContext, originId: string): string {
	const leaf = ctx.sessionManager.getLeafEntry();
	if (!leaf) throw new Error("Cannot inspect current branch origin leaf.");
	if (leaf.id !== originId) throw new Error("Current leaf changed before branch start state could be recorded.");
	if (leaf.type === "assistant") return originId;
	if ((leaf.type === "custom_message" || leaf.type === "custom") && leaf.customType === ANCHOR_TYPE) return originId;

	pi.sendMessage({
		customType: ANCHOR_TYPE,
		content: "",
		display: true,
		details: {
			version: 1,
			timestamp: new Date().toISOString(),
			anchoredFromId: originId,
			anchoredFromType: leaf.type,
		},
	});

	const anchorId = ctx.sessionManager.getLeafId();
	if (!anchorId) throw new Error("Failed to append branch anchor.");
	return anchorId;
}

function appendBranchStartState(pi: ExtensionAPI, ctx: ExtensionContext, originId: string, agentName?: string, contextMode?: BranchContextMode): BranchState {
	pi.appendEntry<BranchEntryData>(CUSTOM_TYPE, {
		version: 1,
		event: "start",
		originId,
		agentName,
		contextMode,
		timestamp: new Date().toISOString(),
	});

	const startEntryId = ctx.sessionManager.getLeafId();
	if (!startEntryId) throw new Error("Failed to append branch start state.");
	return { originId, startEntryId, agentName, contextMode };
}

function setBranchWidget(ctx: ExtensionContext, state: BranchState | undefined) {
	if (!ctx.hasUI) return;
	if (!state) {
		ctx.ui.setWidget(WIDGET_ID, undefined);
		return;
	}
	const text = state.agentName ? `branch: ${state.agentName}` : "branch: active";
	ctx.ui.setWidget(WIDGET_ID, [ctx.ui.theme.fg("accent", text)]);
}

function setBranchReturnToolActive(pi: ExtensionAPI, active: boolean) {
	const activeTools = pi.getActiveTools();
	const hasTool = activeTools.includes(RETURN_TOOL_NAME);
	if (active === hasTool) return;
	pi.setActiveTools(active ? [...activeTools, RETURN_TOOL_NAME] : activeTools.filter((name) => name !== RETURN_TOOL_NAME));
}

function refreshBranchState(pi: ExtensionAPI, ctx: ExtensionContext): BranchState | undefined {
	const state = readBranchState(ctx);
	setBranchWidget(ctx, state);
	setBranchReturnToolActive(pi, Boolean(state));
	return state;
}

function notify(ctx: ExtensionContext, message: string, level: "info" | "warning" | "error" = "info") {
	if (ctx.hasUI) ctx.ui.notify(message, level);
}

function tokenizeCommandArgs(input: string): string[] {
	const tokens: string[] = [];
	let current = "";
	let quote: '"' | "'" | undefined;
	let escaping = false;

	for (const char of input) {
		if (escaping) {
			current += char;
			escaping = false;
			continue;
		}
		if (char === "\\") {
			escaping = true;
			continue;
		}
		if (quote) {
			if (char === quote) {
				quote = undefined;
			} else {
				current += char;
			}
			continue;
		}
		if (char === '"' || char === "'") {
			quote = char;
			continue;
		}
		if (/\s/.test(char)) {
			if (current) {
				tokens.push(current);
				current = "";
			}
			continue;
		}
		current += char;
	}

	if (escaping) current += "\\";
	if (quote) throw new Error(`Unterminated ${quote} quote in command arguments.`);
	if (current) tokens.push(current);
	return tokens;
}

function quoteCommandArg(value: string): string {
	if (/^[^\s"'\\]+$/.test(value)) return value;
	return JSON.stringify(value);
}

function buildBranchReturnCommand(options?: { mode?: "summary" | "without_summary" | "result"; focus?: string; result?: string }) {
	const parts = ["/branch-return"];
	if (options?.mode === "without_summary") {
		parts.push("--without-summary");
	} else if (options?.mode === "result" && options.result?.trim()) {
		parts.push("--manual-summary", quoteCommandArg(options.result.trim()));
	} else if (options?.focus?.trim()) {
		parts.push("--focused-summary", quoteCommandArg(options.focus.trim()));
	} else if (options?.mode === "summary") {
		parts.push("--auto-summary");
	}
	return parts.join(" ");
}

function suggestBranchReturnInEditor(ctx: ExtensionContext, options?: { mode?: "summary" | "without_summary" | "result"; focus?: string; result?: string }) {
	if (!ctx.hasUI) return false;
	const existing = ctx.ui.getEditorText();
	const prefix = existing.trim() ? "\n" : "";
	ctx.ui.pasteToEditor(`${prefix}${buildBranchReturnCommand(options)}`);
	return true;
}

function parseBranchReturnArgs(args: string): { mode: "summary" | "without_summary" | "result"; focus?: string; result?: string } | { error: string } {
	const trimmed = args.trim();
	if (!trimmed) return { mode: "summary" };

	let tokens: string[];
	try {
		tokens = tokenizeCommandArgs(trimmed);
	} catch (error) {
		return { error: error instanceof Error ? error.message : "Failed to parse /branch-return arguments." };
	}

	let mode: "summary" | "without_summary" | "result" | undefined;
	let focus: string | undefined;
	let result: string | undefined;

	for (let i = 0; i < tokens.length; i++) {
		const token = tokens[i];
		if (token === "--auto-summary") {
			if (mode) return { error: "Use exactly one of --auto-summary, --focused-summary, --without-summary, or --manual-summary." };
			mode = "summary";
			continue;
		}
		if (token === "--without-summary") {
			if (mode) return { error: "Use exactly one of --auto-summary, --focused-summary, --without-summary, or --manual-summary." };
			mode = "without_summary";
			continue;
		}
		if (token === "--focused-summary") {
			if (mode) return { error: "Use exactly one of --auto-summary, --focused-summary, --without-summary, or --manual-summary." };
			const value = tokens[++i];
			if (!value) return { error: "--focused-summary requires text." };
			focus = value;
			mode = "summary";
			continue;
		}
		if (token === "--manual-summary") {
			if (mode) return { error: "Use exactly one of --auto-summary, --focused-summary, --without-summary, or --manual-summary." };
			const value = tokens[++i];
			if (!value) return { error: "--manual-summary requires text." };
			result = value;
			mode = "result";
			continue;
		}
		return { error: `Unknown /branch-return argument: ${token}` };
	}

	return {
		mode: mode ?? "summary",
		focus: focus?.trim() || undefined,
		result: result?.trim() || undefined,
	};
}

function formatBranchPrompt(prompt: string) {
	return `${BRANCH_PROMPT_PREFIX}\n\n${prompt}`;
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

function getStateAgent(ctx: ExtensionContext, state: BranchState): AgentConfig | undefined {
	if (!state.agentName) return undefined;
	return discoverAgents(ctx.cwd, "project").agents.find((agent) => agent.name === state.agentName);
}

function startBranch(
	pi: ExtensionAPI,
	ctx: ExtensionContext,
	prompt: string,
	options?: { agentName?: string; agentScope?: AgentScope; deliverAs?: "followUp" | "steer"; contextMode?: BranchContextMode; deferPrompt?: boolean },
): { ok: true; originId: string; prompt: string; agentName?: string; state: BranchState; contextBaseEntryId: string } | { ok: false; error: string } {
	if (isSubagentProcess()) return { ok: false, error: "tree-excursions is disabled inside subprocess subagents." };

	const currentLeafId = ctx.sessionManager.getLeafId();
	if (!currentLeafId) {
		return { ok: false, error: "Cannot start a branch before the session has a tree entry." };
	}

	const agentScope = options?.agentScope ?? "project";
	const resolved = resolveAgent(ctx, options?.agentName, agentScope);
	if (resolved.error) return { ok: false, error: resolved.error };

	const originId = appendBranchAnchorIfNeeded(pi, ctx, currentLeafId);
	const state = appendBranchStartState(pi, ctx, originId, resolved.agent?.name, options?.contextMode);
	pi.setLabel(originId, ORIGIN_LABEL);
	const contextBaseEntryId = ctx.sessionManager.getLeafId();
	if (!contextBaseEntryId) return { ok: false, error: "Failed to identify branch context base entry." };
	refreshBranchState(pi, ctx);
	if (!options?.deferPrompt) {
		pi.sendUserMessage(formatBranchPrompt(prompt), options?.deliverAs ? { deliverAs: options.deliverAs } : undefined);
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

const ExcursionStartParams = Type.Object({
	prompt: Type.String({ description: "Task prompt to run on a visible temporary session-tree branch." }),
	agent: Type.Optional(
		Type.String({
			description:
				"Optional project-local agent profile name from .pi/agents, e.g. william or worker. The profile description and instructions are injected into the branch system prompt; no subprocess is spawned.",
		}),
	),
});

const ExcursionReturnParams = Type.Object({
	auto_summary: Type.Optional(Type.Boolean({ description: "Use the default automatic branch summary return. Use exactly one return-style parameter." })),
	focused_summary: Type.Optional(Type.String({ description: "Automatic branch summary return with extra focus guidance. Use exactly one return-style parameter." })),
	without_summary: Type.Optional(Type.Boolean({ description: "Return without preserving branch context. Use exactly one return-style parameter." })),
	manual_summary: Type.Optional(Type.String({ description: "Manual summary text to carry back instead of generating one automatically. Use exactly one return-style parameter." })),
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
				pi.sendUserMessage(formatBranchPrompt(prompt));
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
				pi.sendUserMessage(formatBranchPrompt(prompt));
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

async function returnFromBranch(pi: ExtensionAPI, ctx: BranchReturnContext, forget: boolean, focus?: string, resultText?: string): Promise<{ ok: true; cancelled: boolean } | { ok: false; error: string }> {
	const state = readBranchState(ctx);
	if (!state) {
		notify(ctx, "No active branch found.", "warning");
		return { ok: false, error: "No active branch found." };
	}

	if (!ctx.sessionManager.getEntry(state.originId)) {
		refreshBranchState(pi, ctx);
		const error = `Stored branch origin ${state.originId} no longer exists.`;
		notify(ctx, error, "error");
		return { ok: false, error };
	}

	if (typeof ctx.navigateTree !== "function") {
		const error = "Branch return requires a context with navigateTree().";
		notify(ctx, error, "error");
		return { ok: false, error };
	}

	if (typeof ctx.waitForIdle === "function") await ctx.waitForIdle();
	const manualSummary = resultText?.trim();
	const returnMessage = forget
		? `Returning to branch origin ${state.originId} without summary...`
		: manualSummary
			? `Returning to branch origin ${state.originId} with manual summary...`
			: `Returning to branch origin ${state.originId} with branch summary...`;
	if (forget || !ctx.hasUI) notify(ctx, returnMessage, "info");

	const oldLeafId = ctx.sessionManager.getLeafId();
	if (!forget && manualSummary) {
		pendingManualReturnSummary = {
			startEntryId: state.startEntryId,
			targetId: state.originId,
			oldLeafId,
			summary: manualSummary,
		};
	}

	const navigate = () =>
		ctx.navigateTree!(
			state.originId,
			forget
				? undefined
				: {
						summarize: true,
						customInstructions: manualSummary ? undefined : defaultBranchReturnInstructions(focus),
						label: RETURN_LABEL,
					},
		);

	let result: Awaited<ReturnType<NonNullable<BranchReturnContext["navigateTree"]>>>;
	try {
		result =
			!forget && ctx.hasUI
				? await ctx.ui.custom<Awaited<ReturnType<NonNullable<BranchReturnContext["navigateTree"]>>>>((tui, theme, _keybindings, done) => {
						const loader = new BorderedLoader(tui, theme, returnMessage);
						navigate()
							.then(done)
							.catch((error) => {
								notify(ctx, error instanceof Error ? error.message : "Branch return failed.", "error");
								done({ cancelled: true });
							});
						return loader;
					})
				: await navigate();
	} finally {
		if (pendingManualReturnSummary?.startEntryId === state.startEntryId && pendingManualReturnSummary.oldLeafId === oldLeafId && pendingManualReturnSummary.targetId === state.originId) {
			pendingManualReturnSummary = undefined;
		}
	}

	refreshBranchState(pi, ctx);
	notify(ctx, result.cancelled ? "/branch-return cancelled." : "Returned from branch.", result.cancelled ? "warning" : "info");
	return { ok: true, cancelled: result.cancelled };
}

async function showBranchReturnMenu(pi: ExtensionAPI, ctx: ExtensionCommandContext) {
	const state = refreshBranchState(pi, ctx);

	if (!state) {
		notify(ctx, "No active branch found.", "warning");
		return;
	}

	const choice = await ctx.ui.select("Branch Return", [
		"Auto summary",
		"Focused summary...",
		"Manual summary...",
		"Without summary",
	]);
	if (!choice) return;

	if (choice === "Auto summary") {
		await returnFromBranch(pi, ctx, false);
		return;
	}
	if (choice === "Focused summary...") {
		const focus = await inputBranchPrompt(ctx, "Focused branch summary");
		if (!focus) {
			notify(ctx, "/branch-return cancelled: no summary focus entered.", "info");
			return;
		}
		await returnFromBranch(pi, ctx, false, focus);
		return;
	}
	if (choice === "Manual summary...") {
		const summary = await inputBranchPrompt(ctx, "Manual branch summary");
		if (!summary) {
			notify(ctx, "/branch-return cancelled: no manual summary entered.", "info");
			return;
		}
		await returnFromBranch(pi, ctx, false, undefined, summary);
		return;
	}
	if (choice === "Without summary") {
		await returnFromBranch(pi, ctx, true);
	}
}

export default function treeExcursionsExtension(pi: ExtensionAPI) {
	pi.on("session_start", async (_event, ctx) => {
		if (isSubagentProcess()) return;
		refreshBranchState(pi, ctx);
	});

	pi.on("session_before_tree", async (event) => {
		if (isSubagentProcess()) return;
		const pending = pendingManualReturnSummary;
		if (!pending) return;
		if (!event.preparation.userWantsSummary) return;
		if (event.preparation.targetId !== pending.targetId || event.preparation.oldLeafId !== pending.oldLeafId) return;

		pendingManualReturnSummary = undefined;
		return {
			summary: {
				summary: pending.summary,
				details: {
					customType: CUSTOM_TYPE,
					mode: "manual_summary",
					startEntryId: pending.startEntryId,
					targetId: pending.targetId,
					oldLeafId: pending.oldLeafId,
					timestamp: new Date().toISOString(),
				},
			},
			label: RETURN_LABEL,
		};
	});

	pi.on("session_tree", async (_event, ctx) => {
		if (isSubagentProcess()) return;
		refreshBranchState(pi, ctx);
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
		const state = refreshBranchState(pi, ctx);
		if (!state?.agentName) return;

		const agent = getStateAgent(ctx, state);
		if (!agent) return;

		return {
			systemPrompt: event.systemPrompt + buildAgentSystemPrompt(agent),
		};
	});

	pi.registerTool({
		name: "excursion_start",
		label: "Excursion Start",
		description: [
			"Start a visible temporary branch task in the current Pi session tree.",
			"Use when a subagent-style investigation is helpful but true parallel subprocess isolation is not required.",
			"This queues the branch task; the user must later run /branch-return to summarize the branch and return to the origin.",
			"Nested branches are allowed; the closest branch start on the current session path determines active branch behavior.",
			"Optionally provide a project-local agent profile name from .pi/agents to inject that agent's description and instructions into the branch system prompt without spawning a subprocess.",
		].join(" "),
		promptSnippet: "excursion_start: start a branch task; user later runs /branch-return to summarize and return.",
		promptGuidelines: [
			"Prefer excursion_start over subprocess subagent delegation when the work should remain visible and inspectable in /tree and true parallelism is not needed.",
			"excursion_start may be used inside an active branch; the new nested branch becomes active while its path is current.",
			"After starting an excursion branch, tell the user they can inspect it with /tree and should run /branch-return when they want to summarize and come back.",
		],
		parameters: ExcursionStartParams,
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
						text: `Started branch from ${result.originId}${agentText}. The branch task has been queued; run /branch-return when ready to summarize and return.`,
					},
				],
			};
		},
	});

	pi.registerTool({
		name: "excursion_return",
		label: "Excursion Return",
		description: "When the purpose of the active branch exploration has been achieved, call this tool to return to the parent branch.",
		promptSnippet: "excursion_return: return from the active branch to the parent branch.",
		promptGuidelines: [
			"Use excursion_return when the active branch exploration is complete and the result should be carried back to the parent branch.",
			"Call excursion_return when the user asks to return from, end, close, finish, or summarize the active branch.",
			"Use exactly one of these return-style parameters: auto_summary, focused_summary, without_summary, or manual_summary. Do not combine them in the same tool call.",
			"Use auto_summary for the default generated return summary, focused_summary when the generated summary should emphasize specific points, without_summary only when the user asked to return without preserving branch context, and manual_summary only when you can directly provide the summary text to carry back.",
			"The user is shown the tool result directly, so do not repeat routine operational details from the tool output unless extra explanation is actually needed.",
		],
		parameters: ExcursionReturnParams,
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const state = readBranchState(ctx);
			if (!state) {
				return { content: [{ type: "text", text: "No active branch found." }], isError: true };
			}

			const selectedModes = [params.auto_summary === true, typeof params.focused_summary === "string", params.without_summary === true, typeof params.manual_summary === "string"].filter(Boolean).length;
			if (selectedModes > 1) {
				return { content: [{ type: "text", text: "Use exactly one of auto_summary, focused_summary, without_summary, or manual_summary." }], isError: true };
			}

			const mode = params.without_summary ? "without_summary" : typeof params.manual_summary === "string" ? "result" : "summary";
			const focusText = typeof params.focused_summary === "string" ? params.focused_summary.trim() : undefined;
			const resultText = typeof params.manual_summary === "string" ? params.manual_summary.trim() : undefined;
			if (typeof params.focused_summary === "string" && !focusText) {
				return { content: [{ type: "text", text: "focused_summary requires text." }], isError: true };
			}
			if (typeof params.manual_summary === "string" && !resultText) {
				return { content: [{ type: "text", text: "manual_summary requires text." }], isError: true };
			}
			if (typeof (ctx as BranchReturnContext).navigateTree !== "function") {
				const inserted = suggestBranchReturnInEditor(ctx, { mode, focus: focusText, result: resultText });
				const command = buildBranchReturnCommand({ mode, focus: focusText, result: resultText });
				const text = inserted ? `Inserted ${command} into the editor. Press Enter.` : `Run ${command}.`;
				return { content: [{ type: "text", text }] };
			}
			const result = await returnFromBranch(pi, ctx, mode === "without_summary", focusText, resultText);
			if (!result.ok) {
				return { content: [{ type: "text", text: result.error }], isError: true };
			}
			return {
				content: [
					{
						type: "text",
						text: result.cancelled
							? "Branch return was cancelled."
							: mode === "without_summary"
								? "Returned from branch without summary."
								: mode === "result"
									? "Returned from branch with manual summary."
									: focusText
										? "Returned from branch with focused summary."
										: "Returned from branch with automatic summary.",
					},
				],
			};
		},
	});

	pi.registerCommand("branch", {
		description: "Start a visible session-tree branch",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			if (isSubagentProcess()) return;
			if (args.trim()) {
				notify(ctx, "Run /branch with no arguments to start a branch.", "warning");
				return;
			}
			await startBranchFromMenu(pi, ctx);
		},
	});

	pi.registerCommand("branch-return", {
		description: "Return from the nearest active session-tree branch",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			if (isSubagentProcess()) return;
			const parsed = parseBranchReturnArgs(args);
			if ("error" in parsed) {
				notify(ctx, parsed.error, "warning");
				return;
			}
			if (!args.trim()) {
				await showBranchReturnMenu(pi, ctx);
				return;
			}
			const result = await returnFromBranch(pi, ctx, parsed.mode === "without_summary", parsed.focus, parsed.result);
			if (!result.ok) return;
		},
	});
}
