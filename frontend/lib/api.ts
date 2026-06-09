import {mockDashboardData} from "./mock";
import type {DashboardData} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

async function safeJson<T>(path: string): Promise<T | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1500);
  try {
    const response = await fetch(`${API_BASE}${path}`, {cache: "no-store", signal: controller.signal});
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

export async function loadDashboardData(): Promise<DashboardData> {
  const [matches, tournament, health, modelRun] = await Promise.all([
    safeJson<{matches: DashboardData["matches"]}>("/api/matches"),
    safeJson<DashboardData["tournament"]>("/api/tournament/probabilities"),
    safeJson<{sources: DashboardData["sources"]}>("/api/source-health"),
    safeJson<DashboardData["modelRun"]>("/api/model-runs/latest")
  ]);

  if (!matches || !tournament || !health || !modelRun) {
    return mockDashboardData;
  }

  return {
    matches: matches.matches,
    tournament,
    sources: health.sources,
    modelRun
  };
}
