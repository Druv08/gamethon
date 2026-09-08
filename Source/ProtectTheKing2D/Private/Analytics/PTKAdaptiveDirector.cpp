// Protect the King - 2D. Decides how the NEXT wave should attack.

#include "Analytics/PTKAdaptiveDirector.h"

#include "Analytics/PTKAnalyticsSubsystem.h"
#include "Characters/PTKGuardCharacter.h"
#include "Components/PTKHealthComponent.h"
#include "Core/PTKBattlefield.h"
#include "Core/PTKGuardBase.h"
#include "Engine/World.h"
#include "ProtectTheKing2D.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKAdaptiveDirector)

namespace
{
	constexpr int32 StrategyCount = static_cast<int32>(EPTKStrategy::Count);

	float Clamp01(float V) { return FMath::Clamp(V, 0.0f, 1.0f); }

	float SafeShare(float Part, float Total)
	{
		return Total > KINDA_SMALL_NUMBER ? Clamp01(Part / Total) : 0.0f;
	}

	/**
	 * What each guard is least comfortable against.
	 *
	 * Biases, never rules: they multiply the wave's own composition rather than
	 * replacing it, so a countered lane still receives a mixed horde and the
	 * wave's total budget is untouched. The wave definition remains the thing
	 * that decides how many of anything exists.
	 */
	struct FCounterBias
	{
		const TCHAR* GuardId;
		const TCHAR* Favour[2];
		const TCHAR* Suppress;
	};

	static const FCounterBias CounterTable[] = {
		// Wraith picks off single targets at range; numerous fast bodies and a
		// heavy that survives the volley trouble it most.
		{ TEXT("Wraith"),   { TEXT("Infiltrator"), TEXT("Encrypter") },  nullptr },
		// Sentinel's splash is worth most against a tight crowd, so thin the
		// crowd and send things that do not clump.
		{ TEXT("Sentinel"), { TEXT("Infiltrator"), TEXT("Encrypter") },  TEXT("SwarmNode") },
		// Ravager hits several targets in melee; ranged attackers and a heavy
		// make that reach matter less.
		{ TEXT("Ravager"),  { TEXT("Exfiltrator"), TEXT("Encrypter") },  nullptr },
		// Reaver is single-target melee, so the same answer applies harder.
		{ TEXT("Reaver"),   { TEXT("Exfiltrator"), TEXT("Encrypter") },  nullptr },
		// Aegis blocks outright while defending; sustained heavy pressure
		// outlasts the shield rather than trying to beat it.
		{ TEXT("Aegis"),    { TEXT("Encrypter"), TEXT("Hijacker") },     TEXT("SwarmNode") },
	};
}

UPTKAdaptiveDirector* UPTKAdaptiveDirector::Get(const UWorld* World)
{
	return World ? World->GetSubsystem<UPTKAdaptiveDirector>() : nullptr;
}

void UPTKAdaptiveDirector::SeedFrom(int32 Seed)
{
	// Offset so the director's rolls are not the same sequence the wave manager
	// is already drawing from its own copy of the seed.
	Stream.Initialize(Seed ^ 0x5A17C0DE);
	bSeeded = true;

	StrategyValues.Init(InitialStrategyValue, StrategyCount);
	StrategyUses.Init(0, StrategyCount);

	UE_LOG(LogPTK, Log, TEXT("DIRECTOR | seeded from %d | %d strategies at %.2f"),
		Seed, StrategyCount, InitialStrategyValue);
}

float UPTKAdaptiveDirector::GetStrategyValue(EPTKStrategy Strategy) const
{
	const int32 Index = static_cast<int32>(Strategy);
	return StrategyValues.IsValidIndex(Index) ? StrategyValues[Index] : InitialStrategyValue;
}

int32 UPTKAdaptiveDirector::GetStrategyUses(EPTKStrategy Strategy) const
{
	const int32 Index = static_cast<int32>(Strategy);
	return StrategyUses.IsValidIndex(Index) ? StrategyUses[Index] : 0;
}

FString UPTKAdaptiveDirector::GetStrategyName(EPTKStrategy Strategy) const
{
	switch (Strategy)
	{
	case EPTKStrategy::BalancedPressure:		return TEXT("Balanced Pressure");
	case EPTKStrategy::ExploitWeakLane:			return TEXT("Exploit Weak Lane");
	case EPTKStrategy::CounterDominantGuard:	return TEXT("Counter Dominant Guard");
	case EPTKStrategy::SplitPressure:			return TEXT("Split Pressure");
	case EPTKStrategy::Breakthrough:			return TEXT("Breakthrough");
	case EPTKStrategy::FocusedAssault:			return TEXT("Focused Assault");
	default:									return TEXT("Unknown");
	}
}

// ---------------------------------------------------------------------------
// Choosing
// ---------------------------------------------------------------------------

float UPTKAdaptiveDirector::ScoreFit(EPTKStrategy Strategy, const FPTKWaveSnapshot& Last,
	bool bHasHistory, TArray<FString>& OutWhy) const
{
	// With nothing to go on, only balance fits. Everything else is a claim
	// about the player that has not been earned yet.
	if (!bHasHistory)
	{
		return Strategy == EPTKStrategy::BalancedPressure ? 1.0f : 0.1f;
	}

	// Signals, read once.
	float WorstLane = 0.0f;
	FName WorstLaneId;
	float BrokenSignal = 0.0f;
	float WeakLanePlayerPresence = 0.0f;
	float TotalPlayerPresence = 0.0f;
	for (const FPTKLaneWaveStats& Lane : Last.Lanes)
	{
		TotalPlayerPresence += Lane.PlayerPresenceSeconds;
		if (Lane.Vulnerability > WorstLane)
		{
			WorstLane = Lane.Vulnerability;
			WorstLaneId = Lane.LaneId;
			WeakLanePlayerPresence = Lane.PlayerPresenceSeconds;
		}
		if (Lane.bBaseDestroyed || Lane.bBreached)
		{
			BrokenSignal = FMath::Max(BrokenSignal, Lane.bBaseDestroyed ? 1.0f : 0.7f);
		}
		BrokenSignal = FMath::Max(BrokenSignal, Lane.BaseDamageTaken > 0.0f
			? Clamp01(Lane.BaseDamageTaken / 2500.0f) : 0.0f);
	}

	float TopDominance = 0.0f;
	float SecondDominance = 0.0f;
	for (const FPTKGuardWaveStats& Guard : Last.Guards)
	{
		if (Guard.Dominance > TopDominance)
		{
			SecondDominance = TopDominance;
			TopDominance = Guard.Dominance;
		}
		else if (Guard.Dominance > SecondDominance)
		{
			SecondDominance = Guard.Dominance;
		}
	}
	const float DominanceGap = FMath::Max(0.0f, TopDominance - SecondDominance);

	switch (Strategy)
	{
	case EPTKStrategy::BalancedPressure:
		// Always plausible, never compelling - the fallback rather than a plan.
		return 0.35f;

	case EPTKStrategy::ExploitWeakLane:
		OutWhy.Add(FString::Printf(TEXT("weakest lane %s at %.2f vulnerability"),
			*WorstLaneId.ToString(), WorstLane));
		return Clamp01(WorstLane * 1.2f);

	case EPTKStrategy::CounterDominantGuard:
		// A clear gap between best and second matters more than a high score:
		// if every guard did well there is no single one to counter.
		OutWhy.Add(FString::Printf(TEXT("dominance gap %.2f"), DominanceGap));
		return Clamp01(TopDominance * 0.5f + DominanceGap * 2.0f);

	case EPTKStrategy::SplitPressure:
	{
		// The counter to a player who cannot be everywhere: either they sat on
		// one guard, or they change guard too slowly to answer two fronts.
		float Fit = 0.2f;
		if (Last.Switching.bSingleGuardFocus)
		{
			Fit += 0.55f;
			OutWhy.Add(FString::Printf(TEXT("player held %s for most of the wave"),
				*Last.Switching.FocusGuardId.ToString()));
		}
		if (Last.Switching.Tempo == EPTKSwitchTempo::Low)
		{
			Fit += 0.25f;
			OutWhy.Add(FString::Printf(TEXT("low switching, %.1f/min"),
				Last.Switching.SwitchesPerMinute));
		}
		return Clamp01(Fit);
	}

	case EPTKStrategy::Breakthrough:
		OutWhy.Add(FString::Printf(TEXT("damaged or breached structures at %.2f"), BrokenSignal));
		return Clamp01(BrokenSignal);

	case EPTKStrategy::FocusedAssault:
	{
		// Worth committing to only where the player is not standing. A heavy
		// push into the lane they are personally defending is just feeding them.
		const float Undefended = 1.0f - SafeShare(WeakLanePlayerPresence, TotalPlayerPresence);
		OutWhy.Add(FString::Printf(TEXT("weak lane %s is %.0f%% undefended"),
			*WorstLaneId.ToString(), Undefended * 100.0f));
		return Clamp01(WorstLane * Undefended * 1.3f);
	}

	default:
		return 0.0f;
	}
}

FPTKDirectorPlan UPTKAdaptiveDirector::BuildPlan(int32 WaveNumber)
{
	if (!bSeeded)
	{
		SeedFrom(FMath::Rand());
	}

	// Idempotent per wave. The plan is built when the INTERMISSION starts, so
	// the analysis panel can show what is coming rather than guessing; the wave
	// itself then asks for the same wave number and must receive the plan the
	// player was just shown, not a freshly rolled one.
	if (CurrentPlan.WaveNumber == WaveNumber && CurrentPlan.Lanes.Num() > 0)
	{
		return CurrentPlan;
	}

	FPTKDirectorPlan Plan;
	Plan.WaveNumber = WaveNumber;

	const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld());
	const UPTKAnalyticsSubsystem* Analytics = UPTKAnalyticsSubsystem::Get(GetWorld());
	if (!Field || !Analytics)
	{
		CurrentPlan = Plan;
		return Plan;
	}

	const bool bHasHistory = Analytics->GetSnapshots().Num() > 0;
	const FPTKWaveSnapshot Last = Analytics->GetLastSnapshot();

	// Score every strategy: how well it fits the situation, plus what it has
	// been worth so far. Fit dominates, so a strategy cannot keep being chosen
	// on past success once the situation that suited it has passed.
	TArray<float> Scores;
	TArray<TArray<FString>> Whys;
	Scores.SetNum(StrategyCount);
	Whys.SetNum(StrategyCount);

	for (int32 i = 0; i < StrategyCount; ++i)
	{
		const EPTKStrategy Strategy = static_cast<EPTKStrategy>(i);
		const float Fit = ScoreFit(Strategy, Last, bHasHistory, Whys[i]);
		Scores[i] = Fit * (1.0f - LearnedValueWeight)
			+ GetStrategyValue(Strategy) * LearnedValueWeight * (bHasHistory ? 1.0f : 0.0f);
	}

	int32 Best = 0;
	for (int32 i = 1; i < StrategyCount; ++i)
	{
		if (Scores[i] > Scores[Best])
		{
			Best = i;
		}
	}

	// A little exploration, so a strategy that has never run can still be
	// reached and the learned table does not freeze on its first success.
	if (bHasHistory && Stream.FRand() < ExplorationChance)
	{
		Best = Stream.RandRange(0, StrategyCount - 1);
		Plan.bExploratory = true;
	}

	Plan.Strategy = static_cast<EPTKStrategy>(Best);
	Plan.Reasoning = Whys[Best];
	Plan.Reasoning.Insert(FString::Printf(TEXT("%s (fit+value %.2f%s)"),
		*GetStrategyName(Plan.Strategy), Scores[Best],
		Plan.bExploratory ? TEXT(", exploratory") : TEXT("")), 0);

	ShapePlan(Plan, Last, bHasHistory, *Field);

	CurrentPlan = Plan;
	return Plan;
}

// ---------------------------------------------------------------------------
// Shaping
// ---------------------------------------------------------------------------

void UPTKAdaptiveDirector::ShapePlan(FPTKDirectorPlan& Plan, const FPTKWaveSnapshot& Last,
	bool bHasHistory, const APTKBattlefield& Field)
{
	// Start from flat pressure on every lane, then let the strategy lean on it.
	// Starting flat rather than from zero guarantees every lane keeps some
	// chance of being used, so no route is ever completely abandoned.
	for (const FPTKLaneRoute& Route : Field.GetRoutes())
	{
		FPTKLanePlan Lane;
		Lane.LaneId = Route.Id;
		Lane.Pressure = 1.0f;
		Plan.Lanes.Add(MoveTemp(Lane));
	}
	if (Plan.Lanes.Num() == 0)
	{
		return;
	}

	auto LaneStatsFor = [&Last](FName LaneId) -> const FPTKLaneWaveStats*
	{
		return Last.Lanes.FindByPredicate(
			[LaneId](const FPTKLaneWaveStats& L) { return L.LaneId == LaneId; });
	};

	// Which lane was weakest, and which guard was strongest.
	FName WeakestLane;
	float WorstVulnerability = -1.0f;
	for (const FPTKLaneWaveStats& Lane : Last.Lanes)
	{
		if (Lane.Vulnerability > WorstVulnerability)
		{
			WorstVulnerability = Lane.Vulnerability;
			WeakestLane = Lane.LaneId;
		}
	}
	FName DominantGuard;
	float TopDominance = -1.0f;
	for (const FPTKGuardWaveStats& Guard : Last.Guards)
	{
		if (Guard.Dominance > TopDominance)
		{
			TopDominance = Guard.Dominance;
			DominantGuard = Guard.GuardId;
		}
	}

	float Cap = MaxLaneShare;

	switch (Plan.Strategy)
	{
	case EPTKStrategy::BalancedPressure:
		// Left flat on purpose.
		Plan.Reasoning.Add(TEXT("even pressure across every lane"));
		break;

	case EPTKStrategy::ExploitWeakLane:
	{
		Plan.TargetLane = WeakestLane;
		for (FPTKLanePlan& Lane : Plan.Lanes)
		{
			if (const FPTKLaneWaveStats* Stats = LaneStatsFor(Lane.LaneId))
			{
				// Scaled by vulnerability rather than switched on for one lane,
				// so the second-weakest lane also gets more than a safe one.
				Lane.Pressure = 1.0f + Stats->Vulnerability * 2.5f;
			}
		}
		Plan.Reasoning.Add(FString::Printf(TEXT("pressure scaled by lane vulnerability, weakest %s"),
			*WeakestLane.ToString()));
		break;
	}

	case EPTKStrategy::CounterDominantGuard:
		Plan.TargetGuard = DominantGuard;
		BiasAgainstGuard(Plan, DominantGuard, Field);
		// Its lane gets somewhat more traffic too, so the counter-composition
		// actually meets the guard it was chosen for.
		for (FPTKLanePlan& Lane : Plan.Lanes)
		{
			const FPTKLaneRoute* Route = Field.FindRoute(Lane.LaneId);
			if (Route && Route->BaseId == DominantGuard)
			{
				Lane.Pressure *= 1.6f;
				Plan.TargetLane = Lane.LaneId;
			}
		}
		Plan.Reasoning.Add(FString::Printf(TEXT("composition biased against %s"),
			*DominantGuard.ToString()));
		break;

	case EPTKStrategy::SplitPressure:
	{
		// Spread across distinct CORNERS, not merely distinct lanes: two lanes
		// out of the same corner arrive together and can be met by one guard,
		// which is exactly what this strategy is meant to defeat.
		TArray<FName> Corners;
		for (const FPTKLaneRoute& Route : Field.GetRoutes())
		{
			Corners.AddUnique(Route.PortalId);
		}
		for (int32 i = Corners.Num() - 1; i > 0; --i)
		{
			Corners.Swap(i, Stream.RandRange(0, i));
		}
		const int32 Wanted = FMath::Min(SplitMinimumLanes, Corners.Num());
		Plan.MinimumPortals = Wanted;
		Corners.SetNum(Wanted);
		for (FPTKLanePlan& Lane : Plan.Lanes)
		{
			const FPTKLaneRoute* Route = Field.FindRoute(Lane.LaneId);
			const bool bChosen = Route && Corners.Contains(Route->PortalId);
			Lane.Pressure = bChosen ? 2.0f : 0.35f;
		}
		// Tighter than the normal cap: the point is breadth, and a 40% lane
		// inside a "split" wave is not a split.
		Cap = FMath::Min(MaxLaneShare, 1.0f / FMath::Max(Wanted - 1, 1));
		Plan.Reasoning.Add(FString::Printf(TEXT("spread across %d corners, cap %.0f%%"),
			Wanted, Cap * 100.0f));
		break;
	}

	case EPTKStrategy::Breakthrough:
	{
		for (FPTKLanePlan& Lane : Plan.Lanes)
		{
			if (const FPTKLaneWaveStats* Stats = LaneStatsFor(Lane.LaneId))
			{
				const float Damage = Clamp01(Stats->BaseDamageTaken / 2500.0f);
				Lane.Pressure = 1.0f + Damage * 2.0f
					+ (Stats->bBreached ? 1.0f : 0.0f)
					+ (Stats->bBaseDestroyed ? 1.5f : 0.0f);
				if (Lane.Pressure > 1.5f)
				{
					Plan.TargetLane = Lane.LaneId;
				}
			}
			// Heavies and structure-killers, aimed at finishing the job.
			Lane.TypeWeights.Add(FName(TEXT("Hijacker")), FavouredTypeMultiplier);
			Lane.TypeWeights.Add(FName(TEXT("Encrypter")), FavouredTypeMultiplier);
		}
		Plan.Reasoning.Add(TEXT("pressing damaged structures with Hijacker and Encrypter"));
		break;
	}

	case EPTKStrategy::FocusedAssault:
	{
		Plan.TargetLane = WeakestLane;
		for (FPTKLanePlan& Lane : Plan.Lanes)
		{
			Lane.Pressure = (Lane.LaneId == WeakestLane) ? 6.0f : 0.5f;
		}
		Cap = MaxLaneShareFocused;
		Plan.Reasoning.Add(FString::Printf(TEXT("committing to %s, cap %.0f%%"),
			*WeakestLane.ToString(), Cap * 100.0f));
		break;
	}

	default:
		break;
	}

	// Whoever led the last wave is worth countering whatever the headline
	// strategy is. The bias is light - two enemy types doubled on that guard's
	// own lanes - and it costs nothing to carry, so it applies whenever there
	// is a leader at all rather than only when one scores above some bar.
	//
	// An earlier version gated this on TopDominance > 0.5 and was invisible for
	// whole runs: in a wave where the guards split the work evenly, nobody
	// cleared the bar, and two runs with quite different play produced byte
	// identical plans. A leader who is only narrowly ahead is still the leader.
	if (bHasHistory && Plan.Strategy != EPTKStrategy::CounterDominantGuard
		&& !DominantGuard.IsNone() && TopDominance > 0.0f)
	{
		BiasAgainstGuard(Plan, DominantGuard, Field);
		Plan.Reasoning.Add(FString::Printf(TEXT("light counter to %s, who led at %.2f"),
			*DominantGuard.ToString(), TopDominance));
	}

	NormaliseAndCap(Plan, Cap);
}

void UPTKAdaptiveDirector::BiasAgainstGuard(FPTKDirectorPlan& Plan, FName GuardId,
	const APTKBattlefield& Field)
{
	const FCounterBias* Bias = nullptr;
	for (const FCounterBias& Entry : CounterTable)
	{
		if (GuardId == FName(Entry.GuardId))
		{
			Bias = &Entry;
			break;
		}
	}
	if (!Bias)
	{
		return;
	}

	// Applied only to the lanes that actually reach this guard's base. A bias
	// smeared over every lane would not be a counter to anybody.
	for (FPTKLanePlan& Lane : Plan.Lanes)
	{
		const FPTKLaneRoute* Route = Field.FindRoute(Lane.LaneId);
		if (!Route || Route->BaseId != GuardId)
		{
			continue;
		}
		for (const TCHAR* Favoured : Bias->Favour)
		{
			if (Favoured)
			{
				float& Weight = Lane.TypeWeights.FindOrAdd(FName(Favoured), 1.0f);
				Weight *= FavouredTypeMultiplier;
			}
		}
		if (Bias->Suppress)
		{
			float& Weight = Lane.TypeWeights.FindOrAdd(FName(Bias->Suppress), 1.0f);
			Weight *= SuppressedTypeMultiplier;
		}
	}
}

void UPTKAdaptiveDirector::NormaliseAndCap(FPTKDirectorPlan& Plan, float Cap) const
{
	if (Plan.Lanes.Num() == 0)
	{
		return;
	}
	// A cap below an even split is impossible to satisfy, so it is raised to
	// one rather than looping forever trying.
	Cap = FMath::Max(Cap, 1.0f / Plan.Lanes.Num());

	// Normalise, clip whatever exceeds the cap, and hand the clipped surplus to
	// the lanes still under it. Repeated because redistributing can push a
	// second lane over; it settles in a couple of passes.
	for (int32 Pass = 0; Pass < 8; ++Pass)
	{
		float Total = 0.0f;
		for (const FPTKLanePlan& Lane : Plan.Lanes)
		{
			Total += FMath::Max(Lane.Pressure, 0.0f);
		}
		if (Total <= KINDA_SMALL_NUMBER)
		{
			for (FPTKLanePlan& Lane : Plan.Lanes)
			{
				Lane.Pressure = 1.0f / Plan.Lanes.Num();
			}
			return;
		}

		float Surplus = 0.0f;
		float Headroom = 0.0f;
		for (FPTKLanePlan& Lane : Plan.Lanes)
		{
			Lane.Pressure = FMath::Max(Lane.Pressure, 0.0f) / Total;
			if (Lane.Pressure > Cap)
			{
				Surplus += Lane.Pressure - Cap;
				Lane.Pressure = Cap;
			}
			else
			{
				Headroom += Cap - Lane.Pressure;
			}
		}
		if (Surplus <= KINDA_SMALL_NUMBER || Headroom <= KINDA_SMALL_NUMBER)
		{
			return;
		}
		for (FPTKLanePlan& Lane : Plan.Lanes)
		{
			if (Lane.Pressure < Cap)
			{
				Lane.Pressure += Surplus * ((Cap - Lane.Pressure) / Headroom);
			}
		}
	}
}

// ---------------------------------------------------------------------------
// Learning
// ---------------------------------------------------------------------------

float UPTKAdaptiveDirector::ScoreReward(const FPTKWaveSnapshot& Snapshot) const
{
	// Scored from the HORDE's side: this is the reward for the attacking plan,
	// so hurting guards, breaking bases and reaching the core all count as
	// success. It is not a measure of whether the game went well for the player.
	float GuardDamage = 0.0f;
	int32 GuardsLost = 0;
	for (const FPTKGuardWaveStats& Guard : Snapshot.Guards)
	{
		GuardDamage += Guard.DamageTaken;
		if (!Guard.bAlive)
		{
			++GuardsLost;
		}
	}

	float BaseDamage = 0.0f;
	int32 BasesDestroyed = 0;
	float DeepestProgress = 0.0f;
	float KingDamage = 0.0f;
	for (const FPTKLaneWaveStats& Lane : Snapshot.Lanes)
	{
		BaseDamage += Lane.BaseDamageTaken;
		BasesDestroyed += Lane.bBaseDestroyed ? 1 : 0;
		DeepestProgress = FMath::Max(DeepestProgress, Lane.DeepestProgress);
		KingDamage += Lane.KingDamageFromLane;
	}

	const int32 GuardCount = FMath::Max(Snapshot.Guards.Num(), 1);
	const int32 LaneCount = FMath::Max(Snapshot.Lanes.Num(), 1);

	return Clamp01(
		SafeShare(GuardDamage, RewardGuardDamageReference) * RewardGuardDamage
		+ SafeShare(static_cast<float>(GuardsLost), static_cast<float>(GuardCount)) * RewardGuardKills
		+ SafeShare(BaseDamage, 2500.0f * LaneCount) * RewardBaseDamage
		+ SafeShare(static_cast<float>(BasesDestroyed), 5.0f) * RewardBasesDestroyed
		+ Clamp01(DeepestProgress) * RewardLaneProgress
		+ SafeShare(KingDamage, RewardKingDamageReference) * RewardKingDamage);
}

void UPTKAdaptiveDirector::LearnFromWave(const FPTKWaveSnapshot& Snapshot)
{
	const int32 Index = static_cast<int32>(CurrentPlan.Strategy);
	if (!StrategyValues.IsValidIndex(Index))
	{
		return;
	}

	// Remembered before the next plan overwrites CurrentPlan, so the panel can
	// say what was tried last as well as what is being tried next.
	PreviousStrategy = CurrentPlan.Strategy;
	bHasPrevious = true;

	LastReward = ScoreReward(Snapshot);
	const float Before = StrategyValues[Index];
	StrategyValues[Index] = Before + LearningRate * (LastReward - Before);
	++StrategyUses[Index];

	UE_LOG(LogPTK, Warning,
		TEXT("DIRECTOR | wave %d ran %s | reward %.3f | value %.3f -> %.3f (used %d)"),
		Snapshot.WaveNumber, *GetStrategyName(CurrentPlan.Strategy), LastReward,
		Before, StrategyValues[Index], StrategyUses[Index]);
}

void UPTKAdaptiveDirector::LogPlan() const
{
	UE_LOG(LogPTK, Warning, TEXT("DIRECTOR | wave %d | %s%s"),
		CurrentPlan.WaveNumber, *GetStrategyName(CurrentPlan.Strategy),
		CurrentPlan.bExploratory ? TEXT(" [exploring]") : TEXT(""));
	for (const FString& Why : CurrentPlan.Reasoning)
	{
		UE_LOG(LogPTK, Warning, TEXT("    why: %s"), *Why);
	}
	for (const FPTKLanePlan& Lane : CurrentPlan.Lanes)
	{
		FString Types;
		for (const TPair<FName, float>& Pair : Lane.TypeWeights)
		{
			Types += FString::Printf(TEXT(" %s x%.2f"), *Pair.Key.ToString(), Pair.Value);
		}
		UE_LOG(LogPTK, Warning, TEXT("    %-14s pressure %.2f%s"),
			*Lane.LaneId.ToString(), Lane.Pressure, *Types);
	}
	for (int32 i = 0; i < StrategyValues.Num(); ++i)
	{
		UE_LOG(LogPTK, Warning, TEXT("    value %-24s %.3f (used %d)"),
			*GetStrategyName(static_cast<EPTKStrategy>(i)), StrategyValues[i], StrategyUses[i]);
	}
}

// ---------------------------------------------------------------------------
// Readouts. Every one of these reads a value the analytics actually computed -
// nothing here is estimated, rounded up for effect, or written to make the AI
// sound cleverer than it is.
// ---------------------------------------------------------------------------

FName UPTKAdaptiveDirector::GetFocusGuard(float& OutShare) const
{
	OutShare = 0.0f;
	const UPTKAnalyticsSubsystem* Analytics = UPTKAnalyticsSubsystem::Get(GetWorld());
	if (!Analytics || Analytics->GetSnapshots().Num() == 0)
	{
		return NAME_None;
	}
	const FPTKWaveSnapshot Last = Analytics->GetLastSnapshot();
	FName Best;
	for (const FPTKGuardWaveStats& Guard : Last.Guards)
	{
		if (Guard.PlayerControlFraction > OutShare)
		{
			OutShare = Guard.PlayerControlFraction;
			Best = Guard.GuardId;
		}
	}
	return Best;
}

FName UPTKAdaptiveDirector::GetWeakestLane(float& OutVulnerability) const
{
	OutVulnerability = 0.0f;
	const UPTKAnalyticsSubsystem* Analytics = UPTKAnalyticsSubsystem::Get(GetWorld());
	if (!Analytics || Analytics->GetSnapshots().Num() == 0)
	{
		return NAME_None;
	}
	const FPTKWaveSnapshot Last = Analytics->GetLastSnapshot();
	FName Best;
	for (const FPTKLaneWaveStats& Lane : Last.Lanes)
	{
		if (Lane.Vulnerability > OutVulnerability)
		{
			OutVulnerability = Lane.Vulnerability;
			Best = Lane.LaneId;
		}
	}
	return Best;
}

FName UPTKAdaptiveDirector::GetDominantGuard(float& OutDominance) const
{
	OutDominance = 0.0f;
	const UPTKAnalyticsSubsystem* Analytics = UPTKAnalyticsSubsystem::Get(GetWorld());
	if (!Analytics || Analytics->GetSnapshots().Num() == 0)
	{
		return NAME_None;
	}
	const FPTKWaveSnapshot Last = Analytics->GetLastSnapshot();
	FName Best;
	for (const FPTKGuardWaveStats& Guard : Last.Guards)
	{
		if (Guard.Dominance > OutDominance)
		{
			OutDominance = Guard.Dominance;
			Best = Guard.GuardId;
		}
	}
	return Best;
}

void UPTKAdaptiveDirector::LogWaveBlock(int32 WaveNumber) const
{
	const UPTKAnalyticsSubsystem* Analytics = UPTKAnalyticsSubsystem::Get(GetWorld());
	if (!Analytics || Analytics->GetSnapshots().Num() == 0)
	{
		return;
	}
	const FPTKWaveSnapshot Last = Analytics->GetLastSnapshot();

	float FocusShare = 0.0f;
	float WeakVuln = 0.0f;
	float TopDom = 0.0f;
	const FName Focus = GetFocusGuard(FocusShare);
	const FName Weak = GetWeakestLane(WeakVuln);
	const FName Dominant = GetDominantGuard(TopDom);

	const TCHAR* Tempo =
		Last.Switching.Tempo == EPTKSwitchTempo::High ? TEXT("High")
		: Last.Switching.Tempo == EPTKSwitchTempo::Medium ? TEXT("Medium") : TEXT("Low");

	UE_LOG(LogPTK, Warning, TEXT("[PTK Adaptive AI]"));
	UE_LOG(LogPTK, Warning, TEXT("  Wave %d"), WaveNumber);
	UE_LOG(LogPTK, Warning, TEXT("  PlayerFocus=%s %.2f"), *Focus.ToString(), FocusShare);
	UE_LOG(LogPTK, Warning, TEXT("  Switching=%s (%.1f/min)"), Tempo, Last.Switching.SwitchesPerMinute);
	UE_LOG(LogPTK, Warning, TEXT("  WeakLane=%s %.2f"), *Weak.ToString(), WeakVuln);
	UE_LOG(LogPTK, Warning, TEXT("  DominantGuard=%s %.2f"), *Dominant.ToString(), TopDom);
	UE_LOG(LogPTK, Warning, TEXT("  PreviousStrategy=%s"),
		bHasPrevious ? *GetStrategyName(PreviousStrategy) : TEXT("none"));
	UE_LOG(LogPTK, Warning, TEXT("  Reward=%.2f"), LastReward);
	UE_LOG(LogPTK, Warning, TEXT("  SelectedStrategy=%s%s"),
		*GetStrategyName(CurrentPlan.Strategy),
		CurrentPlan.bExploratory ? TEXT(" (exploring)") : TEXT(""));
}
