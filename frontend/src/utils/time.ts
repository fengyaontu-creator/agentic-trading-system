export function parseTimestamp(ts: string): Date {
  const hasExplicitOffset = /(?:Z|[+-]\d{2}:\d{2})$/.test(ts);
  const normalized = hasExplicitOffset ? ts : `${ts}Z`;
  return new Date(normalized);
}


export function formatLocal(ts: string): string {
  const date = parseTimestamp(ts);
  const parts = new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZoneName: "short",
  }).formatToParts(date);
  const valueOf = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${valueOf("month")}/${valueOf("day")}/${valueOf("year")} ${valueOf("hour")}:${valueOf("minute")}:${valueOf("second")} ${valueOf("timeZoneName")}`.trim();
}


export function formatET(ts: string): string {
  const date = parseTimestamp(ts);
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    month: "numeric",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date) + " ET";
}


export function localTimeForET(hour: number, minute: number): string {
  const now = new Date();
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZoneName: "shortOffset",
  }).formatToParts(now);

  const valueOf = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  const offsetText = valueOf("timeZoneName");
  const match = offsetText.match(/GMT([+-])(\d{1,2})(?::(\d{2}))?/);
  const sign = match?.[1] === "-" ? -1 : 1;
  const offsetHours = Number(match?.[2] ?? "0");
  const offsetMinutes = Number(match?.[3] ?? "0");
  const offsetTotalMinutes = sign * (offsetHours * 60 + offsetMinutes);

  const utcMillis =
    Date.UTC(
      Number(valueOf("year")),
      Number(valueOf("month")) - 1,
      Number(valueOf("day")),
      hour,
      minute,
      0
    ) - offsetTotalMinutes * 60 * 1000;

  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(utcMillis));
}
