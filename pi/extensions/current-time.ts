import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

function getCurrentTimeLine(now = new Date()): string {
	const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "local";
	const offsetMinutes = -now.getTimezoneOffset();
	const offsetSign = offsetMinutes >= 0 ? "+" : "-";
	const offsetAbsolute = Math.abs(offsetMinutes);
	const offsetHours = String(Math.floor(offsetAbsolute / 60)).padStart(2, "0");
	const offsetMins = String(offsetAbsolute % 60).padStart(2, "0");

	const parts = new Intl.DateTimeFormat("en-US", {
		hour: "2-digit",
		minute: "2-digit",
		second: "2-digit",
		hour12: false,
		hourCycle: "h23",
		timeZoneName: "short",
	}).formatToParts(now);

	const part = (type: Intl.DateTimeFormatPartTypes) =>
		parts.find((entry) => entry.type === type)?.value;

	const hour = part("hour") || String(now.getHours()).padStart(2, "0");
	const minute = part("minute") || String(now.getMinutes()).padStart(2, "0");
	const second = part("second") || String(now.getSeconds()).padStart(2, "0");
	const timeZoneName = part("timeZoneName") || "local";

	return `Current time: ${hour}:${minute}:${second} ${timeZone} (${timeZoneName}, UTC${offsetSign}${offsetHours}:${offsetMins})`;
}

function injectCurrentTime(systemPrompt: string, currentTimeLine: string): string {
	const existingCurrentTimeLine = /^Current time: .*$/m;
	if (existingCurrentTimeLine.test(systemPrompt)) {
		return systemPrompt.replace(existingCurrentTimeLine, currentTimeLine);
	}

	const currentDateLine = /^(Current date: .*)$/m;
	if (currentDateLine.test(systemPrompt)) {
		return systemPrompt.replace(currentDateLine, (_match, dateLine) => `${dateLine}\n${currentTimeLine}`);
	}

	return `${systemPrompt.trimEnd()}\n${currentTimeLine}`;
}

export default function currentTimeExtension(pi: ExtensionAPI) {
	pi.on("before_agent_start", async (event) => {
		return {
			systemPrompt: injectCurrentTime(event.systemPrompt, getCurrentTimeLine()),
		};
	});
}
