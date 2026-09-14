import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { StringEnum } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { fileURLToPath } from "node:url";

const API_BASE = "https://api.track.toggl.com/api/v9";
const ENV_FILE = fileURLToPath(new URL(".env", import.meta.url));
const CREATED_WITH = "parker-pi";

type Project = {
  id: number;
  name: string;
  workspace_id: number;
  active?: boolean;
};

type TimeEntry = {
  id: number;
  description?: string;
  project_id?: number | null;
  start: string;
  stop?: string | null;
  duration: number;
};

type TogglConfig = {
  token: string;
  workspaceId?: number;
};

function parseDotEnv(text: string): Record<string, string> {
  const values: Record<string, string> = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const match = line.match(/^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (!match) continue;
    let value = match[2].trim();
    if ((value.startsWith("\"") && value.endsWith("\"")) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    } else {
      value = value.replace(/\s+#.*$/, "").trim();
    }
    values[match[1]] = value;
  }
  return values;
}

async function loadConfig(): Promise<TogglConfig> {
  const { readFile } = await import("node:fs/promises");
  let fileValues: Record<string, string> = {};
  try {
    fileValues = parseDotEnv(await readFile(ENV_FILE, "utf8"));
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error ? error.code : undefined;
    if (code !== "ENOENT") throw error;
  }

  const token = process.env.TOGGL_API_TOKEN ?? fileValues.TOGGL_API_TOKEN;
  if (!token) {
    throw new Error(`Missing TOGGL_API_TOKEN in ${ENV_FILE}.`);
  }

  const workspaceRaw = process.env.TOGGL_WORKSPACE_ID ?? fileValues.TOGGL_WORKSPACE_ID;
  return {
    token,
    workspaceId: workspaceRaw ? Number(workspaceRaw) : undefined,
  };
}

async function togglRequest<T>(config: TogglConfig, path: string, init: RequestInit = {}): Promise<T> {
  const auth = Buffer.from(`${config.token}:api_token`).toString("base64");
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Basic ${auth}`,
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Toggl API ${response.status}: ${body || response.statusText}`);
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

async function getWorkspaceId(config: TogglConfig): Promise<number> {
  if (config.workspaceId && Number.isFinite(config.workspaceId)) return config.workspaceId;
  const workspaces = await togglRequest<Array<{ id: number; name: string }>>(config, "/me/workspaces");
  if (workspaces.length === 0) throw new Error("No Toggl workspaces found for this account.");
  if (workspaces.length > 1) {
    throw new Error(`Multiple Toggl workspaces found. Set TOGGL_WORKSPACE_ID in ${ENV_FILE}.`);
  }
  return workspaces[0].id;
}

async function listProjects(config: TogglConfig): Promise<Project[]> {
  const workspaceId = await getWorkspaceId(config);
  return togglRequest<Project[]>(config, `/workspaces/${workspaceId}/projects?active=true`);
}

async function currentEntry(config: TogglConfig): Promise<TimeEntry | null> {
  return togglRequest<TimeEntry | null>(config, "/me/time_entries/current");
}

function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m ${secs}s`;
}

function projectLabel(project: Project): string {
  return `${project.name} (${project.id})`;
}

async function startTimer(projectName: string, description: string | undefined): Promise<string> {
  const config = await loadConfig();
  const active = await currentEntry(config);
  if (active) {
    throw new Error(`A timer is already running${active.description ? `: ${active.description}` : ""}. Stop it before starting another.`);
  }

  const projects = await listProjects(config);
  const normalized = projectName.trim().toLocaleLowerCase();
  const matches = projects.filter((project) => project.name.toLocaleLowerCase() === normalized);
  if (matches.length === 0) {
    const suggestions = projects.slice(0, 20).map(projectLabel).join(", ");
    throw new Error(`Project not found: ${projectName}. Available projects: ${suggestions}`);
  }
  if (matches.length > 1) throw new Error(`More than one project matches ${projectName}. Use its exact unique name.`);

  const project = matches[0];
  const entry = await togglRequest<TimeEntry>(config, `/workspaces/${project.workspace_id}/time_entries`, {
    method: "POST",
    body: JSON.stringify({
      workspace_id: project.workspace_id,
      project_id: project.id,
      description: description?.trim() || project.name,
      start: new Date().toISOString(),
      duration: -1,
      created_with: CREATED_WITH,
    }),
  });
  return `Started ${project.name}${entry.description ? ` — ${entry.description}` : ""}.`;
}

async function stopTimer(): Promise<string> {
  const config = await loadConfig();
  const active = await currentEntry(config);
  if (!active) return "No Toggl timer is currently running.";

  const stop = new Date();
  const startMs = Date.parse(active.start);
  const duration = Number.isFinite(startMs) ? Math.max(0, Math.floor((stop.getTime() - startMs) / 1000)) : 0;
  const workspaceId = await getWorkspaceId(config);
  await togglRequest(config, `/workspaces/${workspaceId}/time_entries/${active.id}`, {
    method: "PUT",
    body: JSON.stringify({
      description: active.description ?? "",
      project_id: active.project_id ?? null,
      start: active.start,
      stop: stop.toISOString(),
      duration,
    }),
  });
  return `Stopped${active.description ? ` ${active.description}` : ""} after ${formatDuration(duration)}.`;
}

async function statusTimer(): Promise<string> {
  const config = await loadConfig();
  const active = await currentEntry(config);
  if (!active) return "No Toggl timer is currently running.";
  const elapsed = Math.floor((Date.now() - Date.parse(active.start)) / 1000);
  const project = active.project_id == null
    ? undefined
    : (await listProjects(config)).find((candidate) => candidate.id === active.project_id);
  const projectName = project?.name ?? "Unknown project";
  return `${projectName} running (${formatDuration(elapsed)}).`;
}

async function projectsStatus(): Promise<string> {
  const config = await loadConfig();
  const projects = await listProjects(config);
  return projects.map(projectLabel).join("\n") || "No active Toggl projects found.";
}

async function runTrack(args: string): Promise<string> {
  const trimmed = args.trim();
  const [action, ...rest] = trimmed.split(/\s+/);
  switch ((action || "status").toLocaleLowerCase()) {
    case "start": {
      if (!rest.length) throw new Error("Usage: /track start <project name> [description]");
      // Project names may contain spaces. A pipe provides an unambiguous description separator.
      const input = rest.join(" ");
      const [project, description] = input.split(/\s*\|\s*/, 2);
      return startTimer(project, description);
    }
    case "stop": return stopTimer();
    case "status": return statusTimer();
    case "list":
    case "projects": return projectsStatus();
    default: throw new Error("Usage: /track start <project> [| description], /track stop, /track status, or /track list");
  }
}

function showResult(ctx: ExtensionContext | ExtensionCommandContext, text: string): void {
  ctx.ui.notify(text, "info");
}

export default function togglTrack(pi: ExtensionAPI) {
  pi.registerCommand("track", {
    description: "Toggl timer: start | stop | status | list",
    getArgumentCompletions: (prefix) => {
      const normalized = prefix.trim().toLocaleLowerCase();
      if (prefix.endsWith(" ") || normalized.includes(" ")) return null;

      const actions = [
        { value: "start ", label: "start", description: "Start a timer for an exact project name" },
        { value: "stop", label: "stop", description: "Stop the running timer" },
        { value: "status", label: "status", description: "Show the running timer" },
        { value: "list", label: "list", description: "List active Toggl projects" },
      ];
      const matches = actions.filter((item) => item.label.startsWith(normalized));
      return matches.length ? matches : null;
    },
    handler: async (args, ctx) => {
      try {
        showResult(ctx, await runTrack(args));
      } catch (error) {
        ctx.ui.notify(error instanceof Error ? error.message : String(error), "error");
      }
    },
  });

  pi.registerTool({
    name: "toggl_track",
    label: "Toggl Track",
    description: "Start, stop, inspect, or list the user's Toggl Track timer. Starting requires an exact active Toggl project name.",
    parameters: Type.Object({
      action: StringEnum(["start", "stop", "status", "list"] as const),
      project: Type.Optional(Type.String({ description: "Exact Toggl project name; required for start" })),
      description: Type.Optional(Type.String({ description: "Optional time-entry description" })),
    }),
    async execute(_toolCallId, params) {
      try {
        let result: string;
        if (params.action === "start") {
          if (!params.project) throw new Error("project is required when action is start");
          result = await startTimer(params.project, params.description);
        } else if (params.action === "stop") {
          result = await stopTimer();
        } else if (params.action === "list") {
          result = await projectsStatus();
        } else {
          result = await statusTimer();
        }
        return { content: [{ type: "text", text: result }], details: {} };
      } catch (error) {
        throw error instanceof Error ? error : new Error(String(error));
      }
    },
  });
}
