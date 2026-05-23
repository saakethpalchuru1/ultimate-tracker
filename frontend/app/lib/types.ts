export type Team = { id: string; name: string; seed: number; pool: string };
export type Game = {
  game_id: string;
  pool: string;
  team1: string;
  team2: string;
  score1: number | null;
  score2: number | null;
  status: "final" | "in_progress" | "scheduled";
  scheduled_at?: string | null;
  field?: string | null;
};

export type StandingRow = {
  team_id: string;
  wins: number;
  losses: number;
  pf: number;
  pa: number;
  pd: number;
};

export type PoolStandingPayload = {
  pool: string;
  ordered_team_ids: string[];
  rows: Record<string, StandingRow>;
  tiebreak_trace: Array<{
    rule: number;
    tied_team_ids: string[];
    metric_values: Record<string, number>;
    outcome: "split" | "all_still_tied" | "single_team";
    note?: string;
  }>;
  usau_tie_hints?: Record<string, string>;
};

export type CurrentSnapshot = {
  tournament_id: string;
  name: string;
  division: string;
  target_team_id: string;
  generated_at: string;
  teams: Team[];
  pools: { name: string; team_ids: string[] }[];
  games: Game[];
  standings: PoolStandingPayload[];
};

export type Permutation = {
  id: number;
  assumed_outcomes: Array<{
    game_id: string;
    winner_id: string;
    loser_id: string;
    winning_margin: number;
  }>;
  final_order: string[];
  margin_sensitive: boolean;
  target_finish?: number;
};

export type ScenariosSnapshot = {
  pools: Record<string, { pool: string; n_remaining: number; n_permutations: number; permutations: Permutation[] }>;
  target_summary?: {
    target_team_id: string;
    finish_distribution: Record<number, number>;
    scenarios_by_finish: Record<string, Permutation[]>;
  };
};

export type BracketSnapshot = {
  bracket_id: string;
  rounds: Array<{
    name: string;
    games: Array<{
      id: string;
      round: string;
      participants: Array<{ side: string; team_id: string | null; source: string }>;
      projected_winner: string | null;
    }>;
  }>;
  target_path?: Array<{
    round: string;
    game_id: string;
    opponent_team_id: string | null;
    opponent_source: string | null;
  }>;
};

export type LiveSnapshot = {
  target_team_id: string;
  target_pool: string;
  has_live_games: boolean;
  live_games: Array<{
    game_id: string;
    target_team_id: string;
    opponent_id: string;
    current: { target_score: number; opponent_score: number; target_lead_by: number };
    scheduled_at?: string | null;
    field?: string | null;
    summary: Array<{
      finish: number;
      achievable_min_margin: number | null;
      guaranteed_at_or_above_margin: number | null;
      current_margin: number;
      margin_delta_needed: number | null;
    }>;
    matrix: Array<{
      combo: string;
      target_final_margin: number;
      target_finish: number;
    }>;
  }>;
};
