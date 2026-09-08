// Protect the King - 2D. Decides how the NEXT wave should attack.

#pragma once

#include "CoreMinimal.h"
#include "Analytics/PTKAnalyticsTypes.h"
#include "Subsystems/WorldSubsystem.h"
#include "PTKAdaptiveDirector.generated.h"

class APTKBattlefield;
class UPTKAnalyticsSubsystem;

/** How the next wave intends to attack. */
UENUM(BlueprintType)
enum class EPTKStrategy : uint8
{
	/** Even pressure everywhere. The default while there is nothing to learn from. */
	BalancedPressure	UMETA(DisplayName = "Balanced Pressure"),
	/** Lean on whichever lane scored most vulnerable. */
	ExploitWeakLane		UMETA(DisplayName = "Exploit Weak Lane"),
	/** Re-mix enemy types around the guard that did the most damage. */
	CounterDominantGuard UMETA(DisplayName = "Counter Dominant Guard"),
	/** Spread across three or more lanes at once. */
	SplitPressure		UMETA(DisplayName = "Split Pressure"),
	/** Finish off what is already broken. */
	Breakthrough		UMETA(DisplayName = "Breakthrough"),
	/** Put a large share of the same budget down one lane. */
	FocusedAssault		UMETA(DisplayName = "Focused Assault"),

	Count				UMETA(Hidden)
};

/** What the director wants to happen on one lane. */
USTRUCT(BlueprintType)
struct PROTECTTHEKING2D_API FPTKLanePlan
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "PTK|Director") FName LaneId;
	/** Share of the wave to send here, 0..1 across all lanes. */
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Director") float Pressure = 0.0f;
	/** Enemy id -> relative weight. Multiplies the wave's own composition. */
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Director") TMap<FName, float> TypeWeights;
};

/**
 * The whole decision for one wave, plus why it was made.
 *
 * The reasoning strings exist so the choice can be read back and argued with.
 * An adaptive system whose output is a number nobody can explain is one nobody
 * can debug, and this one is deliberately small enough to justify in words.
 */
USTRUCT(BlueprintType)
struct PROTECTTHEKING2D_API FPTKDirectorPlan
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "PTK|Director") int32 WaveNumber = 0;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Director") EPTKStrategy Strategy = EPTKStrategy::BalancedPressure;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Director") TArray<FPTKLanePlan> Lanes;
	/** The guard being countered, when the strategy is about one. */
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Director") FName TargetGuard;
	/** The lane being leaned on, when the strategy is about one. */
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Director") FName TargetLane;
	/**
	 * Corners the wave should open at minimum.
	 *
	 * Lane allocation, not budget: Split Pressure needs several fronts to
	 * exist before it can spread across them, and a two-corner wave cannot be
	 * split three ways however the weights are arranged. The number of enemies
	 * is untouched.
	 */
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Director") int32 MinimumPortals = 0;
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Director") TArray<FString> Reasoning;
	/** True when the strategy was picked by exploration rather than by score. */
	UPROPERTY(BlueprintReadOnly, Category = "PTK|Director") bool bExploratory = false;
};

/**
 * UPTKAdaptiveDirector
 * ====================
 * Reads the wave that just happened and decides how the next one attacks.
 *
 * It may change only three things: which lanes get pressure, how much each
 * gets, and what types walk down them. It never touches health, damage, counts,
 * movement or pathing - an opponent that wins by quietly inflating its own
 * numbers has not out-thought the player, it has cheated, and the difference
 * matters more here than the difficulty does.
 *
 *
 * THE LEARNING IS DELIBERATELY SMALL
 * ----------------------------------
 * One value per strategy, moved toward the reward it earned:
 *
 *     V <- V + LearningRate * (Reward - V)
 *
 * That is a bandit, not a network. It is a few dozen bytes, it converges in a
 * handful of waves - which is all a five-wave run has - and every number in it
 * can be printed and understood. A neural network here would need more data
 * than a whole run produces and would replace an explainable choice with an
 * unexplainable one.
 *
 * Strategy choice is NOT the learned value alone. It is the learned value plus
 * how well the strategy fits what the analytics currently say, plus a little
 * exploration - so a strategy that has never been tried can still be reached,
 * and a strategy that once worked cannot keep being chosen after the situation
 * it suited has gone.
 *
 *
 * SEEDING, RESTART AND NEW GAME
 * -----------------------------
 * The director's randomness comes from the wave manager's seed, so a Restart -
 * which replays that seed - makes the same exploration rolls. The DECISIONS can
 * still differ, because they also depend on what the player did, which is the
 * property the same-seed A/B test checks. Learned values live in the world and
 * die with it, so both Restart and New Game begin with a clean slate.
 */
UCLASS()
class PROTECTTHEKING2D_API UPTKAdaptiveDirector : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	static UPTKAdaptiveDirector* Get(const UWorld* World);

	/** Seeds the exploration rolls. Called by the wave manager at BeginPlay. */
	void SeedFrom(int32 Seed);

	/**
	 * Decides how wave WaveNumber should attack.
	 *
	 * Reads the analytics history as it stands, so calling it before wave 1 -
	 * when there is no history - correctly yields balanced pressure.
	 */
	FPTKDirectorPlan BuildPlan(int32 WaveNumber);

	/** Scores the wave that just ended and updates the strategy that ran it. */
	void LearnFromWave(const FPTKWaveSnapshot& Snapshot);

	UFUNCTION(BlueprintPure, Category = "PTK|Director")
	FPTKDirectorPlan GetCurrentPlan() const { return CurrentPlan; }

	/** Learned value of a strategy, 0..1. */
	UFUNCTION(BlueprintPure, Category = "PTK|Director")
	float GetStrategyValue(EPTKStrategy Strategy) const;

	/** How many times a strategy has actually run. */
	UFUNCTION(BlueprintPure, Category = "PTK|Director")
	int32 GetStrategyUses(EPTKStrategy Strategy) const;

	/** The reward the last finished wave earned its strategy. */
	UFUNCTION(BlueprintPure, Category = "PTK|Director")
	float GetLastReward() const { return LastReward; }

	/**
	 * The strategy of the wave that just FINISHED, as opposed to the one about
	 * to run. Both are needed at once during an intermission, which is exactly
	 * when the analysis panel is on screen saying what changed and why.
	 */
	UFUNCTION(BlueprintPure, Category = "PTK|Director")
	EPTKStrategy GetPreviousStrategy() const { return PreviousStrategy; }

	UFUNCTION(BlueprintPure, Category = "PTK|Director")
	bool HasPreviousStrategy() const { return bHasPrevious; }

	UFUNCTION(BlueprintPure, Category = "PTK|Director")
	FString GetStrategyName(EPTKStrategy Strategy) const;

	/** Prints the plan and the learned table. Verification aid. */
	UFUNCTION(BlueprintCallable, Category = "PTK|Director")
	void LogPlan() const;

	/**
	 * One block per wave, written when the next wave is decided.
	 *
	 * Deliberately once per wave and not per tick: a running commentary of the
	 * same numbers sixty times a second buries the one moment that matters,
	 * which is the moment the decision changes.
	 */
	UFUNCTION(BlueprintCallable, Category = "PTK|Director")
	void LogWaveBlock(int32 WaveNumber) const;

	/** Player focus guard and its share, from the last finished wave. */
	UFUNCTION(BlueprintPure, Category = "PTK|Director")
	FName GetFocusGuard(float& OutShare) const;

	/** Weakest lane of the last finished wave and its vulnerability. */
	UFUNCTION(BlueprintPure, Category = "PTK|Director")
	FName GetWeakestLane(float& OutVulnerability) const;

	/** Strongest guard of the last finished wave and its dominance. */
	UFUNCTION(BlueprintPure, Category = "PTK|Director")
	FName GetDominantGuard(float& OutDominance) const;

	// ------------------------------------------------------------------
	// Tuning
	// ------------------------------------------------------------------

	UPROPERTY(EditAnywhere, Category = "PTK|Director|Learning", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float LearningRate = 0.35f;

	/** Value a strategy starts on, before it has ever run. */
	UPROPERTY(EditAnywhere, Category = "PTK|Director|Learning", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float InitialStrategyValue = 0.5f;

	/** Chance of picking at random instead of by score. */
	UPROPERTY(EditAnywhere, Category = "PTK|Director|Learning", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float ExplorationChance = 0.15f;

	/** How much the learned value counts against situational fit when choosing. */
	UPROPERTY(EditAnywhere, Category = "PTK|Director|Learning", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float LearnedValueWeight = 0.45f;

	/** Largest share of a wave one lane may receive, normally. */
	UPROPERTY(EditAnywhere, Category = "PTK|Director|Pressure", meta = (ClampMin = "0.1", ClampMax = "1.0"))
	float MaxLaneShare = 0.40f;

	/** Largest share one lane may receive under Focused Assault. */
	UPROPERTY(EditAnywhere, Category = "PTK|Director|Pressure", meta = (ClampMin = "0.1", ClampMax = "1.0"))
	float MaxLaneShareFocused = 0.55f;

	/** Lanes Split Pressure must spread across at least. */
	UPROPERTY(EditAnywhere, Category = "PTK|Director|Pressure", meta = (ClampMin = "2"))
	int32 SplitMinimumLanes = 3;

	/** Weight multiplier applied to a type a strategy favours. */
	UPROPERTY(EditAnywhere, Category = "PTK|Director|Composition", meta = (ClampMin = "1.0"))
	float FavouredTypeMultiplier = 2.0f;

	/** Weight multiplier applied to a type a strategy wants less of. */
	UPROPERTY(EditAnywhere, Category = "PTK|Director|Composition", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float SuppressedTypeMultiplier = 0.5f;

	// Reward weights. What "the wave went well" means, from the horde's side.
	UPROPERTY(EditAnywhere, Category = "PTK|Director|Reward") float RewardGuardDamage = 0.22f;
	UPROPERTY(EditAnywhere, Category = "PTK|Director|Reward") float RewardGuardKills = 0.18f;
	UPROPERTY(EditAnywhere, Category = "PTK|Director|Reward") float RewardBaseDamage = 0.22f;
	UPROPERTY(EditAnywhere, Category = "PTK|Director|Reward") float RewardBasesDestroyed = 0.15f;
	UPROPERTY(EditAnywhere, Category = "PTK|Director|Reward") float RewardLaneProgress = 0.13f;
	UPROPERTY(EditAnywhere, Category = "PTK|Director|Reward") float RewardKingDamage = 0.10f;

	/** Guard damage across a wave that counts as a full score. */
	UPROPERTY(EditAnywhere, Category = "PTK|Director|Reward", meta = (ClampMin = "1.0"))
	float RewardGuardDamageReference = 4000.0f;

	/** King damage across a wave that counts as a full score. */
	UPROPERTY(EditAnywhere, Category = "PTK|Director|Reward", meta = (ClampMin = "1.0"))
	float RewardKingDamageReference = 1500.0f;

private:
	/** How well a strategy suits what the analytics currently say, 0..1. */
	float ScoreFit(EPTKStrategy Strategy, const FPTKWaveSnapshot& Last,
		bool bHasHistory, TArray<FString>& OutWhy) const;

	/** Turns the chosen strategy into per-lane pressure and composition. */
	void ShapePlan(FPTKDirectorPlan& Plan, const FPTKWaveSnapshot& Last,
		bool bHasHistory, const APTKBattlefield& Field);

	/** Normalises pressures to sum to 1 and enforces the cap. */
	void NormaliseAndCap(FPTKDirectorPlan& Plan, float Cap) const;

	/** Applies the per-guard counter table to the lane that guard defends. */
	void BiasAgainstGuard(FPTKDirectorPlan& Plan, FName GuardId, const APTKBattlefield& Field);

	/** Reward for the enemy side, 0..1, from a finished wave. */
	float ScoreReward(const FPTKWaveSnapshot& Snapshot) const;

	UPROPERTY() TArray<float> StrategyValues;
	UPROPERTY() TArray<int32> StrategyUses;

	FPTKDirectorPlan CurrentPlan;
	float LastReward = 0.0f;
	EPTKStrategy PreviousStrategy = EPTKStrategy::BalancedPressure;
	bool bHasPrevious = false;
	FRandomStream Stream;
	bool bSeeded = false;
};
