import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Award,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Coins,
  Gift,
  History,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Star,
  Trophy,
  X,
  Zap,
} from "lucide-react";

import { api } from "../../../api";

// ==========================================================
// Types
// ==========================================================

type LoyaltyTier = "BRONZE" | "SILVER" | "GOLD" | "PLATINUM";

interface LoyaltyAccount {
  id?: number;
  customer_id?: number;
  points_balance?: number;
  lifetime_points?: number;
  tier?: LoyaltyTier | string;
  is_active?: boolean;
}

interface LoyaltyReward {
  id: number;
  name: string;
  description?: string | null;
  reward_type?: string | null;
  points_cost: number;
  monetary_value?: number | string | null;
  status?: string | null;
  is_active?: boolean;
  minimum_tier?: LoyaltyTier | string | null;
  valid_from?: string | null;
  valid_until?: string | null;
}

interface LoyaltyPointTransaction {
  id: number;
  transaction_type?: string | null;
  points?: number | null;
  balance_after?: number | null;
  reference_type?: string | null;
  reference_id?: number | null;
  description?: string | null;
  created_at?: string | null;
}

interface RewardRedemption {
  id: number;
  redemption_reference?: string | null;
  reward_id?: number | null;
  points_spent?: number | null;
  status?: string | null;
  used_at?: string | null;
  expires_at?: string | null;
  description?: string | null;
  created_at?: string | null;
  reward?: LoyaltyReward | null;
}

type Tab = "overview" | "rewards" | "redemptions" | "activity";

// ==========================================================
// Constants
// ==========================================================

const TIER_THRESHOLDS: Record<LoyaltyTier, number> = {
  BRONZE: 0,
  SILVER: 1000,
  GOLD: 5000,
  PLATINUM: 10000,
};

const TIER_ORDER: LoyaltyTier[] = ["BRONZE", "SILVER", "GOLD", "PLATINUM"];

// ==========================================================
// Helpers
// ==========================================================

function unwrap<T>(response: any): T {
  return response?.data ?? response;
}

function toNumber(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function points(value: unknown): string {
  return toNumber(value).toLocaleString("en-KE");
}

function money(value: unknown): string {
  return `KES ${toNumber(value).toLocaleString("en-KE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function dateTime(value?: string | null): string {
  if (!value) return "—";

  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;

  return d.toLocaleString("en-KE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function dateOnly(value?: string | null): string {
  if (!value) return "—";

  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;

  return d.toLocaleDateString("en-KE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function label(value?: string | null): string {
  if (!value) return "—";

  return value
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function normalizeTier(value?: string | null): LoyaltyTier {
  const tier = String(value ?? "BRONZE").toUpperCase();

  if (tier === "SILVER" || tier === "GOLD" || tier === "PLATINUM") {
    return tier;
  }

  return "BRONZE";
}

function tierIcon(tier: LoyaltyTier) {
  if (tier === "PLATINUM") return Sparkles;
  if (tier === "GOLD") return Trophy;
  if (tier === "SILVER") return Award;
  return Star;
}

function tierDescription(tier: LoyaltyTier): string {
  switch (tier) {
    case "PLATINUM":
      return "Premium SmartPark loyalty member.";
    case "GOLD":
      return "Enjoy enhanced SmartPark rewards.";
    case "SILVER":
      return "You're building a strong SmartPark reward balance.";
    default:
      return "Start earning points with SmartPark.";
  }
}

function nextTier(tier: LoyaltyTier): LoyaltyTier | null {
  const index = TIER_ORDER.indexOf(tier);
  return index >= 0 && index < TIER_ORDER.length - 1
    ? TIER_ORDER[index + 1]
    : null;
}

function getProgress(lifetimePoints: number, tier: LoyaltyTier) {
  const next = nextTier(tier);

  if (!next) {
    return {
      percentage: 100,
      remaining: 0,
      nextTier: null as LoyaltyTier | null,
    };
  }

  const currentThreshold = TIER_THRESHOLDS[tier];
  const nextThreshold = TIER_THRESHOLDS[next];
  const range = nextThreshold - currentThreshold;
  const earnedInRange = lifetimePoints - currentThreshold;

  return {
    percentage:
      range > 0
        ? Math.min(100, Math.max(0, (earnedInRange / range) * 100))
        : 100,
    remaining: Math.max(0, nextThreshold - lifetimePoints),
    nextTier: next,
  };
}

function errorMessage(error: any): string {
  const detail = error?.response?.data?.detail;

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg ?? String(item)).join(", ");
  }

  return (
    error?.response?.data?.message ??
    error?.message ??
    "Unable to complete the request."
  );
}

// ==========================================================
// Component
// ==========================================================

export default function Loyalty() {
  const [account, setAccount] = useState<LoyaltyAccount | null>(null);
  const [balance, setBalance] = useState(0);
  const [lifetimePoints, setLifetimePoints] = useState(0);
  const [tier, setTier] = useState<LoyaltyTier>("BRONZE");

  const [history, setHistory] = useState<LoyaltyPointTransaction[]>([]);
  const [rewards, setRewards] = useState<LoyaltyReward[]>([]);
  const [redemptions, setRedemptions] = useState<RewardRedemption[]>([]);

  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedReward, setSelectedReward] = useState<LoyaltyReward | null>(
    null,
  );
  const [redeeming, setRedeeming] = useState(false);
  const [showRedeemModal, setShowRedeemModal] = useState(false);

  const [success, setSuccess] = useState<{
    reference?: string;
    remainingPoints?: number;
    reward?: LoyaltyReward;
  } | null>(null);

  // --------------------------------------------------------
  // Load loyalty information
  // --------------------------------------------------------

  const loadLoyalty = useCallback(async (manualRefresh = false) => {
    if (manualRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    setError(null);

    try {
      const [
        accountResponse,
        balanceResponse,
        lifetimeResponse,
        tierResponse,
        historyResponse,
        rewardsResponse,
        redemptionsResponse,
      ] = await Promise.all([
        api.get<LoyaltyAccount>("/loyalty"),
        api.get<number>("/loyalty/balance"),
        api.get<number>("/loyalty/lifetime-points"),
        api.get<LoyaltyTier>("/loyalty/tier"),
        api.get<LoyaltyPointTransaction[]>("/loyalty/history", {
          params: { limit: 100, offset: 0 },
        }),
        api.get<LoyaltyReward[]>("/loyalty/rewards/eligible", {
          params: { limit: 100, offset: 0 },
        }),
        api.get<RewardRedemption[]>("/loyalty/reward-redemptions", {
          params: { limit: 100, offset: 0 },
        }),
      ]);

      const accountData = unwrap<LoyaltyAccount>(accountResponse.data);
      const balanceData = unwrap<any>(balanceResponse.data);
      const lifetimeData = unwrap<any>(lifetimeResponse.data);
      const tierData = unwrap<any>(tierResponse.data);

      setAccount(accountData);

      setBalance(
        toNumber(
          balanceData?.points_balance ??
            balanceData?.balance ??
            balanceData?.points ??
            balanceData,
        ),
      );

      setLifetimePoints(
        toNumber(
          lifetimeData?.lifetime_points ?? lifetimeData?.points ?? lifetimeData,
        ),
      );

      setTier(normalizeTier(tierData?.tier ?? tierData?.value ?? tierData));

      const historyData = unwrap<any>(historyResponse.data);
      setHistory(
        Array.isArray(historyData)
          ? historyData
          : (historyData?.items ??
              historyData?.transactions ??
              historyData?.results ??
              []),
      );

      const rewardsData = unwrap<any>(rewardsResponse.data);
      setRewards(
        Array.isArray(rewardsData)
          ? rewardsData
          : (rewardsData?.items ??
              rewardsData?.rewards ??
              rewardsData?.results ??
              []),
      );

      const redemptionData = unwrap<any>(redemptionsResponse.data);
      setRedemptions(
        Array.isArray(redemptionData)
          ? redemptionData
          : (redemptionData?.items ??
              redemptionData?.redemptions ??
              redemptionData?.results ??
              []),
      );
    } catch (err: any) {
      console.error("[SmartPark Loyalty] Failed to load loyalty data:", err);
      setError(errorMessage(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadLoyalty();
  }, [loadLoyalty]);

  // --------------------------------------------------------
  // Derived state
  // --------------------------------------------------------

  const currentBalance =
    account?.points_balance !== undefined
      ? toNumber(account.points_balance)
      : balance;

  const currentLifetimePoints =
    account?.lifetime_points !== undefined
      ? toNumber(account.lifetime_points)
      : lifetimePoints;

  const currentTier = account?.tier ? normalizeTier(account.tier) : tier;

  const progress = useMemo(
    () => getProgress(currentLifetimePoints, currentTier),
    [currentLifetimePoints, currentTier],
  );

  const TierIcon = tierIcon(currentTier);

  const recentHistory = history.slice(0, 5);

  const earnedPoints = history
    .filter((item) => toNumber(item.points) > 0)
    .reduce((sum, item) => sum + Math.max(0, toNumber(item.points)), 0);

  const redeemedPoints = history
    .filter((item) => toNumber(item.points) < 0)
    .reduce((sum, item) => sum + Math.abs(toNumber(item.points)), 0);

  const eligibleRewards = rewards.filter(
    (reward) => reward.is_active !== false,
  );

  // --------------------------------------------------------
  // Redemption
  // --------------------------------------------------------

  function openRedeem(reward: LoyaltyReward) {
    setSelectedReward(reward);
    setSuccess(null);
    setShowRedeemModal(true);
  }

  function closeRedeem() {
    if (redeeming) return;

    setShowRedeemModal(false);
    setSelectedReward(null);
    setSuccess(null);
  }

  async function redeemReward() {
    if (!selectedReward) return;

    setRedeeming(true);
    setError(null);

    try {
      const response = await api.post(
        `/loyalty/rewards/${selectedReward.id}/redeem`,
      );

      const result = unwrap<any>(response.data);
      const redemption = result?.redemption ?? result;

      setSuccess({
        reference:
          redemption?.redemption_reference ??
          redemption?.reference ??
          redemption?.id?.toString(),
        remainingPoints: toNumber(result?.remaining_points),
        reward: result?.reward ?? selectedReward,
      });

      await loadLoyalty(true);
    } catch (err: any) {
      console.error("[SmartPark Loyalty] Redemption failed:", err);
      setError(errorMessage(err));
    } finally {
      setRedeeming(false);
    }
  }

  // --------------------------------------------------------
  // Loading
  // --------------------------------------------------------

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="h-8 w-64 animate-pulse rounded bg-slate-200" />
            <div className="mt-2 h-4 w-96 animate-pulse rounded bg-slate-200" />
          </div>
          <div className="h-10 w-24 animate-pulse rounded-xl bg-slate-200" />
        </div>

        <div className="grid gap-5 md:grid-cols-3">
          {[1, 2, 3].map((item) => (
            <div
              key={item}
              className="h-40 animate-pulse rounded-2xl border border-slate-200 bg-white"
            />
          ))}
        </div>

        <div className="h-80 animate-pulse rounded-2xl border border-slate-200 bg-white" />
      </div>
    );
  }

  // --------------------------------------------------------
  // Render
  // --------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Header */}

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-emerald-50 text-emerald-600">
            <Trophy size={24} />
          </div>

          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
              Loyalty Programme
            </h1>

            <p className="mt-1 text-sm text-slate-500">
              Earn points, unlock rewards and get more from SmartPark.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => void loadLoyalty(true)}
          disabled={refreshing}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Error */}

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <ShieldCheck size={18} className="mt-0.5 shrink-0" />

          <div className="flex-1">
            <p className="font-bold">Unable to complete the loyalty request.</p>
            <p className="mt-1">{error}</p>
          </div>

          <button
            type="button"
            onClick={() => setError(null)}
            className="rounded-lg p-1 hover:bg-rose-100"
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* Summary cards */}

      <div className="grid gap-5 md:grid-cols-3">
        <MetricCard
          label="Available Points"
          value={points(currentBalance)}
          helper="Ready to redeem"
          icon={<Coins size={22} />}
          iconClass="text-emerald-600 bg-emerald-50"
        />

        <MetricCard
          label="Lifetime Points"
          value={points(currentLifetimePoints)}
          helper="Total points earned"
          icon={<Zap size={22} />}
          iconClass="text-blue-600 bg-blue-50"
        />

        <MetricCard
          label="Current Tier"
          value={label(currentTier)}
          helper={tierDescription(currentTier)}
          icon={<TierIcon size={22} />}
          iconClass="text-violet-600 bg-violet-50"
        />
      </div>

      {/* Tabs */}

      <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white p-1.5 shadow-sm">
        <div className="flex min-w-max gap-1">
          <TabButton
            active={tab === "overview"}
            onClick={() => setTab("overview")}
            icon={<Trophy size={16} />}
            text="Overview"
          />
          <TabButton
            active={tab === "rewards"}
            onClick={() => setTab("rewards")}
            icon={<Gift size={16} />}
            text="Rewards"
          />
          <TabButton
            active={tab === "redemptions"}
            onClick={() => setTab("redemptions")}
            icon={<Award size={16} />}
            text="My Rewards"
          />
          <TabButton
            active={tab === "activity"}
            onClick={() => setTab("activity")}
            icon={<History size={16} />}
            text="Points Activity"
          />
        </div>
      </div>

      {/* Overview */}

      {tab === "overview" && (
        <div className="space-y-6">
          {/* Tier progress */}

          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-3">
                <div className="grid h-10 w-10 place-items-center rounded-xl bg-violet-50 text-violet-600">
                  <TierIcon size={20} />
                </div>

                <div>
                  <p className="text-xs font-bold uppercase tracking-widest text-slate-400">
                    Your Loyalty Tier
                  </p>

                  <h2 className="text-xl font-extrabold text-slate-900">
                    {label(currentTier)}
                  </h2>
                </div>
              </div>

              {progress.nextTier ? (
                <div className="text-left sm:text-right">
                  <p className="text-xs font-bold uppercase tracking-widest text-slate-400">
                    Next Tier
                  </p>
                  <p className="font-extrabold text-slate-900">
                    {label(progress.nextTier)}
                  </p>
                </div>
              ) : (
                <span className="rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-700">
                  Highest Tier
                </span>
              )}
            </div>

            <div className="mt-6">
              <div className="mb-2 flex justify-between text-sm">
                <span className="font-semibold text-slate-500">
                  {points(currentLifetimePoints)} points
                </span>

                {progress.nextTier && (
                  <span className="font-bold text-slate-700">
                    {points(progress.remaining)} points to{" "}
                    {label(progress.nextTier)}
                  </span>
                )}
              </div>

              <div className="h-3 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                  style={{ width: `${progress.percentage}%` }}
                />
              </div>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {TIER_ORDER.map((tierName) => {
                const Icon = tierIcon(tierName);
                const reached =
                  currentLifetimePoints >= TIER_THRESHOLDS[tierName];

                return (
                  <div
                    key={tierName}
                    className={`rounded-xl border p-3 text-center ${
                      tierName === currentTier
                        ? "border-emerald-300 bg-emerald-50"
                        : reached
                          ? "border-slate-200 bg-slate-50"
                          : "border-slate-100 bg-white"
                    }`}
                  >
                    <Icon
                      size={18}
                      className={`mx-auto ${
                        reached ? "text-emerald-600" : "text-slate-300"
                      }`}
                    />

                    <p className="mt-1 text-xs font-bold text-slate-700">
                      {label(tierName)}
                    </p>

                    <p className="mt-0.5 text-[10px] text-slate-400">
                      {points(TIER_THRESHOLDS[tierName])}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Statistics */}

          <div className="grid gap-5 md:grid-cols-2">
            <StatCard
              title="Points Earned"
              helper="From the available loyalty history"
              value={`+${points(earnedPoints)}`}
              icon={<Zap size={20} />}
              className="text-emerald-600 bg-emerald-50"
            />

            <StatCard
              title="Points Redeemed"
              helper="Used for loyalty rewards"
              value={`-${points(redeemedPoints)}`}
              icon={<Gift size={20} />}
              className="text-amber-600 bg-amber-50"
            />
          </div>

          {/* Featured rewards */}

          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-extrabold text-slate-900">
                  Available Rewards
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Rewards currently eligible for your loyalty tier.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setTab("rewards")}
                className="inline-flex items-center gap-1 text-sm font-bold text-emerald-600 hover:text-emerald-700"
              >
                View all
                <ChevronRight size={16} />
              </button>
            </div>

            {eligibleRewards.length === 0 ? (
              <EmptyState
                icon={<Gift size={30} />}
                title="No eligible rewards"
                text="Keep earning points and check again later."
              />
            ) : (
              <div className="mt-5 grid gap-4 md:grid-cols-3">
                {eligibleRewards.slice(0, 3).map((reward) => (
                  <RewardCard
                    key={reward.id}
                    reward={reward}
                    balance={currentBalance}
                    onRedeem={openRedeem}
                  />
                ))}
              </div>
            )}
          </section>

          <RecentActivity
            history={recentHistory}
            onViewAll={() => setTab("activity")}
          />
        </div>
      )}

      {/* Rewards */}

      {tab === "rewards" && (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-xl font-extrabold text-slate-900">
                Rewards Catalogue
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Redeem your SmartPark loyalty points.
              </p>
            </div>

            <div className="rounded-xl bg-emerald-50 px-4 py-2 text-sm font-bold text-emerald-700">
              {points(currentBalance)} points available
            </div>
          </div>

          {eligibleRewards.length === 0 ? (
            <EmptyState
              icon={<Gift size={36} />}
              title="No eligible rewards"
              text="There are currently no rewards available for your tier."
            />
          ) : (
            <div className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {eligibleRewards.map((reward) => (
                <RewardCard
                  key={reward.id}
                  reward={reward}
                  balance={currentBalance}
                  onRedeem={openRedeem}
                />
              ))}
            </div>
          )}
        </section>
      )}

      {/* Redemptions */}

      {tab === "redemptions" && (
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 p-6">
            <h2 className="text-xl font-extrabold text-slate-900">
              My Rewards
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Rewards you have redeemed using loyalty points.
            </p>
          </div>

          {redemptions.length === 0 ? (
            <EmptyState
              icon={<Award size={36} />}
              title="No redeemed rewards"
              text="Your redeemed rewards will appear here."
            />
          ) : (
            <div className="divide-y divide-slate-100">
              {redemptions.map((redemption) => (
                <div
                  key={redemption.id}
                  className="p-5 transition hover:bg-slate-50"
                >
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-start gap-4">
                      <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
                        <Gift size={20} />
                      </div>

                      <div>
                        <h3 className="font-extrabold text-slate-900">
                          {redemption.reward?.name ??
                            redemption.description ??
                            "Loyalty Reward"}
                        </h3>

                        <p className="mt-1 text-xs text-slate-500">
                          Redeemed {dateTime(redemption.created_at)}
                        </p>

                        {redemption.redemption_reference && (
                          <p className="mt-1 font-mono text-xs text-slate-400">
                            {redemption.redemption_reference}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="text-left sm:text-right">
                      <p className="font-extrabold text-slate-900">
                        -{points(redemption.points_spent)} pts
                      </p>

                      <span className="mt-1 inline-flex rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-600">
                        {label(redemption.status)}
                      </span>

                      {redemption.expires_at && (
                        <p className="mt-1 text-xs text-slate-400">
                          Expires {dateOnly(redemption.expires_at)}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Activity */}

      {tab === "activity" && (
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 p-6">
            <h2 className="text-xl font-extrabold text-slate-900">
              Points Activity
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Your loyalty point transaction history.
            </p>
          </div>

          {history.length === 0 ? (
            <EmptyState
              icon={<History size={36} />}
              title="No points activity"
              text="Your loyalty transactions will appear here."
            />
          ) : (
            <div className="divide-y divide-slate-100">
              {history.map((transaction) => {
                const value = toNumber(transaction.points);
                const positive = value > 0;

                return (
                  <div
                    key={transaction.id}
                    className="flex items-center justify-between gap-4 p-5 hover:bg-slate-50"
                  >
                    <div className="flex min-w-0 items-start gap-4">
                      <div
                        className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${
                          positive
                            ? "bg-emerald-50 text-emerald-600"
                            : "bg-amber-50 text-amber-600"
                        }`}
                      >
                        {positive ? <Zap size={18} /> : <Gift size={18} />}
                      </div>

                      <div className="min-w-0">
                        <p className="truncate font-bold text-slate-900">
                          {transaction.description ??
                            label(transaction.transaction_type)}
                        </p>

                        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-400">
                          <span>{dateTime(transaction.created_at)}</span>

                          {transaction.reference_type && (
                            <span>{transaction.reference_type}</span>
                          )}

                          {transaction.reference_id && (
                            <span>#{transaction.reference_id}</span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="shrink-0 text-right">
                      <p
                        className={`font-extrabold ${
                          positive ? "text-emerald-600" : "text-slate-900"
                        }`}
                      >
                        {positive ? "+" : ""}
                        {points(value)}
                      </p>

                      {transaction.balance_after !== undefined &&
                        transaction.balance_after !== null && (
                          <p className="mt-1 text-xs text-slate-400">
                            Balance: {points(transaction.balance_after)}
                          </p>
                        )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {/* Redemption modal */}

      {showRedeemModal && selectedReward && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closeRedeem();
            }
          }}
        >
          <div className="w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-emerald-600">
                  Loyalty Reward
                </p>

                <h2 className="mt-1 text-xl font-extrabold text-slate-900">
                  {success ? "Reward Redeemed" : "Redeem Reward"}
                </h2>
              </div>

              <button
                type="button"
                onClick={closeRedeem}
                disabled={redeeming}
                className="grid h-9 w-9 place-items-center rounded-xl border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-50"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-6">
              {success ? (
                <div className="text-center">
                  <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-emerald-50 text-emerald-600">
                    <CheckCircle2 size={34} />
                  </div>

                  <h3 className="mt-4 text-xl font-extrabold text-slate-900">
                    Successfully Redeemed
                  </h3>

                  <p className="mt-2 text-sm text-slate-500">
                    Your loyalty reward has been redeemed successfully.
                  </p>

                  <div className="mt-5 rounded-xl bg-slate-50 p-4 text-left">
                    <div className="flex justify-between gap-4">
                      <span className="text-sm text-slate-500">Reward</span>
                      <span className="text-right text-sm font-bold text-slate-900">
                        {success.reward?.name ?? selectedReward.name}
                      </span>
                    </div>

                    {success.reference && (
                      <div className="mt-3 flex justify-between gap-4">
                        <span className="text-sm text-slate-500">
                          Reference
                        </span>
                        <span className="text-right font-mono text-xs font-bold text-slate-700">
                          {success.reference}
                        </span>
                      </div>
                    )}

                    <div className="mt-3 flex justify-between gap-4 border-t border-slate-200 pt-3">
                      <span className="text-sm text-slate-500">
                        Remaining Points
                      </span>
                      <span className="text-sm font-extrabold text-emerald-600">
                        {points(success.remainingPoints)}
                      </span>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={closeRedeem}
                    className="mt-5 w-full rounded-xl bg-slate-900 px-4 py-3 text-sm font-bold text-white hover:bg-slate-800"
                  >
                    Close
                  </button>
                </div>
              ) : (
                <>
                  <div className="rounded-2xl bg-emerald-50 p-5">
                    <div className="flex items-start gap-4">
                      <div className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-white text-emerald-600 shadow-sm">
                        <Gift size={23} />
                      </div>

                      <div>
                        <h3 className="font-extrabold text-slate-900">
                          {selectedReward.name}
                        </h3>

                        <p className="mt-1 text-sm text-slate-600">
                          {selectedReward.description ??
                            "Redeem your loyalty points for this reward."}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-5 space-y-3">
                    <SummaryRow
                      label="Reward Cost"
                      value={`${points(selectedReward.points_cost)} points`}
                    />

                    <SummaryRow
                      label="Your Balance"
                      value={`${points(currentBalance)} points`}
                      valueClass="text-emerald-600"
                    />

                    {selectedReward.monetary_value !== null &&
                      selectedReward.monetary_value !== undefined && (
                        <SummaryRow
                          label="Reward Value"
                          value={money(selectedReward.monetary_value)}
                        />
                      )}
                  </div>

                  {currentBalance < toNumber(selectedReward.points_cost) && (
                    <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                      You need{" "}
                      {points(
                        toNumber(selectedReward.points_cost) - currentBalance,
                      )}{" "}
                      more points to redeem this reward.
                    </div>
                  )}

                  <div className="mt-6 flex gap-3">
                    <button
                      type="button"
                      onClick={closeRedeem}
                      disabled={redeeming}
                      className="flex-1 rounded-xl border border-slate-200 px-4 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                    >
                      Cancel
                    </button>

                    <button
                      type="button"
                      onClick={() => void redeemReward()}
                      disabled={
                        redeeming ||
                        currentBalance < toNumber(selectedReward.points_cost)
                      }
                      className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-bold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {redeeming ? (
                        <>
                          <RefreshCw size={16} className="animate-spin" />
                          Redeeming...
                        </>
                      ) : (
                        <>
                          <Gift size={16} />
                          Redeem Reward
                        </>
                      )}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ==========================================================
// Presentational Components
// ==========================================================

function MetricCard({
  label: title,
  value,
  helper,
  icon,
  iconClass,
}: {
  label: string;
  value: string;
  helper: string;
  icon: React.ReactNode;
  iconClass: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-slate-400">
            {title}
          </p>

          <p className="mt-3 text-3xl font-extrabold text-slate-900">{value}</p>

          <p className="mt-1 text-sm text-slate-500">{helper}</p>
        </div>

        <div
          className={`grid h-11 w-11 place-items-center rounded-xl ${iconClass}`}
        >
          {icon}
        </div>
      </div>
    </div>
  );
}

function StatCard({
  title,
  helper,
  value,
  icon,
  className,
}: {
  title: string;
  helper: string;
  value: string;
  icon: React.ReactNode;
  className: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-center gap-3">
        <div
          className={`grid h-10 w-10 place-items-center rounded-xl ${className}`}
        >
          {icon}
        </div>

        <div>
          <p className="text-sm font-bold text-slate-900">{title}</p>
          <p className="text-xs text-slate-500">{helper}</p>
        </div>
      </div>

      <p className={`mt-5 text-2xl font-extrabold ${className.split(" ")[0]}`}>
        {value}
      </p>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  text,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  text: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold transition ${
        active
          ? "bg-slate-900 text-white"
          : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
      }`}
    >
      {icon}
      {text}
    </button>
  );
}

function RewardCard({
  reward,
  balance,
  onRedeem,
}: {
  reward: LoyaltyReward;
  balance: number;
  onRedeem: (reward: LoyaltyReward) => void;
}) {
  const cost = toNumber(reward.points_cost);
  const canRedeem = balance >= cost;

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white transition hover:-translate-y-0.5 hover:border-emerald-200 hover:shadow-md">
      <div className="bg-gradient-to-br from-emerald-50 to-white p-5">
        <div className="grid h-12 w-12 place-items-center rounded-xl bg-white text-emerald-600 shadow-sm">
          <Gift size={22} />
        </div>

        <h3 className="mt-4 font-extrabold text-slate-900">{reward.name}</h3>

        <p className="mt-2 min-h-[40px] text-sm leading-5 text-slate-500">
          {reward.description ?? "Redeem your loyalty points for this reward."}
        </p>
      </div>

      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-widest text-slate-400">
            Cost
          </span>

          <span className="font-extrabold text-emerald-600">
            {points(cost)} pts
          </span>
        </div>

        {reward.monetary_value !== null &&
          reward.monetary_value !== undefined && (
            <div className="mt-3 flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-widest text-slate-400">
                Value
              </span>

              <span className="font-bold text-slate-800">
                {money(reward.monetary_value)}
              </span>
            </div>
          )}

        {reward.minimum_tier && (
          <div className="mt-3 flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-widest text-slate-400">
              Minimum Tier
            </span>

            <span className="font-bold text-slate-700">
              {label(reward.minimum_tier)}
            </span>
          </div>
        )}

        {reward.valid_until && (
          <div className="mt-3 flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-widest text-slate-400">
              Valid Until
            </span>

            <span className="font-bold text-slate-700">
              {dateOnly(reward.valid_until)}
            </span>
          </div>
        )}

        <div className="mt-auto pt-5">
          <button
            type="button"
            onClick={() => onRedeem(reward)}
            disabled={!canRedeem}
            className="w-full rounded-xl bg-emerald-600 px-4 py-3 text-sm font-bold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
          >
            {canRedeem
              ? "Redeem Reward"
              : `Need ${points(cost - balance)} more points`}
          </button>
        </div>
      </div>
    </div>
  );
}

function RecentActivity({
  history,
  onViewAll,
}: {
  history: LoyaltyPointTransaction[];
  onViewAll: () => void;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 p-6">
        <div>
          <h2 className="text-lg font-extrabold text-slate-900">
            Recent Points Activity
          </h2>

          <p className="mt-1 text-sm text-slate-500">
            Your latest loyalty transactions.
          </p>
        </div>

        <button
          type="button"
          onClick={onViewAll}
          className="inline-flex items-center gap-1 text-sm font-bold text-emerald-600 hover:text-emerald-700"
        >
          View all
          <ChevronRight size={16} />
        </button>
      </div>

      {history.length === 0 ? (
        <div className="p-8 text-center">
          <Clock3 size={30} className="mx-auto text-slate-300" />
          <p className="mt-3 text-sm font-bold text-slate-600">
            No recent activity
          </p>
        </div>
      ) : (
        <div className="divide-y divide-slate-100">
          {history.map((transaction) => {
            const value = toNumber(transaction.points);
            const positive = value > 0;

            return (
              <div
                key={transaction.id}
                className="flex items-center justify-between gap-4 p-5"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <div
                    className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${
                      positive
                        ? "bg-emerald-50 text-emerald-600"
                        : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {positive ? <Zap size={16} /> : <Gift size={16} />}
                  </div>

                  <div className="min-w-0">
                    <p className="truncate text-sm font-bold text-slate-900">
                      {transaction.description ??
                        label(transaction.transaction_type)}
                    </p>

                    <p className="mt-1 text-xs text-slate-400">
                      {dateTime(transaction.created_at)}
                    </p>
                  </div>
                </div>

                <span
                  className={`shrink-0 text-sm font-extrabold ${
                    positive ? "text-emerald-600" : "text-slate-900"
                  }`}
                >
                  {positive ? "+" : ""}
                  {points(value)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function EmptyState({
  icon,
  title,
  text,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
}) {
  return (
    <div className="mt-8 rounded-xl border border-dashed border-slate-200 p-10 text-center">
      <div className="mx-auto w-fit text-slate-300">{icon}</div>
      <h3 className="mt-4 font-extrabold text-slate-800">{title}</h3>
      <p className="mt-1 text-sm text-slate-500">{text}</p>
    </div>
  );
}

function SummaryRow({
  label: title,
  value,
  valueClass = "text-slate-900",
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="flex justify-between rounded-xl border border-slate-200 p-4">
      <span className="text-sm text-slate-500">{title}</span>
      <span className={`font-extrabold ${valueClass}`}>{value}</span>
    </div>
  );
}
